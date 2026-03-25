from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient
from decimal import Decimal
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
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

    customer_me_response = client.get("/api/customers/me", headers={"Authorization": f"Bearer {token}"})
    assert customer_me_response.status_code == 200
    customer_me_json = customer_me_response.json()
    assert customer_me_json["id"] == register_json["customer"]["id"]
    assert customer_me_json["name"] == "Max Mustermann"
    assert customer_me_json["email"] == "max@example.com"


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
