from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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


class MarketPriceBackfillResponse(BaseModel):
    processed_products: int
    inserted_rows: int
    skipped_products: int
    failed_products: int
    target_start_date: date
    earliest_observed_ts: datetime | None
    latest_backfilled_ts: datetime | None


class LiveMarketPricePoint(BaseModel):
    ts: datetime
    price_eur_mwh: Decimal
    price_ct_kwh: Decimal


class LiveMarketPriceResponse(BaseModel):
    source: str
    product: str
    unit: str = "Eur/MWh"
    fetched_at: datetime
    current: LiveMarketPricePoint | None = None
    next: LiveMarketPricePoint | None = None
    points: list[LiveMarketPricePoint]


class BiddingZoneResponse(BaseModel):
    id: int
    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class BiddingZoneListResponse(BaseModel):
    items: list[BiddingZoneResponse]
