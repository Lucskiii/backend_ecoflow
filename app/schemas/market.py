from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarketPricePoint(BaseModel):
    ts: datetime
    price_eur_mwh: Decimal


class MarketPriceTimeseriesResponse(BaseModel):
    source: str
    product: str
    unit: str = "Eur/MWh"
    from_ts: datetime = Field(alias="from")
    to_ts: datetime = Field(alias="to")
    points: list[MarketPricePoint]


class MarketPriceRefreshResponse(BaseModel):
    inserted: int
