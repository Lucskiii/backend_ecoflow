from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.router import get_live_market_prices
from app.database import Base
from app.services.market_price_service import MarketPriceService


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_get_live_market_prices_endpoint_shape() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()

    now = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)

    def fake_get_live_prices(self, lookback_hours: int, lookahead_hours: int) -> dict:
        point_now = {
            "ts": now,
            "price_eur_mwh": Decimal("85.1"),
            "price_ct_kwh": Decimal("8.5100"),
        }
        point_next = {
            "ts": now.replace(hour=13),
            "price_eur_mwh": Decimal("90.2"),
            "price_ct_kwh": Decimal("9.0200"),
        }
        return {
            "source": "awattar",
            "product": "DE day-ahead",
            "unit": "Eur/MWh",
            "fetched_at": now,
            "current": point_now,
            "next": point_next,
            "points": [point_now, point_next],
        }

    original = MarketPriceService.get_live_prices
    MarketPriceService.get_live_prices = fake_get_live_prices  # type: ignore[method-assign]
    try:
        response = get_live_market_prices(lookback_hours=3, lookahead_hours=36, db=db)
    finally:
        MarketPriceService.get_live_prices = original  # type: ignore[assignment]
        db.close()

    assert response.source == "awattar"
    assert response.current is not None
    assert response.current.price_ct_kwh == Decimal("8.5100")
    assert response.next is not None
    assert response.next.price_eur_mwh == Decimal("90.2")
    assert len(response.points) == 2
