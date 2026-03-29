from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.weather_price_statistics import WeatherPriceStatisticsRequest, WeatherPriceStatisticsResponse
from app.services.weather_price_analysis_service import AnalysisNotFoundError
from app.services.weather_price_statistics_service import (
    StatisticsDataNotFoundError,
    StatisticsInputError,
    StatisticsNotEnoughDataError,
    WeatherPriceStatisticsService,
)

router = APIRouter(prefix="/analysis/weather-price", tags=["weather-price-statistics"])


@router.post("/statistics", response_model=WeatherPriceStatisticsResponse)
def get_weather_price_statistics(
    payload: WeatherPriceStatisticsRequest,
    db: Session = Depends(get_db),
) -> WeatherPriceStatisticsResponse:
    try:
        return WeatherPriceStatisticsService(db).analyze(payload)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StatisticsDataNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StatisticsInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except StatisticsNotEnoughDataError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
