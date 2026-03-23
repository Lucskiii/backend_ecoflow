from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.weather_ingestion_service import WeatherIngestionService

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.post("/backfill/site/{site_id}")
def backfill_weather_for_site(
    site_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return WeatherIngestionService(db).backfill_weather_for_site(site_id, start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/backfill/all")
def backfill_weather_for_all(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    return WeatherIngestionService(db).backfill_weather_for_all_sites(start_date, end_date)


@router.post("/sync")
def sync_weather(db: Session = Depends(get_db)) -> dict:
    return WeatherIngestionService(db).sync_missing_weather()


@router.get("/status")
def weather_status(db: Session = Depends(get_db)) -> dict:
    return WeatherIngestionService(db).get_status()
