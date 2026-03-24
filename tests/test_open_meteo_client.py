from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.clients.open_meteo_client import OpenMeteoClient


class DummyResponse:
    def __init__(self, payload: dict, url: str = "https://api.open-meteo.com/v1/forecast") -> None:
        self._payload = payload
        self.url = url

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class DummySession:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_params: dict | None = None

    def get(self, url, params, timeout):
        self.last_params = params
        return DummyResponse(self.payload, url=url)


def test_fetch_recent_hourly_uses_past_days_without_start_end() -> None:
    client = OpenMeteoClient()
    session = DummySession({"hourly": {"time": []}})
    client._session = session  # type: ignore[assignment]

    client.fetch_recent_hourly(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 1), date(2024, 1, 3))

    assert session.last_params is not None
    assert session.last_params["past_days"] == 3
    assert "start_date" not in session.last_params
    assert "end_date" not in session.last_params


def test_request_raises_runtime_error_for_error_payload() -> None:
    client = OpenMeteoClient()
    client._session = DummySession({"error": True, "reason": "Parameter conflict"})  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Parameter conflict"):
        client.fetch_recent_hourly(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 1), date(2024, 1, 2))
