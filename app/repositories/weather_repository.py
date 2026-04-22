from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import MetaData, Table, and_, func, insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db_dialect import is_mysql_family
from app.repositories.raw_ingestion_repository import RawIngestionRepository

@dataclass(slots=True)
class SiteCoordinate:
    site_id: int
    latitude: Decimal
    longitude: Decimal


class WeatherRepository:
    def __init__(self, db: Session):
        self.db = db
        metadata = MetaData()
        bind = db.get_bind()
        self.site_table = Table("core_site", metadata, autoload_with=bind)
        self.weather_location_table = Table("core_weather_location", metadata, autoload_with=bind)
        self.weather_observation_table = Table("core_ts_weather_observation", metadata, autoload_with=bind)
        self.batch_table = Table("raw_ingestion_batch", metadata, autoload_with=bind)
        self.raw_payload_table = Table("raw_raw_payload", metadata, autoload_with=bind)
        self.quality_flag_table = Table("core_quality_flag", metadata, autoload_with=bind)
        self.raw_ingestion_repository = RawIngestionRepository(db)

        self.site_id_col = self._column(self.site_table, "site_id", "id")
        self.site_lat_col = self._column(self.site_table, "lat", "latitude")
        self.site_lon_col = self._column(self.site_table, "lon", "longitude")

        self.weather_loc_id_col = self._column(self.weather_location_table, "weather_loc_id", "id")
        self.weather_loc_site_id_col = self._optional_column(self.weather_location_table, "site_id")
        self.weather_loc_lat_col = self._column(self.weather_location_table, "lat", "latitude")
        self.weather_loc_lon_col = self._column(self.weather_location_table, "lon", "longitude")
        self.weather_loc_provider_col = self._column(self.weather_location_table, "provider")
        self.weather_loc_model_col = self._optional_column(self.weather_location_table, "model_name")
        self.weather_loc_key_col = self._optional_column(self.weather_location_table, "provider_location_key")

        self.obs_loc_id_col = self._column(self.weather_observation_table, "weather_loc_id", "weather_location_id")
        self.obs_ts_col = self._column(self.weather_observation_table, "ts_utc", "ts")
        self.obs_metric_col = self._column(self.weather_observation_table, "metric")
        self.obs_value_col = self._column(self.weather_observation_table, "value")

        self.batch_id_col = self._column(self.batch_table, "ingestion_batch_id", "id")
        self.raw_payload_id_col = self._column(self.raw_payload_table, "raw_payload_id", "id")
        self.raw_payload_batch_col = self._column(self.raw_payload_table, "ingestion_batch_id")
        self.raw_payload_entity_col = self._optional_column(self.raw_payload_table, "entity_hint")
        self.raw_payload_payload_col = self._column(self.raw_payload_table, "payload")
        self.raw_payload_hash_col = self._optional_column(self.raw_payload_table, "payload_hash")

        self.quality_flag_code_col = self._optional_column(self.quality_flag_table, "quality_flag", "code")
        self.quality_flag_desc_col = self._optional_column(self.quality_flag_table, "description")

    @staticmethod
    def _column(table: Table, *names: str):
        for name in names:
            if name in table.c:
                return table.c[name]
        raise KeyError(f"None of columns {names!r} found in {table.name}")

    @staticmethod
    def _optional_column(table: Table, *names: str):
        for name in names:
            if name in table.c:
                return table.c[name]
        return None

    @staticmethod
    def _normalize_coord(value: Decimal | float) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def list_sites_with_valid_coordinates(self) -> list[SiteCoordinate]:
        rows = self.db.execute(
            select(self.site_id_col, self.site_lat_col, self.site_lon_col).where(
                and_(self.site_lat_col.is_not(None), self.site_lon_col.is_not(None))
            )
        ).all()
        return [SiteCoordinate(site_id=row[0], latitude=Decimal(str(row[1])), longitude=Decimal(str(row[2]))) for row in rows]

    def get_site_coordinates(self, site_id: int) -> SiteCoordinate | None:
        row = self.db.execute(
            select(self.site_id_col, self.site_lat_col, self.site_lon_col).where(
                self.site_id_col == site_id,
                self.site_lat_col.is_not(None),
                self.site_lon_col.is_not(None),
            )
        ).first()
        if row is None:
            return None
        return SiteCoordinate(site_id=row[0], latitude=Decimal(str(row[1])), longitude=Decimal(str(row[2])))

    def find_weather_location_id(self, site_id: int, latitude: Decimal, longitude: Decimal, provider: str) -> int | None:
        latitude = self._normalize_coord(latitude)
        longitude = self._normalize_coord(longitude)
        filters = [
            self.weather_loc_provider_col == provider,
            self.weather_loc_lat_col == latitude,
            self.weather_loc_lon_col == longitude,
        ]
        if self.weather_loc_site_id_col is not None:
            filters.insert(0, self.weather_loc_site_id_col == site_id)
        existing = self.db.execute(select(self.weather_loc_id_col).where(*filters)).scalar_one_or_none()
        return int(existing) if existing is not None else None

    def get_or_create_weather_location(
        self, site_id: int, latitude: Decimal, longitude: Decimal, provider: str, model_name: str | None = None
    ) -> int:
        latitude = self._normalize_coord(latitude)
        longitude = self._normalize_coord(longitude)
        provider_key = f"{latitude:.6f},{longitude:.6f}"
        existing = self.find_weather_location_id(site_id, latitude, longitude, provider)
        if existing is not None:
            if self.weather_loc_site_id_col is not None:
                self.db.execute(
                    self.weather_location_table.update()
                    .where(self.weather_loc_id_col == existing, self.weather_loc_site_id_col.is_(None))
                    .values({self.weather_loc_site_id_col.key: site_id})
                )
            return int(existing)

        payload: dict[str, Any] = {
            self.weather_loc_provider_col.key: provider,
            self.weather_loc_lat_col.key: latitude,
            self.weather_loc_lon_col.key: longitude,
        }
        if self.weather_loc_site_id_col is not None:
            payload[self.weather_loc_site_id_col.key] = site_id
        if self.weather_loc_model_col is not None:
            payload[self.weather_loc_model_col.key] = model_name
        if self.weather_loc_key_col is not None:
            payload[self.weather_loc_key_col.key] = provider_key

        result = self.db.execute(insert(self.weather_location_table).values(**payload))
        return int(result.inserted_primary_key[0])

    def get_latest_stored_timestamp(self, weather_loc_id: int) -> datetime | None:
        return self.db.execute(
            select(func.max(self.obs_ts_col)).where(self.obs_loc_id_col == weather_loc_id)
        ).scalar_one_or_none()

    def create_ingestion_batch(self, source_uri: str | None, notes: str | None = None) -> int:
        return self.raw_ingestion_repository._create_batch(
            source_system="open-meteo",
            source_topic="weather_hourly",
            source_uri=source_uri,
            notes=notes,
        )

    def store_raw_payload(self, ingestion_batch_id: int, payload: dict[str, Any], entity_hint: str | None = None) -> int | None:
        raw_bytes = json.dumps(payload).encode("utf-8")
        return self.raw_ingestion_repository._store_payload(
            ingestion_batch_id=ingestion_batch_id,
            payload=payload,
            raw_bytes=raw_bytes,
            entity_hint=entity_hint,
        )

    def ensure_quality_flag(self, code: str, description: str) -> None:
        if self.quality_flag_code_col is None or self.quality_flag_desc_col is None:
            return
        existing = self.db.execute(
            select(self.quality_flag_code_col).where(self.quality_flag_code_col == code)
        ).scalar_one_or_none()
        if existing is None:
            self.db.execute(
                insert(self.quality_flag_table).values(
                    **{
                        self.quality_flag_code_col.key: code,
                        self.quality_flag_desc_col.key: description,
                    }
                )
            )

    def upsert_weather_observations(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        dialect_name = self.db.get_bind().dialect.name
        if is_mysql_family(dialect_name):
            stmt = mysql_insert(self.weather_observation_table).values(rows)
            result = self.db.execute(
                stmt.on_duplicate_key_update(
                    **{self.obs_value_col.key: getattr(stmt.inserted, self.obs_value_col.key)}
                )
            )
            return int(result.rowcount or 0)

        inserted = 0
        for row in rows:
            existing = self.db.execute(
                select(self.obs_ts_col).where(
                    self.obs_loc_id_col == row[self.obs_loc_id_col.key],
                    self.obs_ts_col == row[self.obs_ts_col.key],
                    self.obs_metric_col == row[self.obs_metric_col.key],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.execute(insert(self.weather_observation_table).values(**row))
                inserted += 1
        return inserted
