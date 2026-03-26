from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, and_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models.tables import CoreAnalysisCityWeatherObservation


class AnalysisCityWeatherRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_existing_timestamps(self, analysis_city_id: int, start_ts: datetime, end_ts: datetime) -> set[datetime]:
        stmt: Select[tuple[datetime]] = select(CoreAnalysisCityWeatherObservation.ts_utc).where(
            CoreAnalysisCityWeatherObservation.analysis_city_id == analysis_city_id,
            CoreAnalysisCityWeatherObservation.ts_utc >= start_ts,
            CoreAnalysisCityWeatherObservation.ts_utc <= end_ts,
        )
        return {row[0] for row in self.db.execute(stmt).all()}

    def calculate_missing_ranges(self, analysis_city_id: int, start_ts: datetime, end_ts: datetime) -> list[tuple[datetime, datetime]]:
        existing = self.list_existing_timestamps(analysis_city_id, start_ts, end_ts)
        if not existing:
            return [(start_ts, end_ts)]

        missing_ranges: list[tuple[datetime, datetime]] = []
        cursor = start_ts
        range_start: datetime | None = None
        while cursor <= end_ts:
            if cursor not in existing:
                if range_start is None:
                    range_start = cursor
            elif range_start is not None:
                missing_ranges.append((range_start, cursor - timedelta(hours=1)))
                range_start = None
            cursor += timedelta(hours=1)

        if range_start is not None:
            missing_ranges.append((range_start, end_ts))
        return missing_ranges

    def bulk_upsert_observations(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        table = CoreAnalysisCityWeatherObservation.__table__
        dialect_name = self.db.get_bind().dialect.name

        if dialect_name == "mysql":
            stmt = mysql_insert(table).values(rows)
            result = self.db.execute(
                stmt.on_duplicate_key_update(
                    temp_c=stmt.inserted.temp_c,
                    wind_ms=stmt.inserted.wind_ms,
                    ghi_wm2=stmt.inserted.ghi_wm2,
                    cloud_pct=stmt.inserted.cloud_pct,
                    quality_flag=stmt.inserted.quality_flag,
                    source_system=stmt.inserted.source_system,
                )
            )
            return int(result.rowcount or 0)

        inserted = 0
        for row in rows:
            existing = self.db.scalar(
                select(CoreAnalysisCityWeatherObservation.id).where(
                    CoreAnalysisCityWeatherObservation.analysis_city_id == row["analysis_city_id"],
                    CoreAnalysisCityWeatherObservation.ts_utc == row["ts_utc"],
                )
            )
            if existing is None:
                self.db.add(CoreAnalysisCityWeatherObservation(**row))
                inserted += 1
        return inserted

    def list_weather_rows(
        self, city_ids: list[int], start_ts: datetime, end_ts: datetime
    ) -> list[CoreAnalysisCityWeatherObservation]:
        if not city_ids:
            return []
        return list(
            self.db.scalars(
                select(CoreAnalysisCityWeatherObservation)
                .where(
                    and_(
                        CoreAnalysisCityWeatherObservation.analysis_city_id.in_(city_ids),
                        CoreAnalysisCityWeatherObservation.ts_utc >= start_ts,
                        CoreAnalysisCityWeatherObservation.ts_utc <= end_ts,
                    )
                )
                .order_by(CoreAnalysisCityWeatherObservation.ts_utc.asc())
            )
        )
