from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import CoreDailyConsumption


class ConsumptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_consumption_date(self, customer_id: int) -> date | None:
        return self.db.scalar(
            select(func.max(CoreDailyConsumption.consumption_date)).where(
                CoreDailyConsumption.customer_id == customer_id
            )
        )

    def exists_for_date(self, customer_id: int, consumption_date: date) -> bool:
        statement = select(CoreDailyConsumption.consumption_id).where(
            CoreDailyConsumption.customer_id == customer_id,
            CoreDailyConsumption.consumption_date == consumption_date,
        )
        return self.db.scalar(statement) is not None

    def bulk_insert(self, rows: list[CoreDailyConsumption]) -> int:
        if not rows:
            return 0
        self.db.add_all(rows)
        self.db.commit()
        return len(rows)

    def list_by_customer_and_range(
        self,
        customer_id: int,
        start_date: date,
        end_date: date,
    ) -> list[CoreDailyConsumption]:
        statement = (
            select(CoreDailyConsumption)
            .where(
                CoreDailyConsumption.customer_id == customer_id,
                CoreDailyConsumption.consumption_date >= start_date,
                CoreDailyConsumption.consumption_date <= end_date,
            )
            .order_by(CoreDailyConsumption.consumption_date)
        )
        return list(self.db.scalars(statement))
