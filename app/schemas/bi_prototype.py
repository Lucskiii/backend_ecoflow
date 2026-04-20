from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BiPrototypeSyncResponse(BaseModel):
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    inserted_or_updated_dim_time: int
    inserted_or_updated_dim_customer: int
    inserted_or_updated_dim_site: int
    inserted_or_updated_dim_market_product: int
    inserted_or_updated_fact_energy_interval: int
    inserted_or_updated_fact_market_price: int


class BiTrendPoint(BaseModel):
    ts: datetime
    value: Decimal


class BiEnergyTrendResponse(BaseModel):
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    site_key: int | None = None
    points: list[BiTrendPoint]


class BiPriceTrendResponse(BaseModel):
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    market_product_key: int | None = None
    bidding_zone_id: int | None = None
    points: list[BiTrendPoint]
