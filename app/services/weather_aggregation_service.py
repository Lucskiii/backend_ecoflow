from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.analysis_city_weather_repository import AnalysisCityWeatherRepository
from app.repositories.weighted_weather_repository import WeightedWeatherRepository


class WeatherAggregationService:
    """Weighted aggregation strategy:
    Aggregate using only cities that have a non-null value for a metric at a timestamp,
    and renormalize weights per timestamp+metric.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.weather_repository = AnalysisCityWeatherRepository(db)
        self.weighted_repository = WeightedWeatherRepository(db)

    def aggregate_and_store(
        self,
        analysis_run_id: int,
        city_weights: dict[int, Decimal],
        start_ts: datetime,
        end_ts: datetime,
    ) -> tuple[int, list[dict]]:
        weather_rows = self.weather_repository.list_weather_rows(list(city_weights.keys()), start_ts, end_ts)
        grouped: dict[datetime, dict[int, object]] = defaultdict(dict)
        for row in weather_rows:
            grouped[row.ts_utc][row.analysis_city_id] = row

        aggregate_rows: list[dict] = []
        for ts_utc, city_row_map in sorted(grouped.items(), key=lambda item: item[0]):
            aggregate_rows.append(
                {
                    "analysis_run_id": analysis_run_id,
                    "ts_utc": ts_utc,
                    "temp_c_weighted": self._weighted_metric(city_weights, city_row_map, "temp_c"),
                    "wind_ms_weighted": self._weighted_metric(city_weights, city_row_map, "wind_ms"),
                    "ghi_wm2_weighted": self._weighted_metric(city_weights, city_row_map, "ghi_wm2"),
                    "cloud_pct_weighted": self._weighted_metric(city_weights, city_row_map, "cloud_pct"),
                }
            )

        inserted = self.weighted_repository.bulk_upsert(aggregate_rows)
        return inserted, aggregate_rows

    @staticmethod
    def _weighted_metric(city_weights: dict[int, Decimal], city_rows: dict[int, object], metric: str) -> Decimal | None:
        numerator = Decimal("0")
        denominator = Decimal("0")
        for city_id, base_weight in city_weights.items():
            row = city_rows.get(city_id)
            if row is None:
                continue
            metric_value = getattr(row, metric)
            if metric_value is None:
                continue
            denominator += base_weight
            numerator += Decimal(str(metric_value)) * base_weight

        if denominator == 0:
            return None
        return numerator / denominator
