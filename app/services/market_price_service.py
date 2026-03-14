from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.tables import (
    CoreBiddingZone,
    CoreMarket,
    CoreMarketProduct,
    CoreTsMarketPrice,
)

logger = logging.getLogger(__name__)


@dataclass
class AwattarPricePoint:
    ts_utc: datetime
    price_eur_mwh: Decimal
    unit: str


class MarketPriceService:
    SOURCE = "awattar"
    MARKET_CODE = "AWATTAR"
    MARKET_NAME = "aWATTar"
    PRODUCT_CODE = "AT_DAY_AHEAD"
    PRODUCT_NAME = "AT day-ahead"
    BIDDING_ZONE_CODE = "AT"
    BIDDING_ZONE_NAME = "Austria"
    GRANULARITY_MINUTES = 60

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _fetch_marketdata(
        self, start_ms: int | None = None, end_ms: int | None = None
    ) -> list[AwattarPricePoint]:
        params: dict[str, int] = {}
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms

        response = requests.get(
            self.settings.awattar_api_url, params=params or None, timeout=15
        )
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", [])
        points: list[AwattarPricePoint] = []
        for item in data:
            ts_utc = datetime.fromtimestamp(
                item["start_timestamp"] / 1000, tz=timezone.utc
            )
            points.append(
                AwattarPricePoint(
                    ts_utc=ts_utc,
                    price_eur_mwh=Decimal(str(item["marketprice"])),
                    unit=str(item.get("unit", "Eur/MWh")),
                )
            )
        return points

    def _get_or_create_market(self) -> CoreMarket:
        market = self.db.scalar(
            select(CoreMarket).where(CoreMarket.code == self.MARKET_CODE)
        )
        if market is None:
            market = CoreMarket(code=self.MARKET_CODE, name=self.MARKET_NAME)
            self.db.add(market)
            self.db.flush()
        return market

    def _get_or_create_product(self, market_id: int) -> CoreMarketProduct:
        product = self.db.scalar(
            select(CoreMarketProduct).where(
                CoreMarketProduct.market_id == market_id,
                CoreMarketProduct.product_code == self.PRODUCT_CODE,
            )
        )
        if product is None:
            product = CoreMarketProduct(
                market_id=market_id,
                product_code=self.PRODUCT_CODE,
                granularity_minutes=self.GRANULARITY_MINUTES,
                direction=None,
            )
            self.db.add(product)
            self.db.flush()
        return product

    def _get_or_create_bidding_zone(self) -> CoreBiddingZone:
        bidding_zone = self.db.scalar(
            select(CoreBiddingZone).where(
                CoreBiddingZone.code == self.BIDDING_ZONE_CODE
            )
        )
        if bidding_zone is None:
            bidding_zone = CoreBiddingZone(
                code=self.BIDDING_ZONE_CODE, name=self.BIDDING_ZONE_NAME
            )
            self.db.add(bidding_zone)
            self.db.flush()
        return bidding_zone

    def refresh_prices(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> int:
        start_ms = (
            int(start.astimezone(timezone.utc).timestamp() * 1000)
            if start is not None
            else None
        )
        end_ms = (
            int(end.astimezone(timezone.utc).timestamp() * 1000)
            if end is not None
            else None
        )

        points = self._fetch_marketdata(start_ms=start_ms, end_ms=end_ms)
        if not points:
            return 0

        market = self._get_or_create_market()
        product = self._get_or_create_product(market.id)
        bidding_zone = self._get_or_create_bidding_zone()

        min_ts = min(point.ts_utc for point in points)
        max_ts = max(point.ts_utc for point in points)
        existing_ts = set(
            self.db.scalars(
                select(CoreTsMarketPrice.ts).where(
                    CoreTsMarketPrice.market_product_id == product.id,
                    CoreTsMarketPrice.bidding_zone_id == bidding_zone.id,
                    CoreTsMarketPrice.ts >= min_ts,
                    CoreTsMarketPrice.ts <= max_ts,
                )
            )
        )

        inserted = 0
        for point in points:
            if point.ts_utc in existing_ts:
                continue

            self.db.add(
                CoreTsMarketPrice(
                    market_product_id=product.id,
                    bidding_zone_id=bidding_zone.id,
                    ts=point.ts_utc,
                    price=point.price_eur_mwh,
                    currency="EUR",
                )
            )
            inserted += 1

        self.db.commit()
        logger.info(
            "Market price refresh complete source=%s inserted=%s", self.SOURCE, inserted
        )
        return inserted

    def get_prices(self, from_ts: datetime, to_ts: datetime) -> dict:
        market = self.db.scalar(
            select(CoreMarket).where(CoreMarket.code == self.MARKET_CODE)
        )
        if market is None:
            return {
                "source": self.SOURCE,
                "product": self.PRODUCT_NAME,
                "unit": "Eur/MWh",
                "from": from_ts,
                "to": to_ts,
                "points": [],
            }

        product = self.db.scalar(
            select(CoreMarketProduct).where(
                CoreMarketProduct.market_id == market.id,
                CoreMarketProduct.product_code == self.PRODUCT_CODE,
            )
        )
        bidding_zone = self.db.scalar(
            select(CoreBiddingZone).where(
                CoreBiddingZone.code == self.BIDDING_ZONE_CODE
            )
        )
        if product is None or bidding_zone is None:
            return {
                "source": self.SOURCE,
                "product": self.PRODUCT_NAME,
                "unit": "Eur/MWh",
                "from": from_ts,
                "to": to_ts,
                "points": [],
            }

        rows = self.db.execute(
            select(CoreTsMarketPrice.ts, CoreTsMarketPrice.price)
            .where(
                CoreTsMarketPrice.market_product_id == product.id,
                CoreTsMarketPrice.bidding_zone_id == bidding_zone.id,
                CoreTsMarketPrice.ts >= from_ts,
                CoreTsMarketPrice.ts < to_ts,
            )
            .order_by(CoreTsMarketPrice.ts.asc())
        )

        points = [{"ts": ts, "price_eur_mwh": price} for ts, price in rows]
        return {
            "source": self.SOURCE,
            "product": self.PRODUCT_NAME,
            "unit": "Eur/MWh",
            "from": from_ts,
            "to": to_ts,
            "points": points,
        }

    def get_latest_window(self, hours: int = 24) -> dict:
        to_ts = datetime.now(timezone.utc)
        from_ts = to_ts - timedelta(hours=hours)
        return self.get_prices(from_ts=from_ts, to_ts=to_ts)
