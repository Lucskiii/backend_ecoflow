from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DailyConsumptionRead(BaseModel):
    consumption_id: int
    customer_id: int
    consumption_date: date
    consumption_kwh: Decimal
    source_type: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailyConsumptionCreate(BaseModel):
    customer_id: int
    consumption_date: date
    consumption_kwh: Decimal
    source_type: str = "simulated"


class ConsumptionSimulationResponse(BaseModel):
    customer_id: int
    rows_created: int


class ConsumptionStatusResponse(BaseModel):
    customer_id: int
    latest_available_date: date | None
    missing_until_today: bool
    days_missing_count: int
