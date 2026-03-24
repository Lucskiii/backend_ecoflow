from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.services.weather_ingestion_service import WeatherIngestionService


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []

    def fetch_historical_hourly(self, latitude, longitude, start_date, end_date):
        self.calls.append(("historical", start_date, end_date))
        return self._result(start_date)

    def fetch_recent_hourly(self, latitude, longitude, start_date, end_date):
        self.calls.append(("recent", start_date, end_date))
        return self._result(start_date)

    @staticmethod
    def _result(start_date: date):
        from app.clients.open_meteo_client import OpenMeteoHourlyPoint, OpenMeteoResult

        point = OpenMeteoHourlyPoint(
            ts_utc=datetime.combine(start_date, datetime.min.time()),
            temp_c=Decimal("12.5"),
            wind_ms=Decimal("5.1"),
            ghi_wm2=Decimal("100.0"),
            cloud_pct=Decimal("42.0"),
        )
        return OpenMeteoResult(
            source_url="https://example.test/weather",
            model_name="test-model",
            points=[point],
            raw_payload={"hourly": {"time": [start_date.isoformat()]}},
        )


class FailingRecentClient(FakeClient):
    def fetch_recent_hourly(self, latitude, longitude, start_date, end_date):
        self.calls.append(("recent", start_date, end_date))
        raise RuntimeError("recent endpoint failed")


class EmptyRecentClient(FakeClient):
    def fetch_recent_hourly(self, latitude, longitude, start_date, end_date):
        self.calls.append(("recent", start_date, end_date))
        from app.clients.open_meteo_client import OpenMeteoHourlyPoint, OpenMeteoResult

        out_of_range_point = OpenMeteoHourlyPoint(
            ts_utc=datetime.combine(end_date, datetime.max.time()),
            temp_c=Decimal("12.5"),
            wind_ms=Decimal("5.1"),
            ghi_wm2=Decimal("100.0"),
            cloud_pct=Decimal("42.0"),
        )
        return OpenMeteoResult(
            source_url="https://example.test/weather",
            model_name="test-model",
            points=[out_of_range_point],
            raw_payload={"hourly": {"time": [end_date.isoformat()]}},
        )


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE core_site (site_id INTEGER PRIMARY KEY, lat NUMERIC, lon NUMERIC)"))
        conn.execute(text("CREATE TABLE core_weather_location (weather_loc_id INTEGER PRIMARY KEY AUTOINCREMENT, site_id INTEGER NULL, lat NUMERIC NOT NULL, lon NUMERIC NOT NULL, provider TEXT NOT NULL, model_name TEXT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"))
        conn.execute(text("CREATE TABLE core_quality_flag (quality_flag TEXT PRIMARY KEY, description TEXT)"))
        conn.execute(text("CREATE TABLE raw_ingestion_batch (ingestion_batch_id INTEGER PRIMARY KEY AUTOINCREMENT, source_system TEXT NOT NULL, payload_format TEXT NOT NULL, source_uri TEXT NULL, notes TEXT NULL)"))
        conn.execute(text("CREATE TABLE raw_raw_payload (raw_payload_id INTEGER PRIMARY KEY AUTOINCREMENT, ingestion_batch_id INTEGER NOT NULL, entity_hint TEXT NULL, payload BLOB NOT NULL)"))
        conn.execute(text("CREATE TABLE core_ts_weather_observation (weather_location_id INTEGER NOT NULL, ts DATETIME NOT NULL, metric TEXT NOT NULL, value NUMERIC NOT NULL, PRIMARY KEY (weather_location_id, ts, metric))"))
        conn.execute(text("INSERT INTO core_site (site_id, lat, lon) VALUES (1, 48.2, 16.37)"))
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def test_backfill_weather_for_site_is_idempotent() -> None:
    session_local = _setup_test_db()
    client = FakeClient()
    with session_local() as db:
        service = WeatherIngestionService(db, client=client)
        first = service.backfill_weather_for_site(1, date(2024, 1, 1), date(2024, 1, 1))
        second = service.backfill_weather_for_site(1, date(2024, 1, 1), date(2024, 1, 1))

        count = db.execute(text("SELECT COUNT(*) FROM core_ts_weather_observation")).scalar_one()

    assert first["rows_inserted"] == 4
    assert second["rows_inserted"] == 0
    assert count == 4


def test_sync_missing_weather_uses_latest_timestamp_gap() -> None:
    session_local = _setup_test_db()
    client = FakeClient()
    with session_local() as db:
        db.execute(text("INSERT INTO core_weather_location (weather_loc_id, site_id, lat, lon, provider, model_name) VALUES (10, 1, 48.2, 16.37, 'open-meteo', 'test')"))
        db.execute(text("INSERT INTO core_quality_flag (quality_flag, description) VALUES ('estimated', 'Estimated')"))
        db.execute(text("INSERT INTO core_ts_weather_observation (weather_location_id, ts, metric, value) VALUES (10, '2024-01-01 23:00:00', 'temperature_2m', 1)"))
        db.commit()

        service = WeatherIngestionService(db, client=client)
        service._latest_available_date_utc = lambda: date(2024, 1, 2)  # type: ignore[method-assign]
        result = service.sync_missing_weather()

    assert result["sites_processed"] == 1
    assert client.calls[0][1] == date(2024, 1, 2)
    assert client.calls[0][2] == date(2024, 1, 2)


def test_recent_fetch_filters_future_hours_from_forecast_results() -> None:
    session_local = _setup_test_db()
    with session_local() as db:
        service = WeatherIngestionService(db, client=FakeClient())
        service._latest_available_date_utc = lambda: date(2024, 1, 2)  # type: ignore[method-assign]
        service._latest_complete_hour_utc = lambda: datetime(2024, 1, 2, 10, 0, 0)  # type: ignore[method-assign]

        result = service._fetch_for_range(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 2), date(2024, 1, 2))

    assert [point.ts_utc for point in result.points] == [datetime(2024, 1, 2, 0, 0, 0)]


def test_get_status_does_not_create_missing_weather_locations() -> None:
    session_local = _setup_test_db()
    with session_local() as db:
        service = WeatherIngestionService(db, client=FakeClient())

        status = service.get_status()
        location_count = db.execute(text("SELECT COUNT(*) FROM core_weather_location")).scalar_one()

    assert status["sites"][0]["weather_loc_id"] is None
    assert location_count == 0


def test_recent_fetch_falls_back_to_historical_on_recent_error() -> None:
    session_local = _setup_test_db()
    client = FailingRecentClient()
    with session_local() as db:
        service = WeatherIngestionService(db, client=client)
        service._latest_available_date_utc = lambda: date(2024, 1, 2)  # type: ignore[method-assign]
        result = service._fetch_for_range(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 2), date(2024, 1, 2))

    assert client.calls == [
        ("recent", date(2024, 1, 2), date(2024, 1, 2)),
        ("historical", date(2024, 1, 2), date(2024, 1, 2)),
    ]
    assert len(result.points) == 1


def test_recent_fetch_falls_back_to_historical_when_recent_points_are_empty_after_filter() -> None:
    session_local = _setup_test_db()
    client = EmptyRecentClient()
    with session_local() as db:
        service = WeatherIngestionService(db, client=client)
        service._latest_available_date_utc = lambda: date(2024, 1, 2)  # type: ignore[method-assign]
        service._latest_complete_hour_utc = lambda: datetime(2024, 1, 2, 10, 0, 0)  # type: ignore[method-assign]
        result = service._fetch_for_range(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 2), date(2024, 1, 2))

    assert client.calls == [
        ("recent", date(2024, 1, 2), date(2024, 1, 2)),
        ("historical", date(2024, 1, 2), date(2024, 1, 2)),
    ]
    assert len(result.points) == 1


def test_ranges_ending_before_today_use_historical_to_avoid_recent_anchor_gaps() -> None:
    session_local = _setup_test_db()
    client = FakeClient()
    with session_local() as db:
        service = WeatherIngestionService(db, client=client)
        service._latest_available_date_utc = lambda: date(2024, 1, 4)  # type: ignore[method-assign]
        result = service._fetch_for_range(Decimal("48.2"), Decimal("16.37"), date(2024, 1, 2), date(2024, 1, 3))

    assert client.calls == [("historical", date(2024, 1, 2), date(2024, 1, 3))]
    assert len(result.points) == 1
