from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.tables import CoreMeter, CoreTsMeterReading, Site


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def _register_and_login(client: TestClient, name: str, email: str) -> str:
    register_response = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": "secret123"},
    )
    assert register_response.status_code == 201

    login_response = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def test_energy_simulation_and_customer_scoped_queries() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    token_a = _register_and_login(client, "Customer A", "a@example.com")
    token_b = _register_and_login(client, "Customer B", "b@example.com")

    simulate_a = client.post("/api/customers/me/energy/simulate", headers={"Authorization": f"Bearer {token_a}"})
    assert simulate_a.status_code == 200
    assert simulate_a.json()["readings_created"] > 0

    summary_a = client.get("/api/customers/me/energy/summary?period=7d", headers={"Authorization": f"Bearer {token_a}"})
    assert summary_a.status_code == 200
    payload_a = summary_a.json()
    assert payload_a["load_kwh"] > 0
    assert payload_a["grid_import_kwh"] >= 0

    summary_b = client.get("/api/customers/me/energy/summary?period=7d", headers={"Authorization": f"Bearer {token_b}"})
    assert summary_b.status_code == 200
    payload_b = summary_b.json()
    assert payload_b["load_kwh"] == 0
    assert payload_b["pv_generation_kwh"] == 0

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=6)).isoformat()
    until = now.isoformat()
    timeseries = client.get(
        f"/api/customers/me/energy/timeseries?from={since}&to={until}&interval=15m",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert timeseries.status_code == 200
    series = timeseries.json()["series"]
    assert len(series) == 4
    assert any(item["meter_type"] == "load" and len(item["points"]) > 0 for item in series)

    invalid_interval = client.get(
        "/api/customers/me/energy/timeseries?interval=1h",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert invalid_interval.status_code == 400

    app.dependency_overrides.clear()


def test_timeseries_handles_non_modeled_meter_roles() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    token = _register_and_login(client, "Customer Extra Role", "extra-role@example.com")
    simulate = client.post("/api/customers/me/energy/simulate", headers={"Authorization": f"Bearer {token}"})
    assert simulate.status_code == 200

    db = testing_session_local()
    try:
        site = db.query(Site).first()
        assert site is not None

        meter = CoreMeter(site_id=site.id, meter_code="meter-battery-charge", meter_role="battery_charge", unit="kWh")
        db.add(meter)
        db.flush()

        db.add(
            CoreTsMeterReading(
                meter_id=meter.id,
                ts=datetime.now(timezone.utc) - timedelta(minutes=15),
                interval_seconds=900,
                value=1.25,
            )
        )
        db.commit()
    finally:
        db.close()

    now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=6)).isoformat()
    until = now.isoformat()
    timeseries = client.get(
        f"/api/customers/me/energy/timeseries?from={since}&to={until}&interval=15m",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert timeseries.status_code == 200
    series = timeseries.json()["series"]
    assert any(item["meter_type"] == "battery_charge" for item in series)

    app.dependency_overrides.clear()

def test_timeseries_rejects_naive_datetime_inputs() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    token = _register_and_login(client, "Customer Naive", "naive@example.com")

    response = client.get(
        "/api/customers/me/energy/timeseries?from=2026-01-01T00:00:00",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "from must include timezone information"

    app.dependency_overrides.clear()


def test_login_backfills_missing_energy_intervals() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={"name": "Customer Backfill", "email": "backfill@example.com", "password": "secret123"},
    )
    assert register_response.status_code == 201

    first_login = client.post("/api/auth/login", json={"email": "backfill@example.com", "password": "secret123"})
    assert first_login.status_code == 200

    db = testing_session_local()
    try:
        latest_ts = db.query(CoreTsMeterReading.ts).order_by(CoreTsMeterReading.ts.desc()).first()
        assert latest_ts is not None
        cutoff_ts = latest_ts[0] - timedelta(minutes=45)

        db.query(CoreTsMeterReading).filter(CoreTsMeterReading.ts > cutoff_ts).delete(synchronize_session=False)
        db.commit()

        remaining_latest = db.query(CoreTsMeterReading.ts).order_by(CoreTsMeterReading.ts.desc()).first()
        assert remaining_latest is not None
        assert remaining_latest[0] == cutoff_ts
    finally:
        db.close()

    second_login = client.post("/api/auth/login", json={"email": "backfill@example.com", "password": "secret123"})
    assert second_login.status_code == 200

    db = testing_session_local()
    try:
        latest_after_backfill = db.query(CoreTsMeterReading.ts).order_by(CoreTsMeterReading.ts.desc()).first()
        assert latest_after_backfill is not None
        assert latest_after_backfill[0] > cutoff_ts

        role_count = db.query(CoreMeter.meter_role).distinct().count()
        repaired_count = db.query(CoreTsMeterReading).filter(CoreTsMeterReading.ts > cutoff_ts).count()
        assert role_count == 4
        assert repaired_count >= 4 * 3
    finally:
        db.close()

    app.dependency_overrides.clear()
