from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session


class ConsumptionSimulationService:
    """Disabled because core_daily_consumption is not part of mysql_schema.sql."""

    def __init__(self, db: Session):
        self.db = db

    def ensure_customer_consumption_data(self, customer_id: int) -> int:
        raise ValueError("core_daily_consumption is not available in the target schema")

    def get_status(self, customer_id: int) -> dict[str, date | bool | int | None]:
        raise ValueError("core_daily_consumption is not available in the target schema")

    def list_consumption(self, customer_id: int, start_date: date, end_date: date) -> list[object]:
        raise ValueError("core_daily_consumption is not available in the target schema")
