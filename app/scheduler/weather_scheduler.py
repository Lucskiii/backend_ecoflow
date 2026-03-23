from __future__ import annotations

import logging
import threading

from app.config import get_settings
from app.database import SessionLocal
from app.services.weather_ingestion_service import WeatherIngestionService

logger = logging.getLogger(__name__)


class WeatherScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.settings.weather_scheduler_enabled:
            logger.info("Weather scheduler disabled via WEATHER_SCHEDULER_ENABLED")
            return
        if self._thread and self._thread.is_alive():
            return
        if self.settings.weather_scheduler_interval_minutes <= 0:
            logger.error(
                "Invalid WEATHER_SCHEDULER_INTERVAL_MINUTES=%s, scheduler not started",
                self.settings.weather_scheduler_interval_minutes,
            )
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="weather-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._run_sync_cycle()
        while not self._stop_event.wait(self.settings.weather_scheduler_interval_minutes * 60):
            self._run_sync_cycle()

    def _run_sync_cycle(self) -> None:
        db = SessionLocal()
        try:
            result = WeatherIngestionService(db).sync_missing_weather()
            logger.info("Weather scheduler sync complete rows_inserted=%s failures=%s", result["rows_inserted"], len(result["failures"]))
        except Exception:
            logger.exception("Weather scheduler sync failed")
            db.rollback()
        finally:
            db.close()
