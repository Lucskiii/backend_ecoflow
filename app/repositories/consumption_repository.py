from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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

    def _is_duplicate_key_error(self, exc: IntegrityError) -> bool:
        message = str(getattr(exc, "orig", exc)).lower()
        duplicate_markers = ("duplicate", "unique", "uq_daily_consumption_customer_date")
        return any(marker in message for marker in duplicate_markers)

    def bulk_insert(self, rows: list[CoreDailyConsumption]) -> int:
        if not rows:
            return 0

        self.db.add_all(rows)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if self._is_duplicate_key_error(exc):
                return 0
            raise

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
