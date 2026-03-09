from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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


def test_portfolio_summary_and_timeseries() -> None:
    testing_session_local = _setup_test_db()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    token_a = _register_and_login(client, "Portfolio A", "portfolio-a@example.com")
    token_b = _register_and_login(client, "Portfolio B", "portfolio-b@example.com")

    assert client.post("/api/customers/me/energy/simulate", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200
    assert client.post("/api/customers/me/energy/simulate", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200

    summary = client.get("/api/portfolio/export/summary?period=7d")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["period"] == "7d"
    assert payload["total_grid_export_kwh"] > 0
    assert payload["tradable_export_kwh"] == payload["total_grid_export_kwh"] * 0.9
    assert payload["customer_count"] == 2
    assert payload["site_count"] >= 2
    assert payload["interval_minutes"] == 15
    assert payload["safety_factor"] == 0.9

    now = datetime.now(timezone.utc)
    from_ts = (now - timedelta(hours=6)).isoformat()
    to_ts = now.isoformat()

    timeseries = client.get(f"/api/portfolio/export/timeseries?from={from_ts}&to={to_ts}&interval=15m")
    assert timeseries.status_code == 200
    ts_payload = timeseries.json()
    assert ts_payload["interval_minutes"] == 15
    assert len(ts_payload["series"]) == 2

    export_series = next(item for item in ts_payload["series"] if item["name"] == "portfolio_grid_export")
    tradable_series = next(item for item in ts_payload["series"] if item["name"] == "portfolio_tradable_export")

    assert len(export_series["points"]) > 0
    assert len(export_series["points"]) == len(tradable_series["points"])
    for export_point, tradable_point in zip(export_series["points"], tradable_series["points"], strict=True):
        assert tradable_point["value"] == export_point["value"] * 0.9

    invalid_interval = client.get("/api/portfolio/export/timeseries?interval=1h")
    assert invalid_interval.status_code == 400

    app.dependency_overrides.clear()
