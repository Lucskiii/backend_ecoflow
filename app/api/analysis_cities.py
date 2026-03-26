from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis_city import AnalysisCityCreate, AnalysisCityListResponse, AnalysisCityResponse
from app.services.analysis_city_service import (
    AnalysisCityConflictError,
    AnalysisCityService,
    OpenMeteoGeocodingNoResultsError,
    OpenMeteoGeocodingPayloadError,
    OpenMeteoGeocodingUnavailableError,
)

router = APIRouter(prefix="/analysis-cities", tags=["analysis-cities"])


@router.post("", response_model=AnalysisCityResponse, status_code=status.HTTP_201_CREATED)
def create_analysis_city(payload: AnalysisCityCreate, db: Session = Depends(get_db)) -> AnalysisCityResponse:
    service = AnalysisCityService(db)
    try:
        return service.create_analysis_city(payload)
    except AnalysisCityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OpenMeteoGeocodingNoResultsError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OpenMeteoGeocodingUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OpenMeteoGeocodingPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("", response_model=AnalysisCityListResponse)
def list_analysis_cities(db: Session = Depends(get_db)) -> AnalysisCityListResponse:
    service = AnalysisCityService(db)
    return AnalysisCityListResponse(items=service.list_analysis_cities())


@router.get("/{city_id}", response_model=AnalysisCityResponse)
def get_analysis_city(city_id: int, db: Session = Depends(get_db)) -> AnalysisCityResponse:
    service = AnalysisCityService(db)
    try:
        return service.get_analysis_city(city_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{city_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_city(city_id: int, db: Session = Depends(get_db)) -> None:
    service = AnalysisCityService(db)
    try:
        service.delete_analysis_city(city_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
