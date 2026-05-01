from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.weather_price_analysis import (
    WeatherPriceAnalysisRenameRequest,
    WeatherPriceAnalysisRequest,
    WeatherPriceAnalysisResponse,
    WeatherPriceAnalysisRunListResponse,
    WeatherPriceAnalysisRunStatus,
)
from app.services.analysis_city_weather_service import WeatherUpstreamError
from app.services.weather_price_analysis_service import (
    AnalysisNotFoundError,
    AnalysisValidationError,
    NoPriceDataError,
    WeatherPriceAnalysisService,
)

router = APIRouter(prefix="/analysis/weather-price", tags=["weather-price-analysis"])


@router.post("", response_model=WeatherPriceAnalysisResponse)
def create_weather_price_analysis(
    payload: WeatherPriceAnalysisRequest,
    db: Session = Depends(get_db),
) -> WeatherPriceAnalysisResponse:
    service = WeatherPriceAnalysisService(db)
    try:
        return service.execute(payload)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except NoPriceDataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WeatherUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/runs", response_model=WeatherPriceAnalysisRunListResponse)
def list_weather_price_analysis_runs(
    limit: int = 100,
    db: Session = Depends(get_db),
) -> WeatherPriceAnalysisRunListResponse:
    safe_limit = max(1, min(limit, 500))
    payload = WeatherPriceAnalysisService(db).list_runs(limit=safe_limit)
    return WeatherPriceAnalysisRunListResponse(**payload)


@router.get("/{analysis_run_id}", response_model=WeatherPriceAnalysisResponse)
def get_weather_price_analysis(
    analysis_run_id: int,
    db: Session = Depends(get_db),
) -> WeatherPriceAnalysisResponse:
    try:
        return WeatherPriceAnalysisService(db).get_run_data(analysis_run_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{analysis_run_id}/status", response_model=WeatherPriceAnalysisRunStatus)
def get_weather_price_analysis_status(
    analysis_run_id: int,
    db: Session = Depends(get_db),
) -> WeatherPriceAnalysisRunStatus:
    try:
        payload = WeatherPriceAnalysisService(db).get_status(analysis_run_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WeatherPriceAnalysisRunStatus(**payload)


@router.patch("/{analysis_run_id}/name")
def rename_weather_price_analysis(
    analysis_run_id: int,
    payload: WeatherPriceAnalysisRenameRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return WeatherPriceAnalysisService(db).rename_run(analysis_run_id, payload.run_name)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
