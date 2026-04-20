from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import (
    Asset,
    BiDimAsset,
    BiDimMarketProduct,
    BiDimSite,
    BiDimTime,
    BiFactEnergyInterval,
    BiFactMarketPrice,
    CoreMarket,
    CoreMarketProduct,
    CoreMeter,
    CoreTsMarketPrice,
    CoreTsMeterReading,
    Site,
)


class BiPrototypeService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _ensure_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None or ts.utcoffset() is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @staticmethod
    def _time_key(ts: datetime) -> int:
        return int(ts.timestamp() // 60)

    def sync_from_core(self, from_ts: datetime, to_ts: datetime) -> dict:
        from_ts = self._ensure_utc(from_ts)
        to_ts = self._ensure_utc(to_ts)

        dim_time_count = 0
        dim_site_count = 0
        dim_market_product_count = 0
        fact_energy_count = 0
        fact_market_price_count = 0

        ts_candidates = self.db.execute(
            select(CoreTsMeterReading.ts)
            .where(CoreTsMeterReading.ts >= from_ts, CoreTsMeterReading.ts < to_ts)
            .union(
                select(CoreTsMarketPrice.ts).where(
                    CoreTsMarketPrice.ts >= from_ts,
                    CoreTsMarketPrice.ts < to_ts,
                )
            )
        ).all()

        for (ts_raw,) in ts_candidates:
            ts = self._ensure_utc(ts_raw)
            self.db.merge(
                BiDimTime(
                    time_key=self._time_key(ts),
                    ts=ts.replace(tzinfo=None),
                    date=ts.date(),
                    hour=ts.hour,
                    quarter_hour=(ts.minute // 15) * 15,
                )
            )
            dim_time_count += 1

        for site_id, customer_id, name in self.db.execute(select(Site.id, Site.customer_id, Site.name)):
            self.db.merge(
                BiDimSite(
                    site_key=site_id,
                    site_id=site_id,
                    customer_key=customer_id,
                    site_name=name,
                )
            )
            dim_site_count += 1


        for asset_id, site_id, asset_type in self.db.execute(select(Asset.id, Asset.site_id, Asset.asset_type)):
            self.db.merge(
                BiDimAsset(
                    asset_key=asset_id,
                    asset_id=asset_id,
                    site_key=site_id,
                    asset_type=asset_type,
                )
            )

        market_rows = self.db.execute(
            select(CoreMarketProduct.id, CoreMarket.code, CoreMarketProduct.product_code)
            .join(CoreMarket, CoreMarket.id == CoreMarketProduct.market_id)
        ).all()

        for product_id, market_code, product_code in market_rows:
            self.db.merge(
                BiDimMarketProduct(
                    market_product_key=product_id,
                    market_product_id=product_id,
                    market_code=market_code,
                    product_code=product_code,
                )
            )
            dim_market_product_count += 1

        energy_rows = self.db.execute(
            select(
                CoreTsMeterReading.ts,
                CoreMeter.site_id,
                CoreMeter.asset_id,
                func.sum(CoreTsMeterReading.value).label("energy_kwh"),
            )
            .join(CoreMeter, CoreMeter.id == CoreTsMeterReading.meter_id)
            .where(
                CoreMeter.site_id.is_not(None),
                CoreMeter.asset_id.is_not(None),
                CoreTsMeterReading.ts >= from_ts,
                CoreTsMeterReading.ts < to_ts,
            )
            .group_by(CoreTsMeterReading.ts, CoreMeter.site_id, CoreMeter.asset_id)
        ).all()

        for ts_raw, site_id, asset_id, energy_kwh in energy_rows:
            if site_id is None or asset_id is None:
                continue
            ts = self._ensure_utc(ts_raw)
            self.db.merge(
                BiFactEnergyInterval(
                    time_key=self._time_key(ts),
                    site_key=site_id,
                    asset_key=asset_id,
                    quality_key=None,
                    energy_kwh=energy_kwh or Decimal("0"),
                )
            )
            fact_energy_count += 1

        market_price_rows = self.db.execute(
            select(
                CoreTsMarketPrice.ts,
                CoreTsMarketPrice.market_product_id,
                CoreTsMarketPrice.bidding_zone_id,
                CoreTsMarketPrice.price,
            ).where(CoreTsMarketPrice.ts >= from_ts, CoreTsMarketPrice.ts < to_ts)
        ).all()

        for ts_raw, product_id, bidding_zone_id, price in market_price_rows:
            ts = self._ensure_utc(ts_raw)
            self.db.merge(
                BiFactMarketPrice(
                    time_key=self._time_key(ts),
                    market_product_key=product_id,
                    bidding_zone_id=bidding_zone_id,
                    price=price,
                )
            )
            fact_market_price_count += 1

        self.db.commit()

        return {
            "from": from_ts,
            "to": to_ts,
            "inserted_or_updated_dim_time": dim_time_count,
            "inserted_or_updated_dim_site": dim_site_count,
            "inserted_or_updated_dim_market_product": dim_market_product_count,
            "inserted_or_updated_fact_energy_interval": fact_energy_count,
            "inserted_or_updated_fact_market_price": fact_market_price_count,
        }

    def energy_trend(self, from_ts: datetime, to_ts: datetime, site_key: int | None = None) -> dict:
        from_ts = self._ensure_utc(from_ts)
        to_ts = self._ensure_utc(to_ts)

        stmt = (
            select(BiDimTime.ts, func.sum(BiFactEnergyInterval.energy_kwh).label("value"))
            .join(BiFactEnergyInterval, BiFactEnergyInterval.time_key == BiDimTime.time_key)
            .where(BiDimTime.ts >= from_ts.replace(tzinfo=None), BiDimTime.ts < to_ts.replace(tzinfo=None))
            .group_by(BiDimTime.ts)
            .order_by(BiDimTime.ts.asc())
        )
        if site_key is not None:
            stmt = stmt.where(BiFactEnergyInterval.site_key == site_key)

        points = [
            {"ts": ts.replace(tzinfo=timezone.utc), "value": value or Decimal("0")}
            for ts, value in self.db.execute(stmt).all()
        ]
        return {
            "from": from_ts,
            "to": to_ts,
            "site_key": site_key,
            "points": points,
        }

    def price_trend(
        self,
        from_ts: datetime,
        to_ts: datetime,
        market_product_key: int | None = None,
        bidding_zone_id: int | None = None,
    ) -> dict:
        from_ts = self._ensure_utc(from_ts)
        to_ts = self._ensure_utc(to_ts)

        stmt = (
            select(BiDimTime.ts, func.avg(BiFactMarketPrice.price).label("value"))
            .join(BiFactMarketPrice, BiFactMarketPrice.time_key == BiDimTime.time_key)
            .where(BiDimTime.ts >= from_ts.replace(tzinfo=None), BiDimTime.ts < to_ts.replace(tzinfo=None))
            .group_by(BiDimTime.ts)
            .order_by(BiDimTime.ts.asc())
        )
        if market_product_key is not None:
            stmt = stmt.where(BiFactMarketPrice.market_product_key == market_product_key)
        if bidding_zone_id is not None:
            stmt = stmt.where(BiFactMarketPrice.bidding_zone_id == bidding_zone_id)

        points = [
            {"ts": ts.replace(tzinfo=timezone.utc), "value": value or Decimal("0")}
            for ts, value in self.db.execute(stmt).all()
        ]

        return {
            "from": from_ts,
            "to": to_ts,
            "market_product_key": market_product_key,
            "bidding_zone_id": bidding_zone_id,
            "points": points,
        }
