from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OpenMeteoHourlyPoint:
    ts_utc: datetime
    temp_c: Decimal | None
    wind_ms: Decimal | None
    ghi_wm2: Decimal | None
    cloud_pct: Decimal | None


@dataclass(slots=True)
class OpenMeteoResult:
    source_url: str
    model_name: str | None
    points: list[OpenMeteoHourlyPoint]
    raw_payload: dict[str, Any]


class OpenMeteoClient:
    HOURLY_VARIABLES = [
        "temperature_2m",
        "wind_speed_10m",
        "cloud_cover",
        "shortwave_radiation",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()
        self._session = requests.Session()

    def fetch_historical_hourly(
        self, latitude: Decimal | float, longitude: Decimal | float, start_date: date, end_date: date
    ) -> OpenMeteoResult:
        params = self._build_params(latitude, longitude, start_date, end_date)
        return self._request(self.settings.open_meteo_historical_url, params)

    def fetch_recent_hourly(
        self, latitude: Decimal | float, longitude: Decimal | float, start_date: date, end_date: date
    ) -> OpenMeteoResult:
        params = self._build_params(latitude, longitude, start_date, end_date)
        delta_days = max((end_date - start_date).days + 1, 1)
        params["past_days"] = delta_days
        return self._request(self.settings.open_meteo_forecast_url, params)

    def _build_params(
        self, latitude: Decimal | float, longitude: Decimal | float, start_date: date, end_date: date
    ) -> dict[str, Any]:
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "hourly": ",".join(self.HOURLY_VARIABLES),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": "UTC",
            "wind_speed_unit": "ms",
        }

    def _request(self, base_url: str, params: dict[str, Any]) -> OpenMeteoResult:
        try:
            response = self._session.get(base_url, params=params, timeout=self.settings.open_meteo_timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Open-Meteo request failed url=%s params=%s error=%s", base_url, params, exc)
            raise RuntimeError(f"Open-Meteo request failed: {exc}") from exc

        payload = response.json()
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        winds = hourly.get("wind_speed_10m") or []
        clouds = hourly.get("cloud_cover") or []
        radiation = hourly.get("shortwave_radiation") or []

        points: list[OpenMeteoHourlyPoint] = []
        for idx, ts_text in enumerate(times):
            try:
                ts_utc = datetime.fromisoformat(ts_text)
            except ValueError:
                logger.warning("Skipping Open-Meteo timestamp=%s due to parse error", ts_text)
                continue
            if ts_utc.tzinfo is not None:
                ts_utc = ts_utc.astimezone(timezone.utc).replace(tzinfo=None)
            points.append(
                OpenMeteoHourlyPoint(
                    ts_utc=ts_utc,
                    temp_c=self._to_decimal(self._get_value(temperatures, idx)),
                    wind_ms=self._to_decimal(self._get_value(winds, idx)),
                    ghi_wm2=self._to_decimal(self._get_value(radiation, idx)),
                    cloud_pct=self._to_decimal(self._get_value(clouds, idx)),
                )
            )

        return OpenMeteoResult(
            source_url=response.url,
            model_name=payload.get("model") or payload.get("hourly_units", {}).get("temperature_2m"),
            points=points,
            raw_payload=payload,
        )

    @staticmethod
    def _get_value(values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
