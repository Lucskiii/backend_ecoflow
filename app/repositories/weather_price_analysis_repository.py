from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db_dialect import is_mysql_family
from app.models.tables import (
    BiWeatherPriceAnalysis,
    CoreWeightedWeatherAggregate,
    CoreTsMarketPrice,
    CoreWeatherPriceAnalysisRun,
    CoreWeatherPriceAnalysisRunCity,
)


class WeatherPriceAnalysisRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, start_date, end_date, run_name: str | None = None) -> CoreWeatherPriceAnalysisRun:
        run = CoreWeatherPriceAnalysisRun(
            run_name=run_name,
            start_date=start_date,
            end_date=end_date,
            status="created",
        )
        self.db.add(run)
        self.db.flush()
        return run

    def set_run_status(self, run_id: int, status_value: str, notes: str | None = None) -> None:
        run = self.db.get(CoreWeatherPriceAnalysisRun, run_id)
        if run is None:
            return
        run.status = status_value
        run.notes = notes

    def set_run_name(self, run_id: int, run_name: str) -> CoreWeatherPriceAnalysisRun | None:
        run = self.db.get(CoreWeatherPriceAnalysisRun, run_id)
        if run is None:
            return None
        run.run_name = run_name
        return run

    def add_run_cities(self, run_id: int, city_weights: dict[int, object]) -> None:
        for city_id, weight in city_weights.items():
            self.db.add(
                CoreWeatherPriceAnalysisRunCity(
                    analysis_run_id=run_id,
                    analysis_city_id=city_id,
                    weight=weight,
                )
            )

    def get_default_product_id(self) -> int | None:
        return self.db.scalar(select(func.min(CoreTsMarketPrice.market_product_id)))

    def get_default_product_id_for_zone_and_range(
        self, bidding_zone_id: int, start_ts: datetime, end_ts: datetime
    ) -> int | None:
        return self.db.scalar(
            select(func.min(CoreTsMarketPrice.market_product_id)).where(
                CoreTsMarketPrice.bidding_zone_id == bidding_zone_id,
                CoreTsMarketPrice.ts >= start_ts,
                CoreTsMarketPrice.ts <= end_ts,
            )
        )

    def get_prices(self, start_ts: datetime, end_ts: datetime, product_id: int, bidding_zone_id: int) -> dict[datetime, float]:
        stmt: Select[tuple[datetime, float]] = (
            select(CoreTsMarketPrice.ts, CoreTsMarketPrice.price)
            .where(
                CoreTsMarketPrice.market_product_id == product_id,
                CoreTsMarketPrice.bidding_zone_id == bidding_zone_id,
                CoreTsMarketPrice.ts >= start_ts,
                CoreTsMarketPrice.ts <= end_ts,
            )
            .order_by(CoreTsMarketPrice.ts.asc())
        )
        return {ts: price for ts, price in self.db.execute(stmt).all()}

    def bulk_upsert_analysis_rows(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        table = BiWeatherPriceAnalysis.__table__
        if is_mysql_family(self.db.get_bind().dialect.name):
            stmt = mysql_insert(table).values(rows)
            result = self.db.execute(
                stmt.on_duplicate_key_update(
                    temp_c_weighted=stmt.inserted.temp_c_weighted,
                    wind_ms_weighted=stmt.inserted.wind_ms_weighted,
                    ghi_wm2_weighted=stmt.inserted.ghi_wm2_weighted,
                    cloud_pct_weighted=stmt.inserted.cloud_pct_weighted,
                    price_eur_mwh=stmt.inserted.price_eur_mwh,
                    source_system=stmt.inserted.source_system,
                )
            )
            return int(result.rowcount or 0)

        for row in rows:
            self.db.add(BiWeatherPriceAnalysis(**row))
        return len(rows)

    def get_analysis_rows(self, run_id: int) -> list[BiWeatherPriceAnalysis]:
        return list(
            self.db.scalars(
                select(BiWeatherPriceAnalysis)
                .where(BiWeatherPriceAnalysis.analysis_run_id == run_id)
                .order_by(BiWeatherPriceAnalysis.ts_utc.asc())
            )
        )

    def get_run(self, run_id: int) -> CoreWeatherPriceAnalysisRun | None:
        return self.db.get(CoreWeatherPriceAnalysisRun, run_id)

    def get_run_city_weights(self, run_id: int) -> dict[int, object]:
        rows = self.db.execute(
            select(
                CoreWeatherPriceAnalysisRunCity.analysis_city_id,
                CoreWeatherPriceAnalysisRunCity.weight,
            ).where(CoreWeatherPriceAnalysisRunCity.analysis_run_id == run_id)
        ).all()
        return {int(city_id): weight for city_id, weight in rows}

    def get_status_payload(self, run_id: int) -> dict | None:
        run = self.db.get(CoreWeatherPriceAnalysisRun, run_id)
        if run is None:
            return None
        rows_analysis = self.db.scalar(
            select(func.count(BiWeatherPriceAnalysis.id)).where(BiWeatherPriceAnalysis.analysis_run_id == run_id)
        )
        rows_aggregate = self.db.scalar(
            select(func.count(CoreWeightedWeatherAggregate.id)).where(CoreWeightedWeatherAggregate.analysis_run_id == run_id)
        )
        return {
            "analysis_run_id": run.id,
            "run_name": run.run_name,
            "status": run.status,
            "start_date": run.start_date,
            "end_date": run.end_date,
            "requested_at": run.requested_at,
            "rows_aggregate": int(rows_aggregate or 0),
            "rows_analysis": int(rows_analysis or 0),
        }

    def list_runs(self, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            select(
                CoreWeatherPriceAnalysisRun.id,
                CoreWeatherPriceAnalysisRun.run_name,
                CoreWeatherPriceAnalysisRun.status,
                CoreWeatherPriceAnalysisRun.start_date,
                CoreWeatherPriceAnalysisRun.end_date,
                CoreWeatherPriceAnalysisRun.requested_at,
                func.count(BiWeatherPriceAnalysis.id).label("rows_analysis"),
            )
            .outerjoin(
                BiWeatherPriceAnalysis,
                BiWeatherPriceAnalysis.analysis_run_id == CoreWeatherPriceAnalysisRun.id,
            )
            .group_by(
                CoreWeatherPriceAnalysisRun.id,
                CoreWeatherPriceAnalysisRun.run_name,
                CoreWeatherPriceAnalysisRun.status,
                CoreWeatherPriceAnalysisRun.start_date,
                CoreWeatherPriceAnalysisRun.end_date,
                CoreWeatherPriceAnalysisRun.requested_at,
            )
            .order_by(CoreWeatherPriceAnalysisRun.requested_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "analysis_run_id": int(run_id),
                "run_name": run_name,
                "status": status,
                "start_date": start_date,
                "end_date": end_date,
                "requested_at": requested_at,
                "rows_analysis": int(rows_analysis or 0),
            }
            for run_id, run_name, status, start_date, end_date, requested_at, rows_analysis in rows
        ]
