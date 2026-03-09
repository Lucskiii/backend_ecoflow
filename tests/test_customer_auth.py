from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
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
    client = TestClient(app)

    register_response = client.post(
        "/api/auth/register",
        json={"name": "Max Mustermann", "email": "max@example.com", "password": "secret123"},
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

    app.dependency_overrides.clear()
