from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import (
    CoreBiddingZone,
    CoreCustomerRevenuePeriod,
    CoreMarket,
    CoreMarketProduct,
    CoreMeter,
    CoreTsMarketPrice,
    CoreTsMeterReading,
    Site,
)


class CustomerRevenueService:
    MARKET_CODE = "AWATTAR"
    PRODUCT_CODE = "DE_DAY_AHEAD"
    BIDDING_ZONE_CODE = "DE"

    def __init__(self, db: Session):
        self.db = db

    def _hour_bucket_expr(self, column):
        dialect_name = self.db.get_bind().dialect.name
        if dialect_name == "sqlite":
            return func.strftime("%Y-%m-%d %H:00:00", column)
        if dialect_name == "postgresql":
            return func.date_trunc("hour", column)
        return func.date_format(column, "%Y-%m-%d %H:00:00")

    def _resolve_target_series(self) -> tuple[CoreMarketProduct, CoreBiddingZone] | None:
        product = self.db.scalar(
            select(CoreMarketProduct)
            .join(CoreMarket, CoreMarket.id == CoreMarketProduct.market_id)
            .where(
                CoreMarket.code == self.MARKET_CODE,
                CoreMarketProduct.product_code == self.PRODUCT_CODE,
            )
        )
        bidding_zone = self.db.scalar(
            select(CoreBiddingZone).where(CoreBiddingZone.code == self.BIDDING_ZONE_CODE)
        )
        if product is None or bidding_zone is None:
            return None
        return product, bidding_zone

    def calculate_for_customers(self, customer_ids: list[int]) -> dict[int, Decimal]:
        return self.calculate_for_customers_in_range(customer_ids=customer_ids, from_ts=None, to_ts=None)

    def calculate_for_customers_in_range(
        self,
        customer_ids: list[int],
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> dict[int, Decimal]:
        if not customer_ids:
            return {}

        revenues_by_customer = {customer_id: Decimal("0") for customer_id in customer_ids}
        resolved = self._resolve_target_series()
        if resolved is None:
            return revenues_by_customer
        product, bidding_zone = resolved

        to_ts = to_ts or datetime.now(timezone.utc)
        meter_hour_expr = self._hour_bucket_expr(CoreTsMeterReading.ts)
        filters = [
            Site.customer_id.in_(customer_ids),
            CoreMeter.meter_role == "grid_export",
            CoreTsMeterReading.ts < to_ts,
        ]
        if from_ts is not None:
            filters.append(CoreTsMeterReading.ts >= from_ts)
        export_rows = list(
            self.db.execute(
                select(
                    Site.customer_id,
                    meter_hour_expr.label("hour_bucket"),
                    func.sum(CoreTsMeterReading.value).label("export_kwh"),
                )
                .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
                .join(Site, Site.id == CoreMeter.site_id)
                .where(*filters)
                .group_by(Site.customer_id, meter_hour_expr)
            )
        )
        if not export_rows:
            return revenues_by_customer

        hour_buckets = list({hour_bucket for _, hour_bucket, _ in export_rows})
        price_hour_expr = self._hour_bucket_expr(CoreTsMarketPrice.ts)
        price_rows = list(
            self.db.execute(
                select(price_hour_expr.label("hour_bucket"), CoreTsMarketPrice.price)
                .where(
                    CoreTsMarketPrice.market_product_id == product.id,
                    CoreTsMarketPrice.bidding_zone_id == bidding_zone.id,
                    CoreTsMarketPrice.ts < to_ts,
                    price_hour_expr.in_(hour_buckets),
                )
            )
        )
        price_by_hour: dict[Any, Decimal] = {hour_bucket: price for hour_bucket, price in price_rows}

        for customer_id, hour_bucket, export_kwh in export_rows:
            price_eur_mwh = price_by_hour.get(hour_bucket)
            if price_eur_mwh is None:
                continue
            revenues_by_customer[customer_id] += (export_kwh * price_eur_mwh) / Decimal("1000")

        return {
            customer_id: revenue.quantize(Decimal("0.000001"))
            for customer_id, revenue in revenues_by_customer.items()
        }

    def calculate_for_customer(self, customer_id: int) -> Decimal:
        return self.calculate_for_customers([customer_id]).get(customer_id, Decimal("0"))

    def calculate_for_customer_in_range(
        self, customer_id: int, from_ts: datetime | None, to_ts: datetime | None
    ) -> Decimal:
        return self.calculate_for_customers_in_range([customer_id], from_ts=from_ts, to_ts=to_ts).get(
            customer_id, Decimal("0")
        )

    def get_or_create_period_snapshots(self, customer_id: int) -> list[CoreCustomerRevenuePeriod]:
        now = datetime.now(timezone.utc)
        period_ranges = {
            "all": datetime(1970, 1, 1, tzinfo=timezone.utc),
            "30d": now - timedelta(days=30),
            "7d": now - timedelta(days=7),
        }
        snapshots: list[CoreCustomerRevenuePeriod] = []
        next_sqlite_id: int | None = None
        if self.db.get_bind().dialect.name == "sqlite":
            next_sqlite_id = int(
                self.db.scalar(select(func.coalesce(func.max(CoreCustomerRevenuePeriod.id), 0) + 1)) or 1
            )
        for period_code, from_ts in period_ranges.items():
            revenue = self.calculate_for_customer_in_range(customer_id, from_ts=from_ts, to_ts=now)
            snapshot = self.db.scalar(
                select(CoreCustomerRevenuePeriod).where(
                    CoreCustomerRevenuePeriod.customer_id == customer_id,
                    CoreCustomerRevenuePeriod.period_code == period_code,
                )
            )
            if snapshot is None:
                snapshot_id = next_sqlite_id
                if next_sqlite_id is not None:
                    next_sqlite_id += 1
                snapshot = CoreCustomerRevenuePeriod(
                    id=snapshot_id,
                    customer_id=customer_id,
                    period_code=period_code,
                    period_start=from_ts.replace(tzinfo=None),
                    period_end=now.replace(tzinfo=None),
                    revenue_eur=revenue,
                    calculated_at=now.replace(tzinfo=None),
                )
                self.db.add(snapshot)
            else:
                snapshot.period_start = from_ts.replace(tzinfo=None)
                snapshot.period_end = now.replace(tzinfo=None)
                snapshot.revenue_eur = revenue
                snapshot.calculated_at = now.replace(tzinfo=None)
            snapshots.append(snapshot)

        self.db.flush()
        return snapshots
