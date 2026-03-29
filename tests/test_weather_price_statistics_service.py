from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.services.weather_price_analysis_service import AnalysisNotFoundError
from app.services.weather_price_statistics_service import (
    StatisticsNotEnoughDataError,
    WeatherPriceStatisticsService,
)
from app.schemas.weather_price_statistics import WeatherPriceStatisticsRequest


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def _build_rows(n: int) -> list[SimpleNamespace]:
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[SimpleNamespace] = []
    for i in range(n):
        rows.append(
            SimpleNamespace(
                ts_utc=base_ts + timedelta(hours=i),
                temp_c_weighted=Decimal("10.0") + Decimal(i) * Decimal("0.3"),
                wind_ms_weighted=Decimal("2.0") + Decimal(i) * Decimal("0.1"),
                ghi_wm2_weighted=Decimal("50.0") + Decimal(i) * Decimal("5.0"),
                cloud_pct_weighted=Decimal("60.0") - Decimal(i) * Decimal("0.5"),
                price_eur_mwh=Decimal("100.0") - Decimal(i) * Decimal("1.1"),
            )
        )
    return rows


def test_statistics_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = WeatherPriceStatisticsService(db)

    monkeypatch.setattr(service.repository, "get_run", lambda run_id: SimpleNamespace(id=run_id, run_name="run-a"))
    monkeypatch.setattr(service.repository, "get_analysis_rows", lambda run_id: _build_rows(48))

    payload = WeatherPriceStatisticsRequest(analysis_run_id=1)
    response = service.analyze(payload)

    assert response.meta["row_count"] == 48
    assert "price_eur_mwh" in response.descriptive_statistics
    assert set(response.correlations.keys()) == {"temp_vs_price", "wind_vs_price", "ghi_vs_price", "cloud_vs_price"}
    assert len(response.correlation_matrix.columns) == 5
    assert "temperature" in response.bucket_analysis
    assert "temp_vs_price" in response.scatter_data
    assert len(response.lag_analysis["wind_vs_price"]) == 4

    db.close()


def test_statistics_raises_when_run_missing() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = WeatherPriceStatisticsService(db)

    with pytest.raises(AnalysisNotFoundError):
        service.analyze(WeatherPriceStatisticsRequest(analysis_run_id=999))

    db.close()


def test_statistics_raises_on_insufficient_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    service = WeatherPriceStatisticsService(db)

    monkeypatch.setattr(service.repository, "get_run", lambda run_id: SimpleNamespace(id=run_id, run_name="run-a"))
    monkeypatch.setattr(service.repository, "get_analysis_rows", lambda run_id: _build_rows(6))

    with pytest.raises(StatisticsNotEnoughDataError):
        service.analyze(WeatherPriceStatisticsRequest(analysis_run_id=1))

    db.close()


def test_statistics_request_requires_source_payload() -> None:
    with pytest.raises(ValueError):
        WeatherPriceStatisticsRequest()
