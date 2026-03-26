from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCityCreate(BaseModel):
    city_name: str = Field(min_length=1, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=10)


class AnalysisCityResponse(BaseModel):
    id: int
    city_name: str
    country_code: str | None
    country_name: str | None
    latitude: Decimal
    longitude: Decimal
    open_meteo_location_id: int | None
    admin1: str | None
    timezone: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisCityListResponse(BaseModel):
    items: list[AnalysisCityResponse]


class AnalysisCityErrorResponse(BaseModel):
    detail: str
