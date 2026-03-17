from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.tables import CoreDailyConsumption
from app.repositories.consumption_repository import ConsumptionRepository
from app.repositories.customer_repository import CustomerRepository


class ConsumptionSimulationService:
    def __init__(self, db: Session):
        self.db = db
        self.customer_repository = CustomerRepository(db)
        self.consumption_repository = ConsumptionRepository(db)

    def _seasonal_adjustment(self, month: int) -> float:
        if month in (12, 1, 2):
            return 1.35
        if month in (3, 4, 5):
            return 1.05
        if month in (6, 7, 8):
            return 0.85
        return 1.1

    def _pv_seasonal_factor(self, month: int) -> float:
        if month in (12, 1, 2):
            return 0.28
        if month in (3, 4, 5):
            return 0.85
        if month in (6, 7, 8):
            return 1.0
        return 0.62

    def _weekday_adjustment(self, weekday: int) -> float:
        return 1.08 if weekday >= 5 else 1.0

    @staticmethod
    def _round3(value: float) -> Decimal:
        return Decimal(str(round(max(value, 0.0), 3)))

    def _simulate_kwh(self, customer_id: int, consumption_date: date) -> Decimal:
        rng = random.Random((customer_id * 100000) + consumption_date.toordinal())
        baseline = 9.2
        seasonal = self._seasonal_adjustment(consumption_date.month)
        weekday = self._weekday_adjustment(consumption_date.weekday())
        noise = rng.uniform(0.82, 1.18)
        value = max(4.0, min(18.0, baseline * seasonal * weekday * noise))
        return self._round3(value)

    def _simulate_pv_generation_kwh(self, customer_id: int, consumption_date: date) -> Decimal:
        rng = random.Random((customer_id * 200000) + consumption_date.toordinal())
        seasonal = self._pv_seasonal_factor(consumption_date.month)
        cloud_factor = rng.uniform(0.0, 1.15)
        has_low_solar_day = rng.random() < (0.35 if consumption_date.month in (11, 12, 1, 2) else 0.14)
        value = 0.0 if has_low_solar_day else 10.2 * seasonal * cloud_factor
        return self._round3(value)

    def _build_daily_row(self, customer_id: int, consumption_date: date) -> CoreDailyConsumption:
        consumption_kwh = self._simulate_kwh(customer_id, consumption_date)
        pv_generation_kwh = self._simulate_pv_generation_kwh(customer_id, consumption_date)

        self_consumption_kwh = min(consumption_kwh, pv_generation_kwh)
        grid_import_kwh = max(consumption_kwh - self_consumption_kwh, Decimal("0"))
        grid_export_kwh = max(pv_generation_kwh - self_consumption_kwh, Decimal("0"))

        if pv_generation_kwh > 0:
            self_consumption_share_pct = ((pv_generation_kwh - grid_export_kwh) / pv_generation_kwh) * Decimal("100")
        else:
            self_consumption_share_pct = Decimal("0")

        return CoreDailyConsumption(
            customer_id=customer_id,
            consumption_date=consumption_date,
            consumption_kwh=consumption_kwh.quantize(Decimal("0.001")),
            grid_import_kwh=grid_import_kwh.quantize(Decimal("0.001")),
            grid_export_kwh=grid_export_kwh.quantize(Decimal("0.001")),
            pv_generation_kwh=pv_generation_kwh.quantize(Decimal("0.001")),
            self_consumption_share_pct=self_consumption_share_pct.quantize(Decimal("0.01")),
            source_type="simulated",
        )

    def _generate_rows(self, customer_id: int, from_date: date, to_date: date) -> list[CoreDailyConsumption]:
        rows: list[CoreDailyConsumption] = []
        current = from_date
        while current <= to_date:
            if not self.consumption_repository.exists_for_date(customer_id, current):
                rows.append(self._build_daily_row(customer_id, current))
            current += timedelta(days=1)
        return rows

    def ensure_customer_consumption_data(self, customer_id: int) -> int:
        customer = self.customer_repository.get(customer_id)
        if customer is None:
            raise ValueError("Customer not found")

        today = date.today()
        latest = self.consumption_repository.get_latest_consumption_date(customer_id)

        if latest is None:
            start_date = today - timedelta(days=90)
        elif latest >= today:
            return 0
        else:
            start_date = latest + timedelta(days=1)

        rows = self._generate_rows(customer_id=customer.id, from_date=start_date, to_date=today)
        return self.consumption_repository.bulk_insert(rows)

    def get_status(self, customer_id: int) -> dict[str, date | bool | int | None]:
        customer = self.customer_repository.get(customer_id)
        if customer is None:
            raise ValueError("Customer not found")

        today = date.today()
        latest = self.consumption_repository.get_latest_consumption_date(customer_id)

        if latest is None:
            days_missing = 91
            missing_until_today = True
        elif latest >= today:
            days_missing = 0
            missing_until_today = False
        else:
            days_missing = (today - latest).days
            missing_until_today = True

        return {
            "customer_id": customer_id,
            "latest_available_date": latest,
            "missing_until_today": missing_until_today,
            "days_missing_count": days_missing,
        }

    def list_consumption(
        self,
        customer_id: int,
        start_date: date,
        end_date: date,
    ) -> list[CoreDailyConsumption]:
        customer = self.customer_repository.get(customer_id)
        if customer is None:
            raise ValueError("Customer not found")
        return self.consumption_repository.list_by_customer_and_range(customer_id, start_date, end_date)
