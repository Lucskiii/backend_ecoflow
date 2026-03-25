from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.market_price_repository import (
    MarketPriceRepository,
    MarketPriceUpsertRow,
)
from app.repositories.raw_ingestion_repository import RawIngestionRepository
from app.services.market_price_service import MarketPriceService

logger = logging.getLogger(__name__)


@dataclass
class MarketPriceBackfillSummary:
    processed_products: int
    inserted_rows: int
    skipped_products: int
    failed_products: int
    target_start_date: date
    earliest_observed_ts: datetime | None
    latest_backfilled_ts: datetime | None


class MarketPriceBackfillService:
    SOURCE_SYSTEM = "market-price-backfill"

    def __init__(self, db: Session):
        self.db = db
        self.market_price_service = MarketPriceService(db)
        self.market_price_repository = MarketPriceRepository(db)
        self.raw_ingestion_repository = RawIngestionRepository(db)

    def run_historical_backfill(self, target_start_date: date) -> MarketPriceBackfillSummary:
        targets = self.market_price_repository.list_available_market_products()
        if not targets:
            return MarketPriceBackfillSummary(
                processed_products=0,
                inserted_rows=0,
                skipped_products=0,
                failed_products=0,
                target_start_date=target_start_date,
                earliest_observed_ts=None,
                latest_backfilled_ts=None,
            )

        product_ids = [target.market_product_id for target in targets]
        earliest_by_product = self.market_price_repository.get_earliest_timestamps_by_product(product_ids)

        processed_products = 0
        skipped_products = 0
        failed_products = 0
        inserted_rows = 0
        earliest_observed_ts: datetime | None = None
        latest_backfilled_ts: datetime | None = None

        target_start_dt = datetime.combine(target_start_date, time.min)

        for target in targets:
            earliest_ts = earliest_by_product.get(target.market_product_id)
            logger.info(
                "Market price backfill target product_id=%s bidding_zone_id=%s earliest_ts=%s",
                target.market_product_id,
                target.bidding_zone_id,
                earliest_ts,
            )

            if earliest_ts is None:
                skipped_products += 1
                logger.info(
                    "Skipping product_id=%s because no market prices exist yet",
                    target.market_product_id,
                )
                continue

            processed_products += 1
            if earliest_observed_ts is None or earliest_ts < earliest_observed_ts:
                earliest_observed_ts = earliest_ts

            if target_start_dt >= earliest_ts:
                skipped_products += 1
                logger.info(
                    "No backfill needed for product_id=%s, target_start_date=%s is not earlier than earliest_ts=%s",
                    target.market_product_id,
                    target_start_date,
                    earliest_ts,
                )
                continue

            interval = timedelta(minutes=target.granularity_minutes)
            missing_from = target_start_dt.replace(tzinfo=timezone.utc)
            missing_to = (earliest_ts - interval).replace(tzinfo=timezone.utc)
            logger.info(
                "Backfill missing range product_id=%s from=%s to=%s interval_minutes=%s",
                target.market_product_id,
                missing_from,
                missing_to,
                target.granularity_minutes,
            )

            try:
                fetch_result = self.market_price_service._fetch_marketdata(
                    start_ms=int(missing_from.timestamp() * 1000),
                    end_ms=int(missing_to.timestamp() * 1000),
                )
                rows = [
                    MarketPriceUpsertRow(
                        market_product_id=target.market_product_id,
                        bidding_zone_id=target.bidding_zone_id,
                        ts=self.market_price_service._normalize_ts_utc(point.ts_utc),
                        price=point.price_eur_mwh,
                    )
                    for point in fetch_result.points
                ]
                inserted = self.market_price_repository.bulk_upsert_prices(rows)
                inserted_rows += inserted
                self.db.commit()
                logger.info(
                    "Backfill insert complete product_id=%s fetched=%s inserted=%s",
                    target.market_product_id,
                    len(rows),
                    inserted,
                )
                if rows:
                    product_latest_ts = max(row.ts for row in rows)
                    if latest_backfilled_ts is None or product_latest_ts > latest_backfilled_ts:
                        latest_backfilled_ts = product_latest_ts
            except Exception:
                failed_products += 1
                self.db.rollback()
                logger.exception(
                    "Backfill failed for product_id=%s; continuing with next product",
                    target.market_product_id,
                )

        notes = (
            f"historical backfill target_start_date={target_start_date} "
            f"processed={processed_products} skipped={skipped_products} failed={failed_products} inserted={inserted_rows}"
        )
        self.raw_ingestion_repository.create_batch_entry(
            source_system=self.SOURCE_SYSTEM,
            source_topic="market_prices",
            payload_format="json",
            notes=notes,
        )
        self.db.commit()

        return MarketPriceBackfillSummary(
            processed_products=processed_products,
            inserted_rows=inserted_rows,
            skipped_products=skipped_products,
            failed_products=failed_products,
            target_start_date=target_start_date,
            earliest_observed_ts=earliest_observed_ts,
            latest_backfilled_ts=latest_backfilled_ts,
        )
