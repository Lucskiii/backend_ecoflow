from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db_dialect import is_mysql_family
from app.models.tables import CoreMarketProduct, CoreTsMarketPrice


@dataclass
class MarketProductBackfillTarget:
    market_product_id: int
    bidding_zone_id: int
    granularity_minutes: int
    product_code: str | None


@dataclass
class MarketPriceUpsertRow:
    market_product_id: int
    bidding_zone_id: int
    ts: datetime
    price: Decimal
    currency: str = "EUR"


class MarketPriceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_available_market_products(self) -> list[MarketProductBackfillTarget]:
        stmt: Select[tuple[int, int, int, str | None]] = (
            select(
                CoreTsMarketPrice.market_product_id,
                CoreTsMarketPrice.bidding_zone_id,
                CoreMarketProduct.granularity_minutes,
                CoreMarketProduct.product_code,
            )
            .join(
                CoreMarketProduct,
                CoreMarketProduct.id == CoreTsMarketPrice.market_product_id,
            )
            .group_by(
                CoreTsMarketPrice.market_product_id,
                CoreTsMarketPrice.bidding_zone_id,
                CoreMarketProduct.granularity_minutes,
                CoreMarketProduct.product_code,
            )
            .order_by(CoreTsMarketPrice.market_product_id, CoreTsMarketPrice.bidding_zone_id)
        )
        rows = self.db.execute(stmt).all()
        return [
            MarketProductBackfillTarget(
                market_product_id=row[0],
                bidding_zone_id=row[1],
                granularity_minutes=row[2],
                product_code=row[3],
            )
            for row in rows
        ]

    def get_earliest_timestamps_by_product(
        self, product_ids: list[int]
    ) -> dict[int, datetime]:
        if not product_ids:
            return {}
        stmt = (
            select(
                CoreTsMarketPrice.market_product_id,
                func.min(CoreTsMarketPrice.ts),
            )
            .where(CoreTsMarketPrice.market_product_id.in_(product_ids))
            .group_by(CoreTsMarketPrice.market_product_id)
        )
        rows = self.db.execute(stmt).all()
        return {int(product_id): min_ts for product_id, min_ts in rows if min_ts is not None}

    def bulk_upsert_prices(self, rows: list[MarketPriceUpsertRow]) -> int:
        if not rows:
            return 0

        table = CoreTsMarketPrice.__table__
        payload = [
            {
                "market_product_id": row.market_product_id,
                "bidding_zone_id": row.bidding_zone_id,
                "ts": row.ts,
                "price": row.price,
                "currency": row.currency,
            }
            for row in rows
        ]

        dialect_name = self.db.get_bind().dialect.name
        if is_mysql_family(dialect_name):
            stmt = mysql_insert(table).values(payload).prefix_with("IGNORE")
            result = self.db.execute(stmt)
            return int(result.rowcount or 0)

        # sqlite/test fallback with OR IGNORE for idempotent inserts.
        stmt = table.insert().prefix_with("OR IGNORE").values(payload)
        result = self.db.execute(stmt)
        return int(result.rowcount or 0)
