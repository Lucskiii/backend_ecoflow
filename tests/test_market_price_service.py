from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.tables import CoreTsMarketPrice
from app.services.market_price_service import AwattarFetchResult, AwattarPricePoint, MarketPriceService


class _Obj:
    def __init__(self, id: int):
        self.id = id


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def _make_point(ts: datetime, price: str) -> AwattarPricePoint:
    return AwattarPricePoint(ts_utc=ts, price_eur_mwh=Decimal(price), unit="Eur/MWh")


def _make_result(points: list[AwattarPricePoint]) -> AwattarFetchResult:
    return AwattarFetchResult(
        source_url="https://api.awattar.test",
        raw_payload={"data": []},
        points=points,
    )


def test_refresh_prices_is_idempotent_for_overlapping_windows() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = MarketPriceService(db)
    service._get_or_create_market = lambda: _Obj(1)  # type: ignore[method-assign]
    service._get_or_create_product = lambda market_id: _Obj(1)  # type: ignore[method-assign]
    service._get_or_create_bidding_zone = lambda: _Obj(1)  # type: ignore[method-assign]

    p1 = _make_point(datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc), "90.5")
    p2 = _make_point(datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc), "91.0")
    p3 = _make_point(datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc), "89.4")

    service._fetch_marketdata = lambda **kwargs: _make_result([p1, p2])  # type: ignore[method-assign]
    first_inserted = service.refresh_prices()

    service._fetch_marketdata = lambda **kwargs: _make_result([p2, p3])  # type: ignore[method-assign]
    second_inserted = service.refresh_prices()

    service._fetch_marketdata = lambda **kwargs: _make_result([p1, p2, p3])  # type: ignore[method-assign]
    third_inserted = service.refresh_prices()

    total_rows = db.scalar(select(func.count()).select_from(CoreTsMarketPrice))

    assert first_inserted == 2
    assert second_inserted == 1
    assert third_inserted == 0
    assert total_rows == 3

    db.close()


def test_refresh_prices_logs_existing_and_inserted_counts(caplog) -> None:
    caplog.set_level("INFO")
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = MarketPriceService(db)
    service._get_or_create_market = lambda: _Obj(1)  # type: ignore[method-assign]
    service._get_or_create_product = lambda market_id: _Obj(1)  # type: ignore[method-assign]
    service._get_or_create_bidding_zone = lambda: _Obj(1)  # type: ignore[method-assign]

    p1 = _make_point(datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc), "90.5")
    p2 = _make_point(datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc), "91.0")

    service._fetch_marketdata = lambda **kwargs: _make_result([p1, p2])  # type: ignore[method-assign]
    service.refresh_prices()

    caplog.clear()
    service._fetch_marketdata = lambda **kwargs: _make_result([p1, p2])  # type: ignore[method-assign]
    inserted = service.refresh_prices()

    assert inserted == 0
    assert "api_points=2 existing=2 inserted=0" in caplog.text

    db.close()


def test_get_live_prices_returns_current_and_next_point() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = MarketPriceService(db)

    now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)
    p1 = _make_point(now.replace(minute=0), "100.0")
    p2 = _make_point(now.replace(minute=0) + timedelta(hours=1), "120.0")
    service._fetch_marketdata = lambda **kwargs: _make_result([p2, p1])  # type: ignore[method-assign]

    payload = service.get_live_prices(lookback_hours=2, lookahead_hours=2)

    assert payload["current"] is not None
    assert payload["next"] is not None
    assert payload["current"]["price_eur_mwh"] == Decimal("100.0")
    assert payload["current"]["price_ct_kwh"] == Decimal("10.0000")
    assert payload["next"]["price_eur_mwh"] == Decimal("120.0")
    assert len(payload["points"]) == 2

    db.close()
