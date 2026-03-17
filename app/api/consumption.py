from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.consumption import (
    ConsumptionSimulationResponse,
    ConsumptionStatusResponse,
    DailyConsumptionRead,
)
from app.services.consumption_simulation_service import ConsumptionSimulationService

router = APIRouter(prefix="/api", tags=["consumption"])


@router.get("/customers/{customer_id}/consumption/daily", response_model=list[DailyConsumptionRead])
def get_daily_consumption(
    customer_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    auto_generate: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> list[DailyConsumptionRead]:
    service = ConsumptionSimulationService(db)

    try:
        if auto_generate:
            service.ensure_customer_consumption_data(customer_id)

        today = date.today()
        resolved_end = end_date or today
        resolved_start = start_date or (resolved_end - timedelta(days=89))

        if resolved_start > resolved_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before or equal to end_date",
            )

        return service.list_consumption(customer_id, resolved_start, resolved_end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/customers/{customer_id}/consumption/simulate",
    response_model=ConsumptionSimulationResponse,
)
def simulate_missing_consumption(
    customer_id: int,
    db: Session = Depends(get_db),
) -> ConsumptionSimulationResponse:
    service = ConsumptionSimulationService(db)
    try:
        rows_created = service.ensure_customer_consumption_data(customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return ConsumptionSimulationResponse(customer_id=customer_id, rows_created=rows_created)


@router.get("/customers/{customer_id}/consumption/status", response_model=ConsumptionStatusResponse)
def get_consumption_status(customer_id: int, db: Session = Depends(get_db)) -> ConsumptionStatusResponse:
    service = ConsumptionSimulationService(db)
    try:
        return ConsumptionStatusResponse(**service.get_status(customer_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
