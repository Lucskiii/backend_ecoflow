from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.repositories.site_repository import SiteRepository
from app.services.geocoding_service import GeocodingService

logger = logging.getLogger(__name__)


class CustomerSiteCoordinateService:
    def __init__(self, db: Session, geocoding_service: GeocodingService | None = None) -> None:
        self.db = db
        self.geocoding_service = geocoding_service or GeocodingService(db)
        self.site_repository = SiteRepository(db)

    def backfill_missing_site_coordinates(self) -> dict[str, int]:
        sites = self.site_repository.list_sites_without_coordinates()
        customers_geocoded: set[int] = set()
        sites_updated = 0

        for site in sites:
            try:
                geocode = self.geocoding_service.geocode_site(site.id, force=False)
            except Exception as exc:
                logger.warning("Failed to geocode site id=%s: %s", site.id, exc)
                continue
            if geocode.latitude is not None and geocode.longitude is not None:
                self.site_repository.update_site_coordinates(site.id, geocode.latitude, geocode.longitude)
                sites_updated += 1
                customers_geocoded.add(site.customer_id)

        self.db.commit()
        result = {"customers_geocoded": len(customers_geocoded), "sites_updated": sites_updated}
        logger.info(
            "Customer/site coordinate backfill complete customers_geocoded=%s sites_updated=%s",
            result["customers_geocoded"],
            result["sites_updated"],
        )
        return result
