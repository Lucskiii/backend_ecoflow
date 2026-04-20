from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.tables import (
    Asset,
    CoreBiddingZone,
    CoreMarket,
    CoreMarketProduct,
    CoreMeter,
    CoreTsMarketPrice,
    CoreTsMeterReading,
    Customer,
    Site,
)


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_bi_prototype_sync_and_trends() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = testing_session_local()
    try:
        customer = Customer(id=1, name="BI Customer", email="bi@example.com")
        db.add(customer)
        db.flush()

        site = Site(
            id=1,
            customer_id=customer.id,
            site_code="bi-site-1",
            name="BI Site 1",
            timezone="UTC",
            latitude=48.2,
            longitude=16.3,
        )
        db.add(site)
        db.flush()

        asset = Asset(id=1, site_id=site.id, asset_code="asset-1", name="Battery 1", asset_type="battery")
        db.add(asset)

        meter = CoreMeter(id=1, site_id=site.id, asset_id=asset.id, meter_code="bi-meter-1", meter_role="load", unit="kWh")
        db.add(meter)

        market = CoreMarket(id=1, code="EPEX", name="EPEX Spot")
        db.add(market)
        db.flush()

        product = CoreMarketProduct(id=1, market_id=market.id, product_code="DA", granularity_minutes=60)
        db.add(product)
        product_id = product.id

        bidding_zone = CoreBiddingZone(id=1, code="DE", name="Germany")
        db.add(bidding_zone)
        db.flush()
        bidding_zone_id = bidding_zone.id

        ts0_aware = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
        ts1_aware = ts0_aware + timedelta(hours=1)
        ts0 = ts0_aware.replace(tzinfo=None)
        ts1 = ts1_aware.replace(tzinfo=None)

        db.add_all(
            [
                CoreTsMeterReading(meter_id=meter.id, ts=ts0, interval_seconds=3600, value=10),
                CoreTsMeterReading(meter_id=meter.id, ts=ts1, interval_seconds=3600, value=12),
            ]
        )
        db.add_all(
            [
                CoreTsMarketPrice(market_product_id=product.id, bidding_zone_id=bidding_zone.id, ts=ts0, price=100),
                CoreTsMarketPrice(market_product_id=product.id, bidding_zone_id=bidding_zone.id, ts=ts1, price=110),
            ]
        )
        db.commit()
    finally:
        db.close()

    from_iso = ts0_aware.isoformat()
    to_iso = (ts1_aware + timedelta(hours=1)).isoformat()

    sync_response = client.post("/api/bi/prototype/sync", params={"from": from_iso, "to": to_iso})
    assert sync_response.status_code == 200
    sync_payload = sync_response.json()
    assert sync_payload["inserted_or_updated_dim_customer"] >= 1
    assert sync_payload["inserted_or_updated_fact_energy_interval"] >= 2
    assert sync_payload["inserted_or_updated_fact_market_price"] >= 2

    energy_response = client.get("/api/bi/prototype/energy-trend", params={"from": from_iso, "to": to_iso})
    assert energy_response.status_code == 200
    energy_points = energy_response.json()["points"]
    assert len(energy_points) == 2
    assert float(energy_points[0]["value"]) == 10.0

    price_response = client.get(
        "/api/bi/prototype/price-trend",
        params={
            "from": from_iso,
            "to": to_iso,
            "market_product_key": product_id,
            "bidding_zone_id": bidding_zone_id,
        },
    )
    assert price_response.status_code == 200
    price_points = price_response.json()["points"]
    assert len(price_points) == 2
    assert float(price_points[1]["value"]) == 110.0

    app.dependency_overrides.clear()
