from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.clients.opencage_client import OpenCageClient, OpenCageClientError
from app.models.tables import Customer
from app.repositories.raw_ingestion_repository import RawIngestionRepository
from app.repositories.site_repository import SiteRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GeocodeResult:
    latitude: Decimal
    longitude: Decimal


class GeocodingService:
    def __init__(self, db: Session | None = None, client: OpenCageClient | None = None) -> None:
        self.db = db
        self.client = client or OpenCageClient()
        self.raw_ingestion_repository = RawIngestionRepository(db) if db is not None else None
        self.site_repository = SiteRepository(db) if db is not None else None

    def geocode_address(self, *, address_line1: str, city: str, postal_code: str, country: str) -> GeocodeResult:
        queries = self._build_address_candidates(
            address_line1=address_line1,
            city=city,
            postal_code=postal_code,
            country=country,
        )
        if not queries:
            raise ValueError("Address is incomplete and cannot be geocoded")

        last_error: Exception | None = None
        for query in queries:
            try:
                lat, lon = self.client.geocode_address(query)
                if self.raw_ingestion_repository is not None:
                    self.raw_ingestion_repository.record_api_call(
                        source_system="opencage",
                        source_topic="geocoding",
                        source_uri=getattr(getattr(self.client, "settings", None), "opencage_geocoding_url", "opencage"),
                        payload={"query": query, "latitude": lat, "longitude": lon},
                        notes=f"geocode query={query}",
                        entity_hint="customer_address",
                    )
                return GeocodeResult(
                    latitude=Decimal(str(lat)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
                    longitude=Decimal(str(lon)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
                )
            except OpenCageClientError as exc:
                last_error = exc
                logger.warning("Geocoding failed for query=%s: %s", query, exc)

        raise ValueError(f"No geocoding result for address variants: {queries}") from last_error

    def geocode_site(self, site_id: int, force: bool = False) -> GeocodeResult:
        if self.db is None or self.site_repository is None:
            raise ValueError("Database session is required for site geocoding")

        site = self.site_repository.get_site_by_id(site_id)
        if site is None:
            raise LookupError(f"Site {site_id} not found")

        if not force and site.latitude is not None and site.longitude is not None:
            return GeocodeResult(latitude=site.latitude, longitude=site.longitude)

        customer = self.db.get(Customer, site.customer_id)
        if customer is None:
            raise ValueError(f"Customer for site {site_id} not found")

        geocode = self.geocode_address(
            address_line1=customer.address_line1 or "",
            city=customer.city or "",
            postal_code=customer.postal_code or "",
            country=customer.country or "",
        )
        self.site_repository.update_site_coordinates(site.id, geocode.latitude, geocode.longitude)
        self.db.commit()
        logger.info("Geocoded site_id=%s latitude=%s longitude=%s", site.id, geocode.latitude, geocode.longitude)
        return geocode

    @staticmethod
    def _build_address_candidates(*, address_line1: str, city: str, postal_code: str, country: str) -> list[str]:
        def _join(parts: list[str]) -> str:
            return ", ".join([part.strip() for part in parts if part and part.strip()])

        candidates = [
            _join([address_line1, postal_code, city, country]),
            _join([address_line1, city, country]),
            _join([postal_code, city, country]),
            _join([city, country]),
        ]

        deduplicated: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in deduplicated:
                deduplicated.append(candidate)
        return deduplicated
