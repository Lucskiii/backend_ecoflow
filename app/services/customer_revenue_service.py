from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import (
    CoreBiddingZone,
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
        if not customer_ids:
            return {}

        revenues_by_customer = {customer_id: Decimal("0") for customer_id in customer_ids}
        resolved = self._resolve_target_series()
        if resolved is None:
            return revenues_by_customer
        product, bidding_zone = resolved

        meter_hour_expr = self._hour_bucket_expr(CoreTsMeterReading.ts)
        export_rows = list(
            self.db.execute(
                select(
                    Site.customer_id,
                    meter_hour_expr.label("hour_bucket"),
                    func.sum(CoreTsMeterReading.value).label("export_kwh"),
                )
                .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
                .join(Site, Site.id == CoreMeter.site_id)
                .where(
                    Site.customer_id.in_(customer_ids),
                    CoreMeter.meter_role == "grid_export",
                )
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
