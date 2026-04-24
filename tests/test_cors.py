from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


DEFAULT_ORIGIN = "http://localhost:4200"


def test_cors_preflight_allows_configured_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": DEFAULT_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEFAULT_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-methods"] == "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    allow_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


def test_cors_denies_unknown_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://evil.local",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_applies_to_api_routes_for_vercel_frontend_origin() -> None:
    client = TestClient(app)

    response = client.get(
        "/api/customers/me",
        headers={"Origin": "https://frontend-ecoflow.vercel.app"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://frontend-ecoflow.vercel.app"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_allows_custom_headers() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/analysis-cities",
        headers={
            "Origin": "https://frontend-ecoflow.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type,X-Requested-With",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend-ecoflow.vercel.app"

def test_cors_origin_parser_normalizes_and_deduplicates() -> None:
    settings = Settings(
        CORS_ALLOWED_ORIGINS=(
            "http://localhost:4200,https://frontend-ecoflow.vercel.app/login,"
            "https://frontend-ecoflow.vercel.app/"
        )
    )

    assert settings.get_cors_allowed_origins() == [
        "http://localhost:4200",
        "https://frontend-ecoflow.vercel.app",
    ]
