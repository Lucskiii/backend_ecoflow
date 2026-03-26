from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.config import get_settings


class OpenMeteoGeocodingError(Exception):
    pass


class OpenMeteoGeocodingUnavailableError(OpenMeteoGeocodingError):
    pass


class OpenMeteoGeocodingNoResultsError(OpenMeteoGeocodingError):
    pass


class OpenMeteoGeocodingPayloadError(OpenMeteoGeocodingError):
    pass


@dataclass(slots=True)
class OpenMeteoGeocodingResult:
    location_id: int | None
    name: str
    latitude: float
    longitude: float
    country_code: str | None
    country: str | None
    admin1: str | None
    timezone: str | None


class OpenMeteoGeocodingClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._session = requests.Session()

    def search_city(self, city_name: str, country_code: str | None = None) -> OpenMeteoGeocodingResult:
        params: dict[str, Any] = {
            "name": city_name,
            "count": 1,
            "language": "en",
            "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code.upper()

        try:
            response = self._session.get(
                self.settings.open_meteo_geocoding_url,
                params=params,
                timeout=self.settings.open_meteo_timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise OpenMeteoGeocodingUnavailableError("Geocoding service temporarily unavailable.") from exc
        except requests.RequestException as exc:
            raise OpenMeteoGeocodingUnavailableError("Geocoding service temporarily unavailable.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenMeteoGeocodingPayloadError("Invalid response from geocoding service.") from exc

        if not isinstance(payload, dict):
            raise OpenMeteoGeocodingPayloadError("Invalid response from geocoding service.")

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise OpenMeteoGeocodingNoResultsError("Die eingegebene Stadt wurde im Open-Meteo-Geocoding nicht gefunden.")

        first = results[0]
        if not isinstance(first, dict):
            raise OpenMeteoGeocodingPayloadError("Invalid response from geocoding service.")

        try:
            latitude = float(first["latitude"])
            longitude = float(first["longitude"])
            name = str(first["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenMeteoGeocodingPayloadError("Invalid response from geocoding service.") from exc

        raw_id = first.get("id")
        location_id = int(raw_id) if isinstance(raw_id, (int, float, str)) and str(raw_id).isdigit() else None

        return OpenMeteoGeocodingResult(
            location_id=location_id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            country_code=first.get("country_code"),
            country=first.get("country"),
            admin1=first.get("admin1"),
            timezone=first.get("timezone"),
        )
