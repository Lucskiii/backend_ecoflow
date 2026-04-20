from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient
from decimal import Decimal
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.tables import (
    CoreBiddingZone,
    CoreCustomerRevenuePeriod,
    CoreMarket,
    CoreMarketProduct,
    CoreMeter,
    CoreTsMarketPrice,
    CoreTsMeterReading,
    Site,
)
from app.services.geocoding_service import GeocodeResult, GeocodingService
from app.services.energy_service import EnergyService


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_register_login_and_me() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_geocode = GeocodingService.geocode_address
    original_backfill = EnergyService.backfill_customer_data_to_now

    def _fake_geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        return GeocodeResult(latitude=Decimal("48.208200"), longitude=Decimal("16.373800"))

    GeocodingService.geocode_address = _fake_geocode_address
    EnergyService.backfill_customer_data_to_now = lambda self, customer, days=None: None  # type: ignore[method-assign]
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Max Mustermann",
            "email": "max@example.com",
            "password": "secret123",
            "address_line1": "Musterstrasse 1",
            "city": "Wien",
            "postal_code": "1010",
            "country": "Austria",
        },
    )
    assert register_response.status_code == 201
    register_json = register_response.json()
    assert register_json["customer"]["email"] == "max@example.com"
    assert "access_token" in register_json

    login_response = client.post("/api/auth/login", json={"email": "max@example.com", "password": "secret123"})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "max@example.com"
    assert Decimal(str(me_response.json()["umsatz_eur"])) == Decimal("0")

    customer_me_response = client.get("/api/customers/me", headers={"Authorization": f"Bearer {token}"})
    assert customer_me_response.status_code == 200
    customer_me_json = customer_me_response.json()
    assert customer_me_json["id"] == register_json["customer"]["id"]
    assert customer_me_json["name"] == "Max Mustermann"
    assert customer_me_json["email"] == "max@example.com"
    assert Decimal(str(customer_me_json["umsatz_eur"])) == Decimal("0")


    update_me_response = client.put(
        "/api/customers/me",
        json={"name": "Max Mustermann Neu", "email": "max.neu@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_me_response.status_code == 200
    update_me_json = update_me_response.json()
    assert update_me_json["id"] == register_json["customer"]["id"]
    assert update_me_json["name"] == "Max Mustermann Neu"
    assert update_me_json["email"] == "max.neu@example.com"

    second_customer_response = client.post(
        "/api/auth/register",
        json={
            "name": "Erika Musterfrau",
            "email": "erika@example.com",
            "password": "secret123",
            "address_line1": "Ring 2",
            "city": "Wien",
            "postal_code": "1010",
            "country": "Austria",
        },
    )
    assert second_customer_response.status_code == 201

    email_conflict_response = client.put(
        "/api/customers/me",
        json={"email": "erika@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert email_conflict_response.status_code == 409

    invalid_payload_response = client.put(
        "/api/customers/me",
        json={"name": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid_payload_response.status_code == 422

    unauthorized_update_response = client.put("/api/customers/me", json={"name": "Unauthed"})
    assert unauthorized_update_response.status_code == 401
    unauthorized_me_response = client.get("/api/customers/me")
    assert unauthorized_me_response.status_code == 401

    GeocodingService.geocode_address = original_geocode
    EnergyService.backfill_customer_data_to_now = original_backfill
    app.dependency_overrides.clear()


def test_customer_revenue_periods_endpoint_persists_snapshots() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_geocode = GeocodingService.geocode_address
    original_backfill = EnergyService.backfill_customer_data_to_now

    def _fake_geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        return GeocodeResult(latitude=Decimal("48.208200"), longitude=Decimal("16.373800"))

    GeocodingService.geocode_address = _fake_geocode_address
    EnergyService.backfill_customer_data_to_now = lambda self, customer, days=None: None  # type: ignore[method-assign]
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Perioden Kunde",
            "email": "perioden@example.com",
            "password": "secret123",
            "address_line1": "Musterstrasse 1",
            "city": "Wien",
            "postal_code": "1010",
            "country": "Austria",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]
    customer_id = register_response.json()["customer"]["id"]

    db = testing_session_local()
    try:
        site = db.scalar(db.query(Site).where(Site.customer_id == customer_id).statement)
        assert site is not None

        meter_id = int(db.scalar(select(func.coalesce(func.max(CoreMeter.id), 0) + 1)) or 1)
        db.add(
            CoreMeter(
                id=meter_id,
                site_id=site.id,
                meter_code=f"site-{site.id}-grid-export-periods",
                meter_role="grid_export",
                unit="kWh",
            )
        )

        market_id = int(db.scalar(select(func.coalesce(func.max(CoreMarket.id), 0) + 1)) or 1)
        bidding_zone_id = int(db.scalar(select(func.coalesce(func.max(CoreBiddingZone.id), 0) + 1)) or 1)
        product_id = int(db.scalar(select(func.coalesce(func.max(CoreMarketProduct.id), 0) + 1)) or 1)

        db.add_all(
            [
                CoreMarket(id=market_id, code="AWATTAR", name="aWATTar"),
                CoreBiddingZone(id=bidding_zone_id, code="DE", name="Germany"),
                CoreMarketProduct(
                    id=product_id,
                    market_id=market_id,
                    product_code="DE_DAY_AHEAD",
                    granularity_minutes=60,
                    direction=None,
                ),
            ]
        )
        db.flush()

        now = datetime.now(timezone.utc).replace(minute=15, second=0, microsecond=0)
        db.add_all(
            [
                CoreTsMeterReading(meter_id=meter_id, ts=now - timedelta(days=5), interval_seconds=900, value=Decimal("10.0")),
                CoreTsMeterReading(meter_id=meter_id, ts=now - timedelta(days=20), interval_seconds=900, value=Decimal("10.0")),
                CoreTsMeterReading(meter_id=meter_id, ts=now - timedelta(days=45), interval_seconds=900, value=Decimal("10.0")),
            ]
        )
        db.add_all(
            [
                CoreTsMarketPrice(
                    market_product_id=product_id,
                    bidding_zone_id=bidding_zone_id,
                    ts=(now - timedelta(days=5)).replace(minute=0),
                    price=Decimal("100.0"),
                    currency="EUR",
                ),
                CoreTsMarketPrice(
                    market_product_id=product_id,
                    bidding_zone_id=bidding_zone_id,
                    ts=(now - timedelta(days=20)).replace(minute=0),
                    price=Decimal("100.0"),
                    currency="EUR",
                ),
                CoreTsMarketPrice(
                    market_product_id=product_id,
                    bidding_zone_id=bidding_zone_id,
                    ts=(now - timedelta(days=45)).replace(minute=0),
                    price=Decimal("100.0"),
                    currency="EUR",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/customers/me/revenue/periods", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["customer_id"] == customer_id

    by_period = {entry["period"]: Decimal(str(entry["umsatz_eur"])) for entry in payload["periods"]}
    assert by_period["7d"] == Decimal("1.000000")
    assert by_period["30d"] == Decimal("2.000000")
    assert by_period["all"] == Decimal("3.000000")

    repeat_response = client.get("/api/customers/me/revenue/periods", headers={"Authorization": f"Bearer {token}"})
    assert repeat_response.status_code == 200

    db = testing_session_local()
    try:
        rows = list(
            db.query(CoreCustomerRevenuePeriod)
            .filter(CoreCustomerRevenuePeriod.customer_id == customer_id)
            .order_by(CoreCustomerRevenuePeriod.period_code.asc())
        )
        assert len(rows) == 3
        assert {row.period_code for row in rows} == {"all", "30d", "7d"}
    finally:
        db.close()

    GeocodingService.geocode_address = original_geocode
    EnergyService.backfill_customer_data_to_now = original_backfill
    app.dependency_overrides.clear()


def test_customer_umsatz_is_calculated_from_export_and_market_price() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_geocode = GeocodingService.geocode_address
    original_backfill = EnergyService.backfill_customer_data_to_now

    def _fake_geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        return GeocodeResult(latitude=Decimal("48.208200"), longitude=Decimal("16.373800"))

    GeocodingService.geocode_address = _fake_geocode_address
    EnergyService.backfill_customer_data_to_now = lambda self, customer, days=None: None  # type: ignore[method-assign]
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Umsatz Kunde",
            "email": "umsatz@example.com",
            "password": "secret123",
            "address_line1": "Musterstrasse 1",
            "city": "Wien",
            "postal_code": "1010",
            "country": "Austria",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]
    customer_id = register_response.json()["customer"]["id"]

    db = testing_session_local()
    try:
        site = db.scalar(db.query(Site).where(Site.customer_id == customer_id).statement)
        assert site is not None

        meter_id = int(db.scalar(select(func.coalesce(func.max(CoreMeter.id), 0) + 1)) or 1)
        meter = CoreMeter(
            id=meter_id,
            site_id=site.id,
            meter_code=f"site-{site.id}-grid-export-test",
            meter_role="grid_export",
            unit="kWh",
        )
        db.add(meter)

        market_id = int(db.scalar(select(func.coalesce(func.max(CoreMarket.id), 0) + 1)) or 1)
        bidding_zone_id = int(db.scalar(select(func.coalesce(func.max(CoreBiddingZone.id), 0) + 1)) or 1)

        market = CoreMarket(id=market_id, code="AWATTAR", name="aWATTar")
        bidding_zone = CoreBiddingZone(id=bidding_zone_id, code="DE", name="Germany")
        db.add_all([market, bidding_zone])
        db.flush()

        product_id = int(db.scalar(select(func.coalesce(func.max(CoreMarketProduct.id), 0) + 1)) or 1)
        product = CoreMarketProduct(
            id=product_id,
            market_id=market.id,
            product_code="DE_DAY_AHEAD",
            granularity_minutes=60,
            direction=None,
        )
        db.add(product)
        db.flush()

        reading_ts = datetime(2026, 1, 1, 10, 15, tzinfo=timezone.utc)
        db.add(
            CoreTsMeterReading(
                meter_id=meter.id,
                ts=reading_ts,
                interval_seconds=900,
                value=Decimal("10.0"),
            )
        )
        db.add(
            CoreTsMarketPrice(
                market_product_id=product.id,
                bidding_zone_id=bidding_zone.id,
                ts=datetime(2026, 1, 1, 10, 0),
                price=Decimal("100.0"),
                currency="EUR",
            )
        )
        db.commit()
    finally:
        db.close()

    me_response = client.get("/api/customers/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert Decimal(str(me_response.json()["umsatz_eur"])) == Decimal("1.000000")

    GeocodingService.geocode_address = original_geocode
    EnergyService.backfill_customer_data_to_now = original_backfill
    app.dependency_overrides.clear()


def test_customer_umsatz_uses_only_awattar_de_day_ahead_series() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_geocode = GeocodingService.geocode_address
    original_backfill = EnergyService.backfill_customer_data_to_now

    def _fake_geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        return GeocodeResult(latitude=Decimal("48.208200"), longitude=Decimal("16.373800"))

    GeocodingService.geocode_address = _fake_geocode_address
    EnergyService.backfill_customer_data_to_now = lambda self, customer, days=None: None  # type: ignore[method-assign]
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={
            "name": "Serie Kunde",
            "email": "series@example.com",
            "password": "secret123",
            "address_line1": "Musterstrasse 1",
            "city": "Wien",
            "postal_code": "1010",
            "country": "Austria",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]
    customer_id = register_response.json()["customer"]["id"]

    db = testing_session_local()
    try:
        site = db.scalar(db.query(Site).where(Site.customer_id == customer_id).statement)
        assert site is not None

        meter_id = int(db.scalar(select(func.coalesce(func.max(CoreMeter.id), 0) + 1)) or 1)
        db.add(
            CoreMeter(
                id=meter_id,
                site_id=site.id,
                meter_code=f"site-{site.id}-grid-export-series-test",
                meter_role="grid_export",
                unit="kWh",
            )
        )

        market_id = int(db.scalar(select(func.coalesce(func.max(CoreMarket.id), 0) + 1)) or 1)
        bidding_zone_id = int(db.scalar(select(func.coalesce(func.max(CoreBiddingZone.id), 0) + 1)) or 1)
        other_bidding_zone_id = bidding_zone_id + 1

        db.add_all(
            [
                CoreMarket(id=market_id, code="AWATTAR", name="aWATTar"),
                CoreBiddingZone(id=bidding_zone_id, code="DE", name="Germany"),
                CoreBiddingZone(id=other_bidding_zone_id, code="AT", name="Austria"),
            ]
        )
        db.flush()

        product_id = int(db.scalar(select(func.coalesce(func.max(CoreMarketProduct.id), 0) + 1)) or 1)
        other_product_id = product_id + 1
        db.add_all(
            [
                CoreMarketProduct(
                    id=product_id,
                    market_id=market_id,
                    product_code="DE_DAY_AHEAD",
                    granularity_minutes=60,
                    direction=None,
                ),
                CoreMarketProduct(
                    id=other_product_id,
                    market_id=market_id,
                    product_code="AT_DAY_AHEAD",
                    granularity_minutes=60,
                    direction=None,
                ),
            ]
        )
        db.flush()

        reading_ts = datetime(2026, 1, 1, 10, 15, tzinfo=timezone.utc)
        db.add(
            CoreTsMeterReading(
                meter_id=meter_id,
                ts=reading_ts,
                interval_seconds=900,
                value=Decimal("10.0"),
            )
        )

        # Correct series for revenue calculation (expected 10 * 100 / 1000 = 1 EUR).
        db.add(
            CoreTsMarketPrice(
                market_product_id=product_id,
                bidding_zone_id=bidding_zone_id,
                ts=datetime(2026, 1, 1, 10, 0),
                price=Decimal("100.0"),
                currency="EUR",
            )
        )
        # Conflicting same-hour series that must be ignored.
        db.add(
            CoreTsMarketPrice(
                market_product_id=other_product_id,
                bidding_zone_id=other_bidding_zone_id,
                ts=datetime(2026, 1, 1, 10, 0),
                price=Decimal("900.0"),
                currency="EUR",
            )
        )
        db.commit()
    finally:
        db.close()

    me_response = client.get("/api/customers/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert Decimal(str(me_response.json()["umsatz_eur"])) == Decimal("1.000000")

    GeocodingService.geocode_address = original_geocode
    EnergyService.backfill_customer_data_to_now = original_backfill
    app.dependency_overrides.clear()
