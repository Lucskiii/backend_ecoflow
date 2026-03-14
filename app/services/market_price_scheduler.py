from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.database import SessionLocal
from app.services.market_price_service import MarketPriceService

logger = logging.getLogger(__name__)


class MarketPriceScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.settings.market_price_scheduler_enabled:
            logger.info(
                "Market price scheduler disabled via MARKET_PRICE_SCHEDULER_ENABLED"
            )
            return
        if self._thread and self._thread.is_alive():
            return

        refresh_minutes = self.settings.market_price_refresh_minutes
        if refresh_minutes <= 0:
            logger.error(
                "Invalid MARKET_PRICE_REFRESH_MINUTES=%s, scheduler not started",
                refresh_minutes,
            )
            return

        self._stop_event.clear()
        logger.info(
            "Starting market price scheduler with interval=%s minutes",
            refresh_minutes,
        )
        self._thread = threading.Thread(
            target=self._run_loop, name="market-price-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._run_refresh_cycle()
        while not self._stop_event.wait(
            self.settings.market_price_refresh_minutes * 60
        ):
            self._run_refresh_cycle()

    def _run_refresh_cycle(self) -> None:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=2)
            inserted = MarketPriceService(db).refresh_prices(start=start, end=None)
            logger.info("Market price scheduler refresh done inserted=%s", inserted)
        except Exception:
            logger.exception("Market price scheduler refresh failed")
            db.rollback()
        finally:
            db.close()
