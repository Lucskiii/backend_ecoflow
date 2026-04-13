from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import CoreMeter, CoreTsMarketPrice, CoreTsMeterReading, Site


class CustomerRevenueService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_utc_hour(ts: datetime) -> datetime:
        if ts.tzinfo is not None and ts.utcoffset() is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts.replace(minute=0, second=0, microsecond=0)

    def calculate_for_customer(self, customer_id: int) -> Decimal:
        export_rows = list(
            self.db.execute(
                select(CoreTsMeterReading.ts, CoreTsMeterReading.value)
                .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
                .join(Site, Site.id == CoreMeter.site_id)
                .where(
                    Site.customer_id == customer_id,
                    CoreMeter.meter_role == "grid_export",
                )
            )
        )

        if not export_rows:
            return Decimal("0")

        export_by_hour: dict[datetime, Decimal] = {}
        for ts, value in export_rows:
            hour_ts = self._to_utc_hour(ts)
            export_by_hour[hour_ts] = export_by_hour.get(hour_ts, Decimal("0")) + value

        min_hour = min(export_by_hour)
        max_hour = max(export_by_hour)

        price_rows = list(
            self.db.execute(
                select(CoreTsMarketPrice.ts, CoreTsMarketPrice.price).where(
                    CoreTsMarketPrice.ts >= min_hour,
                    CoreTsMarketPrice.ts <= max_hour,
                )
            )
        )
        price_by_hour = {self._to_utc_hour(ts): price for ts, price in price_rows}

        revenue_eur = Decimal("0")
        for hour_ts, export_kwh in export_by_hour.items():
            price_eur_mwh = price_by_hour.get(hour_ts)
            if price_eur_mwh is None:
                continue
            revenue_eur += (export_kwh * price_eur_mwh) / Decimal("1000")

        return revenue_eur.quantize(Decimal("0.000001"))
