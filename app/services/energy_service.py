from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import CoreMeter, CoreQualityFlag, CoreTsMeterReading, Customer, Site

METER_TYPES = ("load", "grid_import", "grid_export", "pv_generation")
INTERVAL_MINUTES = 15
INTERVAL_SECONDS = INTERVAL_MINUTES * 60


@dataclass
class SimulationResult:
    customer_id: int
    days: int
    sites_processed: int
    readings_created: int
    from_ts: datetime
    to_ts: datetime


class EnergyService:
    def __init__(self, db: Session):
        self.db = db

    def _round_to_interval(self, dt: datetime) -> datetime:
        dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
        minute = (dt.minute // INTERVAL_MINUTES) * INTERVAL_MINUTES
        return dt.replace(minute=minute)

    def _get_or_create_quality_flag(self) -> int:
        quality = self.db.scalar(select(CoreQualityFlag).where(CoreQualityFlag.code == "estimated"))
        if quality is None:
            quality = CoreQualityFlag(code="estimated", description="Simulated/estimated value", severity=0)
            self.db.add(quality)
            self.db.flush()
        return quality.id

    def _get_or_create_sites(self, customer_id: int) -> list[Site]:
        sites = list(self.db.scalars(select(Site).where(Site.customer_id == customer_id).order_by(Site.id)))
        if sites:
            return sites

        site = Site(
            customer_id=customer_id,
            site_code=f"cust-{customer_id}-site-1",
            name=f"Default Site Customer {customer_id}",
            timezone="UTC",
        )
        self.db.add(site)
        self.db.flush()
        return [site]

    def _get_or_create_meters(self, site: Site) -> dict[str, CoreMeter]:
        meters = list(self.db.scalars(select(CoreMeter).where(CoreMeter.site_id == site.id)))
        by_role = {meter.meter_role: meter for meter in meters}

        for meter_type in METER_TYPES:
            if meter_type in by_role:
                continue
            meter = CoreMeter(
                site_id=site.id,
                meter_code=f"site-{site.id}-{meter_type}",
                meter_role=meter_type,
                unit="kWh",
            )
            self.db.add(meter)
            self.db.flush()
            by_role[meter_type] = meter

        return by_role

    def simulate_customer_data(self, customer: Customer, days: int = 30) -> SimulationResult:
        end_ts = self._round_to_interval(datetime.now(timezone.utc))
        start_ts = end_ts - timedelta(days=days)

        quality_flag_id = self._get_or_create_quality_flag()
        sites = self._get_or_create_sites(customer.id)

        site_meters: dict[int, dict[str, CoreMeter]] = {site.id: self._get_or_create_meters(site) for site in sites}

        meter_ids = [meter.id for meters in site_meters.values() for meter in meters.values()]
        if meter_ids:
            self.db.query(CoreTsMeterReading).filter(
                CoreTsMeterReading.meter_id.in_(meter_ids),
                CoreTsMeterReading.ts >= start_ts,
                CoreTsMeterReading.ts < end_ts,
            ).delete(synchronize_session=False)

        readings: list[CoreTsMeterReading] = []
        total_steps = int((end_ts - start_ts).total_seconds() // INTERVAL_SECONDS)

        for site in sites:
            meters = site_meters[site.id]
            base_seed = customer.id * 10000 + site.id
            for step in range(total_steps):
                ts = start_ts + timedelta(seconds=step * INTERVAL_SECONDS)
                hour = ts.hour + ts.minute / 60
                day_of_year = ts.timetuple().tm_yday

                rng = random.Random(base_seed + step)
                daily_factor = 0.95 + 0.1 * math.sin((2 * math.pi / 365) * day_of_year)
                noise = rng.uniform(0.92, 1.08)

                morning_peak = math.exp(-((hour - 7.5) ** 2) / 7)
                evening_peak = math.exp(-((hour - 19) ** 2) / 8)
                night_factor = 0.8 if hour < 5 else 1.0
                load_kwh = max((0.18 + 0.2 * morning_peak + 0.28 * evening_peak) * daily_factor * noise * night_factor, 0)

                if 6 <= hour <= 19:
                    solar_shape = math.sin(math.pi * (hour - 6) / 13)
                    seasonal_solar = 0.55 + 0.35 * math.sin((2 * math.pi / 365) * (day_of_year - 80))
                    cloud_factor = rng.uniform(0.65, 1.05)
                    pv_kwh = max(0.65 * solar_shape * seasonal_solar * cloud_factor, 0)
                else:
                    pv_kwh = 0

                grid_import = max(load_kwh - pv_kwh, 0)
                grid_export = max(pv_kwh - load_kwh, 0)

                values = {
                    "load": load_kwh,
                    "pv_generation": pv_kwh,
                    "grid_import": grid_import,
                    "grid_export": grid_export,
                }

                for meter_type, value in values.items():
                    readings.append(
                        CoreTsMeterReading(
                            meter_id=meters[meter_type].id,
                            ts=ts,
                            quality_flag_id=quality_flag_id,
                            interval_seconds=INTERVAL_SECONDS,
                            value=Decimal(f"{value:.6f}"),
                        )
                    )

        self.db.bulk_save_objects(readings)
        self.db.commit()

        return SimulationResult(
            customer_id=customer.id,
            days=days,
            sites_processed=len(sites),
            readings_created=len(readings),
            from_ts=start_ts,
            to_ts=end_ts,
        )

    def _base_query(self, customer_id: int, from_ts: datetime, to_ts: datetime, site_id: int | None = None):
        query = (
            select(CoreMeter.meter_role, func.sum(CoreTsMeterReading.value))
            .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
            .join(Site, Site.id == CoreMeter.site_id)
            .where(
                Site.customer_id == customer_id,
                CoreTsMeterReading.ts >= from_ts,
                CoreTsMeterReading.ts < to_ts,
            )
            .group_by(CoreMeter.meter_role)
        )
        if site_id is not None:
            query = query.where(Site.id == site_id)
        return query

    def energy_summary(self, customer_id: int, period: str = "today", site_id: int | None = None) -> dict:
        now = datetime.now(timezone.utc)
        if period == "7d":
            from_ts = now - timedelta(days=7)
        elif period == "30d":
            from_ts = now - timedelta(days=30)
        else:
            period = "today"
            from_ts = now.replace(hour=0, minute=0, second=0, microsecond=0)

        rows = list(self.db.execute(self._base_query(customer_id, from_ts, now, site_id)))
        data = {meter_role: total or Decimal("0") for meter_role, total in rows}

        pv = data.get("pv_generation", Decimal("0"))
        export = data.get("grid_export", Decimal("0"))
        self_consumed = max(pv - export, Decimal("0"))
        ratio = float((self_consumed / pv) if pv > 0 else Decimal("0"))

        return {
            "period": period,
            "grid_import_kwh": data.get("grid_import", Decimal("0")),
            "grid_export_kwh": data.get("grid_export", Decimal("0")),
            "load_kwh": data.get("load", Decimal("0")),
            "pv_generation_kwh": pv,
            "self_consumption_ratio": round(ratio, 4),
        }

    def energy_timeseries(
        self,
        customer_id: int,
        from_ts: datetime,
        to_ts: datetime,
        site_id: int | None = None,
    ) -> dict:
        from_ts = from_ts.astimezone(timezone.utc)
        to_ts = to_ts.astimezone(timezone.utc)

        query = (
            select(CoreMeter.meter_role, CoreMeter.unit, CoreTsMeterReading.ts, CoreTsMeterReading.value)
            .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
            .join(Site, Site.id == CoreMeter.site_id)
            .where(
                Site.customer_id == customer_id,
                CoreTsMeterReading.ts >= from_ts,
                CoreTsMeterReading.ts < to_ts,
            )
            .order_by(CoreTsMeterReading.ts.asc())
        )
        if site_id is not None:
            query = query.where(Site.id == site_id)

        rows = list(self.db.execute(query))

        series = {meter_type: {"meter_type": meter_type, "unit": "kwh", "points": []} for meter_type in METER_TYPES}
        for meter_role, unit, ts, value in rows:
            series[meter_role]["unit"] = unit.lower()
            series[meter_role]["points"].append({"ts": ts, "value": value})

        return {
            "interval_minutes": INTERVAL_MINUTES,
            "from": from_ts,
            "to": to_ts,
            "series": list(series.values()),
        }
