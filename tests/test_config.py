from app.config import Settings


def test_cors_allow_origins_accepts_single_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:4200")

    settings = Settings()

    assert settings.cors_allow_origins == ["http://localhost:4200"]


def test_cors_allow_origins_accepts_comma_separated_origins(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", "http://localhost:4200, http://127.0.0.1:4200"
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]


def test_cors_allow_origins_accepts_json_list(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", '["http://localhost:4200", "http://127.0.0.1:4200"]'
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]
