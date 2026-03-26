from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis_city import CoreAnalysisCity


class AnalysisCityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_city_and_country(self, city_name: str, country_code: str | None) -> CoreAnalysisCity | None:
        normalized_city = city_name.strip()
        normalized_country = country_code.strip().upper() if country_code else None
        return self.db.scalar(
            select(CoreAnalysisCity).where(
                func.lower(CoreAnalysisCity.city_name) == normalized_city.lower(),
                CoreAnalysisCity.country_code == normalized_country,
            )
        )

    def create_analysis_city(
        self,
        *,
        city_name: str,
        country_code: str | None,
        country_name: str | None,
        latitude: float,
        longitude: float,
        open_meteo_location_id: int | None,
        admin1: str | None,
        timezone: str | None,
    ) -> CoreAnalysisCity:
        city = CoreAnalysisCity(
            city_name=city_name.strip(),
            country_code=country_code.strip().upper() if country_code else None,
            country_name=country_name,
            latitude=latitude,
            longitude=longitude,
            open_meteo_location_id=open_meteo_location_id,
            admin1=admin1,
            timezone=timezone,
        )
        self.db.add(city)
        self.db.commit()
        self.db.refresh(city)
        return city

    def list_analysis_cities(self) -> list[CoreAnalysisCity]:
        return list(self.db.scalars(select(CoreAnalysisCity).order_by(CoreAnalysisCity.city_name.asc())))

    def get_analysis_city_by_id(self, city_id: int) -> CoreAnalysisCity | None:
        return self.db.get(CoreAnalysisCity, city_id)

    def delete_analysis_city(self, city: CoreAnalysisCity) -> None:
        self.db.delete(city)
        self.db.commit()
