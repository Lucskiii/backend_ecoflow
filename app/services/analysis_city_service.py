from __future__ import annotations

from sqlalchemy.orm import Session

from app.clients.open_meteo_geocoding_client import (
    OpenMeteoGeocodingClient,
    OpenMeteoGeocodingNoResultsError,
    OpenMeteoGeocodingPayloadError,
    OpenMeteoGeocodingUnavailableError,
)
from app.models.analysis_city import CoreAnalysisCity
from app.repositories.analysis_city_repository import AnalysisCityRepository
from app.schemas.analysis_city import AnalysisCityCreate


class AnalysisCityConflictError(Exception):
    pass


class AnalysisCityService:
    def __init__(self, db: Session, geocoding_client: OpenMeteoGeocodingClient | None = None) -> None:
        self.repository = AnalysisCityRepository(db)
        self.geocoding_client = geocoding_client or OpenMeteoGeocodingClient()

    def create_analysis_city(self, payload: AnalysisCityCreate) -> CoreAnalysisCity:
        city_name = payload.city_name.strip()
        country_code = payload.country_code.strip().upper() if payload.country_code else None

        existing = self.repository.get_by_city_and_country(city_name, country_code)
        if existing is not None:
            raise AnalysisCityConflictError("Analysis city already exists.")

        result = self.geocoding_client.search_city(city_name=city_name, country_code=country_code)

        return self.repository.create_analysis_city(
            city_name=city_name,
            country_code=country_code,
            country_name=result.country,
            latitude=result.latitude,
            longitude=result.longitude,
            open_meteo_location_id=result.location_id,
            admin1=result.admin1,
            timezone=result.timezone,
        )

    def list_analysis_cities(self) -> list[CoreAnalysisCity]:
        return self.repository.list_analysis_cities()

    def get_analysis_city(self, city_id: int) -> CoreAnalysisCity:
        city = self.repository.get_analysis_city_by_id(city_id)
        if city is None:
            raise LookupError("Analysis city not found.")
        return city

    def delete_analysis_city(self, city_id: int) -> None:
        city = self.repository.get_analysis_city_by_id(city_id)
        if city is None:
            raise LookupError("Analysis city not found.")
        self.repository.delete_analysis_city(city)


__all__ = [
    "AnalysisCityService",
    "AnalysisCityConflictError",
    "OpenMeteoGeocodingNoResultsError",
    "OpenMeteoGeocodingUnavailableError",
    "OpenMeteoGeocodingPayloadError",
]
