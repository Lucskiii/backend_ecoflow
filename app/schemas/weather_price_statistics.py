from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas.weather_price_analysis import AnalysisCityWeightInput


class WeatherPriceStatisticsRequest(BaseModel):
    analysis_run_id: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    end_date: date | None = None
    bidding_zone_id: int | None = Field(default=None, gt=0)
    product_id: int | None = Field(default=None, gt=0)
    price_type: str | None = Field(default="spot", min_length=1, max_length=20)
    cities: list[AnalysisCityWeightInput] | None = None

    @model_validator(mode="after")
    def validate_source_selection(self) -> "WeatherPriceStatisticsRequest":
        if self.analysis_run_id is not None:
            return self

        required_missing = []
        if self.start_date is None:
            required_missing.append("start_date")
        if self.end_date is None:
            required_missing.append("end_date")
        if self.bidding_zone_id is None:
            required_missing.append("bidding_zone_id")
        if not self.cities:
            required_missing.append("cities")

        if required_missing:
            missing = ", ".join(required_missing)
            raise ValueError(
                "Provide analysis_run_id or a full raw selection payload. Missing: "
                f"{missing}"
            )

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")

        return self


class TimeRange(BaseModel):
    start: datetime | None
    end: datetime | None


class MetricDescriptiveStats(BaseModel):
    count: int
    min: float | None
    max: float | None
    mean: float | None
    median: float | None
    std: float | None


class CorrelationMatrix(BaseModel):
    columns: list[str]
    values: list[list[float | None]]


class BucketPoint(BaseModel):
    bucket: str
    count: int
    avg_price: float | None
    min_price: float | None
    max_price: float | None


class ScatterPoint(BaseModel):
    x: float
    y: float
    ts_utc: datetime


class LagCorrelationPoint(BaseModel):
    lag_hours: int
    correlation: float | None


class OutlierPoint(BaseModel):
    ts_utc: datetime
    price_eur_mwh: float
    z_score: float


class TrendLine(BaseModel):
    slope: float | None
    intercept: float | None


class WeatherPriceStatisticsResponse(BaseModel):
    meta: dict
    descriptive_statistics: dict[str, MetricDescriptiveStats]
    correlations: dict[str, float | None]
    correlation_matrix: CorrelationMatrix
    bucket_analysis: dict[str, list[BucketPoint]]
    scatter_data: dict[str, list[ScatterPoint]]
    lag_analysis: dict[str, list[LagCorrelationPoint]]
    interpretation_hints: list[str]
    outliers: list[OutlierPoint] = []
    trend_lines: dict[str, TrendLine] = {}
