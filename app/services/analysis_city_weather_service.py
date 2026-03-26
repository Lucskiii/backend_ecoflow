from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.clients.open_meteo_weather_client import OpenMeteoClient
from app.repositories.analysis_city_repository import AnalysisCityRepository
from app.repositories.analysis_city_weather_repository import AnalysisCityWeatherRepository

logger = logging.getLogger(__name__)


class WeatherUpstreamError(RuntimeError):
    pass


class AnalysisCityWeatherService:
    def __init__(self, db: Session, client: OpenMeteoClient | None = None) -> None:
        self.db = db
        self.client = client or OpenMeteoClient()
        self.city_repository = AnalysisCityRepository(db)
        self.weather_repository = AnalysisCityWeatherRepository(db)

    def ensure_weather_data_for_selected_cities(self, city_ids: list[int], start_date: date, end_date: date) -> int:
        inserted = 0
        for city_id in city_ids:
            inserted += self.ensure_weather_data_for_analysis_city(city_id, start_date, end_date)
        return inserted

    def ensure_weather_data_for_analysis_city(self, city_id: int, start_date: date, end_date: date) -> int:
        city = self.city_repository.get_analysis_city_by_id(city_id)
        if city is None:
            raise LookupError(f"Analysis city {city_id} does not exist")

        start_ts = datetime.combine(start_date, time.min)
        end_ts = datetime.combine(end_date, time.min) + timedelta(hours=23)

        missing_ranges = self.weather_repository.calculate_missing_ranges(city_id, start_ts, end_ts)
        if not missing_ranges:
            return 0

        rows_inserted = 0
        for range_start, range_end in missing_ranges:
            try:
                result = self.client.fetch_historical_hourly(
                    latitude=city.latitude,
                    longitude=city.longitude,
                    start_date=range_start.date(),
                    end_date=range_end.date(),
                )
            except Exception as exc:
                raise WeatherUpstreamError(f"Failed to fetch weather for city_id={city_id}") from exc

            if not result.points:
                raise WeatherUpstreamError(f"No matching weather data returned for city_id={city_id}")

            payload = []
            for point in result.points:
                if point.ts_utc < range_start or point.ts_utc > range_end:
                    continue
                payload.append(
                    {
                        "analysis_city_id": city_id,
                        "ts_utc": point.ts_utc,
                        "temp_c": point.temp_c,
                        "wind_ms": point.wind_ms,
                        "ghi_wm2": point.ghi_wm2,
                        "cloud_pct": point.cloud_pct,
                        "quality_flag": "estimated",
                        "source_system": "open-meteo",
                    }
                )

            rows_inserted += self.weather_repository.bulk_upsert_observations(payload)
            logger.info(
                "Ensured weather for city_id=%s range=%s..%s inserted=%s",
                city_id,
                range_start,
                range_end,
                len(payload),
            )
        return rows_inserted
