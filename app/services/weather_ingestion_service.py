from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.clients.open_meteo_client import OpenMeteoClient, OpenMeteoResult
from app.config import get_settings
from app.repositories.weather_repository import SiteCoordinate, WeatherRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WeatherIngestionResult:
    sites_processed: int = 0
    locations_processed: int = 0
    rows_inserted: int = 0
    failures: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "sites_processed": self.sites_processed,
            "locations_processed": self.locations_processed,
            "rows_inserted": self.rows_inserted,
            "failures": self.failures or [],
        }


class WeatherIngestionService:
    QUALITY_FLAG = "estimated"
    QUALITY_DESCRIPTION = "Estimated or modeled value"
    PROVIDER = "open-meteo"

    def __init__(self, db: Session, client: OpenMeteoClient | None = None):
        self.db = db
        self.settings = get_settings()
        self.client = client or OpenMeteoClient()
        self.repository = WeatherRepository(db)

    def get_status(self) -> dict:
        sites = self.repository.list_sites_with_valid_coordinates()
        status_rows: list[dict] = []
        for site in sites:
            weather_loc_id = self.repository.find_weather_location_id(
                site.site_id, site.latitude, site.longitude, self.PROVIDER
            )
            latest = self.repository.get_latest_stored_timestamp(weather_loc_id) if weather_loc_id is not None else None
            status_rows.append(
                {
                    "site_id": site.site_id,
                    "weather_loc_id": weather_loc_id,
                    "latest_stored_ts_utc": latest.isoformat() if latest else None,
                }
            )
        return {
            "scheduler_enabled": self.settings.weather_scheduler_enabled,
            "scheduler_interval_minutes": self.settings.weather_scheduler_interval_minutes,
            "default_backfill_days": self.settings.weather_default_backfill_days,
            "sites": status_rows,
        }

    def backfill_weather_for_site(
        self, site_id: int, start_date: date | None = None, end_date: date | None = None
    ) -> dict:
        site = self.repository.get_site_coordinates(site_id)
        if site is None:
            raise ValueError(f"Site {site_id} not found or missing coordinates")
        result = self._ingest_site(site, start_date=start_date, end_date=end_date)
        self.db.commit()
        return result.to_dict()

    def backfill_weather_for_all_sites(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> dict:
        result = WeatherIngestionResult(failures=[])
        for site in self.repository.list_sites_with_valid_coordinates():
            try:
                site_result = self._ingest_site(site, start_date=start_date, end_date=end_date)
                result.sites_processed += site_result.sites_processed
                result.locations_processed += site_result.locations_processed
                result.rows_inserted += site_result.rows_inserted
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                message = f"site_id={site.site_id}: {exc}"
                logger.warning("Weather ingestion failed %s", message)
                result.failures.append(message)
        return result.to_dict()

    def sync_missing_weather(self) -> dict:
        newest_available = self._latest_available_date_utc()
        result = WeatherIngestionResult(failures=[])
        for site in self.repository.list_sites_with_valid_coordinates():
            try:
                weather_loc_id = self.repository.get_or_create_weather_location(
                    site.site_id, site.latitude, site.longitude, self.PROVIDER
                )
                latest = self.repository.get_latest_stored_timestamp(weather_loc_id)
                if latest is None:
                    start_date = newest_available - timedelta(days=self.settings.weather_default_backfill_days - 1)
                else:
                    start_date = (latest.replace(tzinfo=timezone.utc) + timedelta(hours=1)).date()
                if start_date > newest_available:
                    continue
                site_result = self._ingest_site(site, start_date=start_date, end_date=newest_available)
                result.sites_processed += site_result.sites_processed
                result.locations_processed += site_result.locations_processed
                result.rows_inserted += site_result.rows_inserted
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                message = f"site_id={site.site_id}: {exc}"
                logger.warning("Weather sync failed %s", message)
                result.failures.append(message)
        return result.to_dict()

    def _ingest_site(
        self, site: SiteCoordinate, start_date: date | None = None, end_date: date | None = None
    ) -> WeatherIngestionResult:
        weather_loc_id = self.repository.get_or_create_weather_location(
            site.site_id, site.latitude, site.longitude, self.PROVIDER
        )
        resolved_start, resolved_end = self._resolve_date_range(weather_loc_id, start_date, end_date)
        if resolved_start > resolved_end:
            return WeatherIngestionResult(sites_processed=1, locations_processed=1, rows_inserted=0, failures=[])

        self.repository.ensure_quality_flag(self.QUALITY_FLAG, self.QUALITY_DESCRIPTION)
        rows_inserted = 0
        for range_start, range_end in self._iter_ranges(resolved_start, resolved_end, self.settings.open_meteo_max_days_per_request):
            result = self._fetch_for_range(site.latitude, site.longitude, range_start, range_end)
            ingestion_batch_id = self.repository.create_ingestion_batch(
                source_uri=result.source_url,
                notes=f"weather ingestion for site_id={site.site_id} range={range_start}..{range_end}",
            )
            if self.settings.weather_store_raw_payload:
                self.repository.store_raw_payload(ingestion_batch_id, result.raw_payload, entity_hint=f"weather_site_{site.site_id}")
            observations = self._build_observation_rows(weather_loc_id, ingestion_batch_id, result)
            rows_inserted += self.repository.upsert_weather_observations(observations)
            logger.info(
                "Weather ingestion chunk complete site_id=%s weather_loc_id=%s start=%s end=%s rows=%s",
                site.site_id,
                weather_loc_id,
                range_start,
                range_end,
                len(observations),
            )
        return WeatherIngestionResult(sites_processed=1, locations_processed=1, rows_inserted=rows_inserted, failures=[])

    def _resolve_date_range(
        self, weather_loc_id: int, start_date: date | None, end_date: date | None
    ) -> tuple[date, date]:
        today = self._latest_available_date_utc()
        resolved_end = end_date or today
        if start_date is not None:
            return start_date, resolved_end
        latest = self.repository.get_latest_stored_timestamp(weather_loc_id)
        if latest is None:
            return resolved_end - timedelta(days=self.settings.weather_default_backfill_days - 1), resolved_end
        return (latest.replace(tzinfo=timezone.utc) + timedelta(hours=1)).date(), resolved_end

    def _fetch_for_range(self, latitude: Decimal, longitude: Decimal, start_date: date, end_date: date) -> OpenMeteoResult:
        recent_cutoff = self._latest_available_date_utc() - timedelta(days=self.settings.weather_recent_days_window)
        if end_date >= recent_cutoff:
            result = self.client.fetch_recent_hourly(latitude, longitude, start_date, end_date)
            latest_complete_hour = self._latest_complete_hour_utc()
            range_start_utc = datetime.combine(start_date, datetime.min.time())
            range_end_utc = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            result.points = [
                point
                for point in result.points
                if range_start_utc <= point.ts_utc < range_end_utc and point.ts_utc <= latest_complete_hour
            ]
            return result
        return self.client.fetch_historical_hourly(latitude, longitude, start_date, end_date)

    def _build_observation_rows(self, weather_loc_id: int, ingestion_batch_id: int, result: OpenMeteoResult) -> list[dict]:
        rows: list[dict] = []
        metrics = {
            "temperature_2m": lambda point: point.temp_c,
            "wind_speed_10m": lambda point: point.wind_ms,
            "shortwave_radiation": lambda point: point.ghi_wm2,
            "cloud_cover": lambda point: point.cloud_pct,
        }
        for point in result.points:
            for metric, extractor in metrics.items():
                value = extractor(point)
                if value is None:
                    continue
                rows.append(
                    {
                        "weather_location_id": weather_loc_id,
                        "ts": point.ts_utc,
                        "metric": metric,
                        "value": value,
                    }
                )
        return rows

    @staticmethod
    def _iter_ranges(start_date: date, end_date: date, chunk_days: int):
        cursor = start_date
        while cursor <= end_date:
            chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
            yield cursor, chunk_end
            cursor = chunk_end + timedelta(days=1)

    @staticmethod
    def _latest_available_date_utc() -> date:
        return datetime.now(timezone.utc).date()

    @staticmethod
    def _latest_complete_hour_utc() -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
