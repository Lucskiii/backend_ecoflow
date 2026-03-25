from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.site import Site
from app.services.geocoding_service import GeocodingService

logger = logging.getLogger(__name__)


class CustomerSiteCoordinateService:
    def __init__(self, db: Session, geocoding_service: GeocodingService | None = None) -> None:
        self.db = db
        self.geocoding_service = geocoding_service or GeocodingService()

    def backfill_missing_site_coordinates(self) -> dict[str, int]:
        customers = list(
            self.db.scalars(
                select(Customer).where(
                    Customer.address_line1.is_not(None),
                    Customer.city.is_not(None),
                    Customer.postal_code.is_not(None),
                    Customer.country.is_not(None),
                )
            )
        )

        customers_geocoded = 0
        sites_updated = 0

        for customer in customers:
            try:
                geocode = self.geocoding_service.geocode_address(
                    address_line1=customer.address_line1 or "",
                    city=customer.city or "",
                    postal_code=customer.postal_code or "",
                    country=customer.country or "",
                )
            except Exception as exc:
                logger.warning("Failed to geocode customer id=%s: %s", customer.id, exc)
                continue
            customers_geocoded += 1

            sites = list(
                self.db.scalars(
                    select(Site).where(
                        Site.customer_id == customer.id,
                        Site.latitude.is_(None),
                        Site.longitude.is_(None),
                    )
                )
            )
            for site in sites:
                site.latitude = geocode.latitude
                site.longitude = geocode.longitude
                sites_updated += 1

        self.db.commit()
        logger.info(
            "Customer/site coordinate backfill complete customers_geocoded=%s sites_updated=%s",
            customers_geocoded,
            sites_updated,
        )
        return {"customers_geocoded": customers_geocoded, "sites_updated": sites_updated}
