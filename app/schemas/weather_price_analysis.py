from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AnalysisCityWeightInput(BaseModel):
    analysis_city_id: int = Field(gt=0)
    weight: Decimal = Field(gt=0)


class WeatherPriceAnalysisRequest(BaseModel):
    start_date: date
    end_date: date
    product_id: int | None = Field(default=None, gt=0)
    price_type: str | None = Field(default="spot", min_length=1, max_length=20)
    cities: list[AnalysisCityWeightInput]

    @field_validator("cities")
    @classmethod
    def validate_cities_non_empty(cls, value: list[AnalysisCityWeightInput]) -> list[AnalysisCityWeightInput]:
        if not value:
            raise ValueError("at least one city must be selected")
        return value


class NormalizedWeight(BaseModel):
    analysis_city_id: int
    weight: Decimal


class WeatherPriceAnalysisRow(BaseModel):
    ts_utc: datetime
    temp_c_weighted: Decimal | None
    wind_ms_weighted: Decimal | None
    ghi_wm2_weighted: Decimal | None
    cloud_pct_weighted: Decimal | None
    price_eur_mwh: Decimal | None
    product_id: int | None
    price_type: str | None


class WeatherPriceAnalysisResponse(BaseModel):
    analysis_run_id: int
    normalized_weights: list[NormalizedWeight]
    rows_inserted_weather: int
    rows_inserted_aggregate: int
    rows_inserted_analysis: int
    data: list[WeatherPriceAnalysisRow]


class WeatherPriceAnalysisRunStatus(BaseModel):
    analysis_run_id: int
    status: str
    start_date: date | None
    end_date: date | None
    requested_at: datetime
    rows_aggregate: int
    rows_analysis: int


class WeatherPriceAnalysisErrorResponse(BaseModel):
    detail: str
