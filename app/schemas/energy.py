from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EnergySummaryResponse(BaseModel):
    period: str
    grid_import_kwh: Decimal = Field(default=Decimal("0"))
    grid_export_kwh: Decimal = Field(default=Decimal("0"))
    load_kwh: Decimal = Field(default=Decimal("0"))
    pv_generation_kwh: Decimal = Field(default=Decimal("0"))
    self_consumption_ratio: float = 0.0


class EnergyPoint(BaseModel):
    ts: datetime
    value: Decimal


class EnergySeries(BaseModel):
    meter_type: str
    unit: str = "kwh"
    points: list[EnergyPoint]


class EnergyTimeseriesResponse(BaseModel):
    interval_minutes: int = 15
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    series: list[EnergySeries]


class EnergySimulationResponse(BaseModel):
    customer_id: int
    days: int
    sites_processed: int
    readings_created: int
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")


class PortfolioSummaryResponse(BaseModel):
    period: str
    total_grid_export_kwh: Decimal = Field(default=Decimal("0"))
    tradable_export_kwh: Decimal = Field(default=Decimal("0"))
    customer_count: int = 0
    site_count: int = 0
    interval_minutes: int = 15
    safety_factor: Decimal = Field(default=Decimal("0.9"))


class PortfolioSeries(BaseModel):
    name: str
    unit: str = "kwh"
    points: list[EnergyPoint]


class PortfolioTimeseriesResponse(BaseModel):
    interval_minutes: int = 15
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    series: list[PortfolioSeries]
