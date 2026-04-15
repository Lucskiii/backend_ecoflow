from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.tables import CoreMeter, CoreTsMeterReading, Site

DEFAULT_TRADABLE_FACTOR = Decimal("0.9")
PORTFOLIO_INTERVAL_MINUTES = 15


class PortfolioService:
    def __init__(self, db: Session, tradable_factor: Decimal = DEFAULT_TRADABLE_FACTOR):
        self.db = db
        self.tradable_factor = tradable_factor

    def _period_range(self, period: str) -> tuple[str, datetime | None, datetime]:
        now = datetime.now(timezone.utc)
        if period == "7d":
            return period, now - timedelta(days=7), now
        if period == "30d":
            return period, now - timedelta(days=30), now
        if period == "all":
            return period, None, now
        return "today", now.replace(hour=0, minute=0, second=0, microsecond=0), now

    def export_summary(self, period: str = "today") -> dict:
        period, from_ts, to_ts = self._period_range(period)

        readings_filter = [
            CoreMeter.meter_role == "grid_export",
            CoreTsMeterReading.ts < to_ts,
        ]
        if from_ts is not None:
            readings_filter.append(CoreTsMeterReading.ts >= from_ts)

        total_grid_export = self.db.scalar(
            select(func.coalesce(func.sum(CoreTsMeterReading.value), Decimal("0")))
            .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
            .where(*readings_filter)
        )

        customer_count = self.db.scalar(
            select(func.count(distinct(Site.customer_id)))
            .join(CoreMeter, CoreMeter.site_id == Site.id)
            .join(CoreTsMeterReading, CoreTsMeterReading.meter_id == CoreMeter.id)
            .where(*readings_filter)
        )

        site_count = self.db.scalar(
            select(func.count(distinct(Site.id)))
            .join(CoreMeter, CoreMeter.site_id == Site.id)
            .join(CoreTsMeterReading, CoreTsMeterReading.meter_id == CoreMeter.id)
            .where(*readings_filter)
        )

        tradable_export = (total_grid_export or Decimal("0")) * self.tradable_factor

        return {
            "period": period,
            "total_grid_export_kwh": total_grid_export or Decimal("0"),
            "tradable_export_kwh": tradable_export,
            "customer_count": customer_count or 0,
            "site_count": site_count or 0,
            "interval_minutes": PORTFOLIO_INTERVAL_MINUTES,
            "safety_factor": self.tradable_factor,
        }

    def export_timeseries(self, from_ts: datetime, to_ts: datetime) -> dict:
        from_ts = from_ts.astimezone(timezone.utc)
        to_ts = to_ts.astimezone(timezone.utc)

        rows = list(
            self.db.execute(
                select(CoreTsMeterReading.ts, func.sum(CoreTsMeterReading.value).label("total_grid_export"))
                .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
                .where(
                    CoreMeter.meter_role == "grid_export",
                    CoreTsMeterReading.ts >= from_ts,
                    CoreTsMeterReading.ts < to_ts,
                )
                .group_by(CoreTsMeterReading.ts)
                .order_by(CoreTsMeterReading.ts.asc())
            )
        )

        export_points = [{"ts": ts, "value": total} for ts, total in rows]
        tradable_points = [{"ts": ts, "value": total * self.tradable_factor} for ts, total in rows]

        return {
            "interval_minutes": PORTFOLIO_INTERVAL_MINUTES,
            "from": from_ts,
            "to": to_ts,
            "series": [
                {"name": "portfolio_grid_export", "unit": "kwh", "points": export_points},
                {"name": "portfolio_tradable_export", "unit": "kwh", "points": tradable_points},
            ],
        }
