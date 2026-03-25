from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.tables import CoreBiddingZone, CoreMarket, CoreMarketProduct, CoreTsMarketPrice
from app.services.market_price_backfill_service import MarketPriceBackfillService
from app.services.market_price_service import AwattarFetchResult, AwattarPricePoint


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def _seed_market(db: Session) -> tuple[int, int]:
    market = CoreMarket(id=1, code="AWATTAR", name="aWATTar")
    zone = CoreBiddingZone(id=1, code="AT", name="Austria")
    db.add_all([market, zone])
    db.flush()
    product = CoreMarketProduct(
        id=1,
        market_id=market.id,
        product_code="AT_DAY_AHEAD",
        granularity_minutes=60,
        direction=None,
    )
    db.add(product)
    db.flush()
    return product.id, zone.id


def test_market_price_backfill_inserts_only_missing_history() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    product_id, zone_id = _seed_market(db)
    db.add(
        CoreTsMarketPrice(
            market_product_id=product_id,
            bidding_zone_id=zone_id,
            ts=datetime(2025, 4, 1, 0, 0),
            price=Decimal("100"),
            currency="EUR",
        )
    )
    db.commit()

    service = MarketPriceBackfillService(db)

    p1 = AwattarPricePoint(
        ts_utc=datetime(2025, 3, 30, 0, 0, tzinfo=timezone.utc),
        price_eur_mwh=Decimal("90"),
        unit="Eur/MWh",
    )
    p2 = AwattarPricePoint(
        ts_utc=datetime(2025, 3, 31, 0, 0, tzinfo=timezone.utc),
        price_eur_mwh=Decimal("95"),
        unit="Eur/MWh",
    )

    service.market_price_service._fetch_marketdata = lambda **kwargs: AwattarFetchResult(  # type: ignore[method-assign]
        source_url="https://api.awattar.test",
        raw_payload={"data": []},
        points=[p1, p2],
    )

    summary = service.run_historical_backfill(target_start_date=date(2025, 3, 30))

    rows = db.execute(
        select(CoreTsMarketPrice).where(CoreTsMarketPrice.market_product_id == product_id)
    ).scalars().all()

    assert summary.processed_products == 1
    assert summary.inserted_rows == 2
    assert len(rows) == 3

    second = service.run_historical_backfill(target_start_date=date(2025, 3, 30))
    assert second.inserted_rows == 0

    db.close()
