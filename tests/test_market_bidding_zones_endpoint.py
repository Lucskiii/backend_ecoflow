from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.tables import CoreBiddingZone


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_list_market_bidding_zones_returns_ids_names_and_codes() -> None:
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
        db.add_all(
            [
                CoreBiddingZone(id=2, code="AT", name="Austria"),
                CoreBiddingZone(id=1, code="DE", name="Germany"),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/market/bidding-zones")
    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["items"]] == ["Austria", "Germany"]
    assert payload["items"][0]["id"] == 2
    assert payload["items"][0]["code"] == "AT"

    app.dependency_overrides.clear()
