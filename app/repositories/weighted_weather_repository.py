from __future__ import annotations

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db_dialect import is_mysql_family
from app.models.tables import CoreWeightedWeatherAggregate


class WeightedWeatherRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        table = CoreWeightedWeatherAggregate.__table__
        dialect_name = self.db.get_bind().dialect.name
        if is_mysql_family(dialect_name):
            stmt = mysql_insert(table).values(rows)
            result = self.db.execute(
                stmt.on_duplicate_key_update(
                    temp_c_weighted=stmt.inserted.temp_c_weighted,
                    wind_ms_weighted=stmt.inserted.wind_ms_weighted,
                    ghi_wm2_weighted=stmt.inserted.ghi_wm2_weighted,
                    cloud_pct_weighted=stmt.inserted.cloud_pct_weighted,
                )
            )
            return int(result.rowcount or 0)

        inserted = 0
        for row in rows:
            self.db.add(CoreWeightedWeatherAggregate(**row))
            inserted += 1
        return inserted
