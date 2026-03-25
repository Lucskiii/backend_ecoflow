from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories.raw_ingestion_repository import RawIngestionRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GeocodeResult:
    latitude: Decimal
    longitude: Decimal


class GeocodingService:
    def __init__(self, db: Session | None = None) -> None:
        self.settings = get_settings()
        self._session = requests.Session()
        self.raw_ingestion_repository = RawIngestionRepository(db) if db is not None else None

    def geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        query = ", ".join([address_line1, postal_code, city, country])
        params = {
            "name": query,
            "count": 1,
            "language": "en",
            "format": "json",
        }
        try:
            response = self._session.get(
                self.settings.open_meteo_geocoding_url,
                params=params,
                timeout=self.settings.open_meteo_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"Geocoding request failed: {exc}") from exc
        payload = response.json()
        if self.raw_ingestion_repository is not None:
            self.raw_ingestion_repository.record_api_call(
                source_system="open-meteo",
                source_topic="geocoding",
                source_uri=str(response.url),
                payload=payload,
                notes=f"geocode query={query}",
                entity_hint="customer_address",
            )
        results = payload.get("results") or []
        if not results:
            raise ValueError(f"No geocoding result for address: {query}")

        first = results[0]
        if first.get("latitude") is None or first.get("longitude") is None:
            raise ValueError(f"Incomplete geocoding result for address: {query}")

        latitude = Decimal(str(first["latitude"])).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        longitude = Decimal(str(first["longitude"])).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        logger.info("Resolved geocoding query=%s latitude=%s longitude=%s", query, latitude, longitude)
        return GeocodeResult(latitude=latitude, longitude=longitude)
