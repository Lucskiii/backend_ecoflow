from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.tables import CoreMeter, CoreQualityFlag, CoreTsMeterReading, Site

METER_TYPES = ("load", "grid_import", "grid_export", "pv_generation")
INTERVAL_MINUTES = 15
INTERVAL_SECONDS = INTERVAL_MINUTES * 60
DEFAULT_BACKFILL_DAYS = 30


logger = logging.getLogger(__name__)


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
            latitude=None,
            longitude=None,
        )
        self.db.add(site)
        self.db.flush()
        return [site]

    def _get_or_create_meters(self, site: Site) -> dict[str, CoreMeter]:
        meters = list(self.db.scalars(select(CoreMeter).where(CoreMeter.site_id == site.id)))
        by_role = {meter.meter_role: meter for meter in meters if meter.meter_role in METER_TYPES}

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

    def _get_existing_meters(self, site: Site) -> dict[str, CoreMeter]:
        meters = list(
            self.db.scalars(
                select(CoreMeter)
                .where(CoreMeter.site_id == site.id, CoreMeter.meter_role.in_(METER_TYPES))
                .order_by(CoreMeter.id)
            )
        )
        return {meter.meter_role: meter for meter in meters}

    def _interval_index(self, ts: datetime) -> int:
        return int(ts.astimezone(timezone.utc).timestamp()) // INTERVAL_SECONDS

    def _build_readings(
        self,
        customer_id: int,
        site_id: int,
        meters: dict[str, CoreMeter],
        quality_flag_id: int,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[dict]:
        if start_ts >= end_ts:
            return []

        readings: list[dict] = []
        total_steps = int((end_ts - start_ts).total_seconds() // INTERVAL_SECONDS)
        base_seed = customer_id * 10000 + site_id

        for step in range(total_steps):
            ts = start_ts + timedelta(seconds=step * INTERVAL_SECONDS)
            hour = ts.hour + ts.minute / 60
            day_of_year = ts.timetuple().tm_yday
            interval_index = self._interval_index(ts)

            rng = random.Random(base_seed + interval_index)
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
                meter = meters.get(meter_type)
                if meter is None:
                    continue
                readings.append(
                    {
                        "meter_id": meter.id,
                        "ts": ts,
                        "quality_flag_id": quality_flag_id,
                        "interval_seconds": INTERVAL_SECONDS,
                        "value": Decimal(f"{value:.6f}"),
                    }
                )

        return readings

    def _insert_readings(self, readings: list[dict]) -> None:
        if not readings:
            return

        dialect_name = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect_name == "sqlite":
            stmt = sqlite_insert(CoreTsMeterReading).values(readings).on_conflict_do_nothing(
                index_elements=[CoreTsMeterReading.meter_id, CoreTsMeterReading.ts]
            )
        elif dialect_name == "postgresql":
            stmt = postgresql_insert(CoreTsMeterReading).values(readings).on_conflict_do_nothing(
                index_elements=[CoreTsMeterReading.meter_id, CoreTsMeterReading.ts]
            )
        elif dialect_name.startswith("mysql"):
            stmt = mysql_insert(CoreTsMeterReading).values(readings).prefix_with("IGNORE")
        else:
            stmt = sqlite_insert(CoreTsMeterReading).values(readings).on_conflict_do_nothing(
                index_elements=[CoreTsMeterReading.meter_id, CoreTsMeterReading.ts]
            )

        self.db.execute(stmt)

    def _site_latest_complete_timestamps(self, customer_id: int) -> dict[int, datetime]:
        rows = list(
            self.db.execute(
                select(Site.id, CoreMeter.meter_role, func.max(CoreTsMeterReading.ts))
                .join(CoreMeter, CoreMeter.site_id == Site.id)
                .join(CoreTsMeterReading, CoreTsMeterReading.meter_id == CoreMeter.id)
                .where(Site.customer_id == customer_id, CoreMeter.meter_role.in_(METER_TYPES))
                .group_by(Site.id, CoreMeter.meter_role)
            )
        )

        by_site: dict[int, dict[str, datetime]] = {}
        for site_id, meter_role, latest_ts in rows:
            if latest_ts is None:
                continue
            by_site.setdefault(site_id, {})[meter_role] = latest_ts.astimezone(timezone.utc)

        return {
            site_id: min(role_timestamps.values())
            for site_id, role_timestamps in by_site.items()
            if len(role_timestamps) == len(METER_TYPES)
        }

    def simulate_customer_data(self, customer: Customer, days: int = DEFAULT_BACKFILL_DAYS) -> SimulationResult:
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

        readings: list[dict] = []
        for site in sites:
            readings.extend(
                self._build_readings(
                    customer_id=customer.id,
                    site_id=site.id,
                    meters=site_meters[site.id],
                    quality_flag_id=quality_flag_id,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
            )

        self._insert_readings(readings)
        self.db.commit()

        return SimulationResult(
            customer_id=customer.id,
            days=days,
            sites_processed=len(sites),
            readings_created=len(readings),
            from_ts=start_ts,
            to_ts=end_ts,
        )

    def customer_has_energy_data(self, customer_id: int) -> bool:
        has_data_query = (
            select(CoreTsMeterReading.meter_id)
            .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
            .join(Site, Site.id == CoreMeter.site_id)
            .where(Site.customer_id == customer_id)
            .limit(1)
        )
        return self.db.scalar(has_data_query) is not None

    def backfill_customer_data_to_now(self, customer: Customer, days: int = DEFAULT_BACKFILL_DAYS) -> SimulationResult | None:
        end_ts = self._round_to_interval(datetime.now(timezone.utc))
        if not self.customer_has_energy_data(customer.id):
            return self.simulate_customer_data(customer, days=days)

        quality_flag_id = self._get_or_create_quality_flag()
        sites = self._get_or_create_sites(customer.id)
        latest_complete_by_site = self._site_latest_complete_timestamps(customer.id)

        total_readings_created = 0
        sites_processed = 0
        earliest_start_ts: datetime | None = None

        for site in sites:
            meters = self._get_existing_meters(site)
            if len(meters) != len(METER_TYPES):
                logger.info(
                    "Skipping login backfill for customer id=%s site id=%s because only %s/%s synthetic roles exist",
                    customer.id,
                    site.id,
                    len(meters),
                    len(METER_TYPES),
                )
                continue

            latest_complete_ts = latest_complete_by_site.get(site.id)
            if latest_complete_ts is None:
                start_ts = end_ts - timedelta(days=days)
            else:
                start_ts = latest_complete_ts + timedelta(seconds=INTERVAL_SECONDS)

            start_ts = self._round_to_interval(start_ts)
            if start_ts >= end_ts:
                continue

            readings = self._build_readings(
                customer_id=customer.id,
                site_id=site.id,
                meters=meters,
                quality_flag_id=quality_flag_id,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            self._insert_readings(readings)

            total_readings_created += len(readings)
            sites_processed += 1
            earliest_start_ts = start_ts if earliest_start_ts is None else min(earliest_start_ts, start_ts)

        self.db.commit()

        if sites_processed == 0:
            return None

        return SimulationResult(
            customer_id=customer.id,
            days=max((end_ts - earliest_start_ts).days, 0) if earliest_start_ts is not None else 0,
            sites_processed=sites_processed,
            readings_created=total_readings_created,
            from_ts=earliest_start_ts or end_ts,
            to_ts=end_ts,
        )

    def ensure_demo_energy_data_for_all_customers(self, days: int = 30) -> None:
        customers = list(self.db.scalars(select(Customer).order_by(Customer.id)))
        logger.info("Auto energy simulation: found %s customer(s)", len(customers))

        for customer in customers:
            if self.customer_has_energy_data(customer.id):
                logger.info(
                    "Auto energy simulation: skipped customer id=%s email=%s (existing data)",
                    customer.id,
                    customer.email,
                )
                continue

            result = self.simulate_customer_data(customer, days=days)
            logger.info(
                "Auto energy simulation: simulated customer id=%s email=%s readings=%s days=%s",
                customer.id,
                customer.email,
                result.readings_created,
                days,
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
            if meter_role not in series:
                series[meter_role] = {"meter_type": meter_role, "unit": "kwh", "points": []}
            series[meter_role]["unit"] = unit.lower()
            series[meter_role]["points"].append({"ts": ts, "value": value})

        return {
            "interval_minutes": INTERVAL_MINUTES,
            "from": from_ts,
            "to": to_ts,
            "series": list(series.values()),
        }
