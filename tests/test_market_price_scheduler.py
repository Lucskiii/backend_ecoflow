import threading

from app.services.market_price_scheduler import MarketPriceScheduler


def test_start_clears_stop_event_before_thread_run(monkeypatch) -> None:
    scheduler = MarketPriceScheduler()
    scheduler.settings.market_price_scheduler_enabled = True
    scheduler.settings.market_price_refresh_minutes = 60
    scheduler._stop_event.set()

    observed_stop_flag: list[bool] = []
    finished = threading.Event()

    def fake_run_loop() -> None:
        observed_stop_flag.append(scheduler._stop_event.is_set())
        finished.set()

    monkeypatch.setattr(scheduler, "_run_loop", fake_run_loop)

    scheduler.start()
    finished.wait(timeout=2)

    assert observed_stop_flag == [False]


def test_start_rejects_non_positive_refresh_interval(monkeypatch) -> None:
    scheduler = MarketPriceScheduler()
    scheduler.settings.market_price_scheduler_enabled = True
    scheduler.settings.market_price_refresh_minutes = 0

    started = {"value": False}

    original_thread = threading.Thread

    class DummyThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self) -> None:
            started["value"] = True

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(threading, "Thread", DummyThread)
    try:
        scheduler.start()
    finally:
        monkeypatch.setattr(threading, "Thread", original_thread)

    assert started["value"] is False
    assert scheduler._thread is None
