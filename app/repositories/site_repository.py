from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Site


class SiteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_site_by_id(self, site_id: int) -> Site | None:
        return self.db.scalar(select(Site).where(Site.id == site_id))

    def list_sites_without_coordinates(self) -> list[Site]:
        stmt = select(Site).where(Site.latitude.is_(None), Site.longitude.is_(None))
        return list(self.db.scalars(stmt))

    def list_all_sites(self) -> list[Site]:
        return list(self.db.scalars(select(Site)))

    def update_site_coordinates(self, site_id: int, lat: Decimal, lon: Decimal) -> Site | None:
        site = self.get_site_by_id(site_id)
        if site is None:
            return None
        site.latitude = lat
        site.longitude = lon
        self.db.flush()
        return site
