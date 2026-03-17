from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import (
    AuthenticatedCustomer,
    CustomerCreate,
    CustomerLogin,
    CustomerRead,
    CustomerRegister,
    CustomerSelfUpdate,
    CustomerUpdate,
    TokenResponse,
)
from app.schemas.energy import (
    EnergySimulationResponse,
    EnergySummaryResponse,
    EnergyTimeseriesResponse,
    PortfolioSummaryResponse,
    PortfolioTimeseriesResponse,
)
from app.schemas.market import MarketPriceRefreshResponse, MarketPriceTimeseriesResponse
from app.security import create_access_token, decode_access_token
from app.services.consumption_simulation_service import ConsumptionSimulationService
from app.services.energy_service import EnergyService
from app.services.market_price_service import MarketPriceService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api", tags=["customers"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _get_current_customer(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise unauthorized
        customer_id = int(subject)
    except (InvalidTokenError, ValueError, TypeError):
        raise unauthorized

    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated customer not found",
        )
    return customer


def _ensure_aware_utc(dt: datetime, field_name: str) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must include timezone information",
        )
    return dt.astimezone(timezone.utc)


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerRead]:
    repository = CustomerRepository(db)
    return repository.list()


@router.get("/customers/me", response_model=CustomerRead)
def get_current_customer(customer=Depends(_get_current_customer)) -> CustomerRead:
    return customer


@router.put("/customers/me", response_model=CustomerRead)
def update_current_customer(
    payload: CustomerSelfUpdate,
    customer=Depends(_get_current_customer),
    db: Session = Depends(get_db),
) -> CustomerRead:
    repository = CustomerRepository(db)

    return repository.update(customer, payload)


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerRead:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )

    return customer


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
def create_customer(
    payload: CustomerCreate, db: Session = Depends(get_db)
) -> CustomerRead:
    repository = CustomerRepository(db)
    return repository.create(payload)


@router.put("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
) -> CustomerRead:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )
    return repository.update(customer, payload)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> None:
    repository = CustomerRepository(db)
    customer = repository.get(customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )
    repository.delete(customer)


@router.post(
    "/auth/register",
    response_model=AuthenticatedCustomer,
    status_code=status.HTTP_201_CREATED,
)
def register_customer(
    payload: CustomerRegister, db: Session = Depends(get_db)
) -> AuthenticatedCustomer:
    repository = CustomerRepository(db)
    customer = repository.create(payload)
    token = create_access_token(str(customer.customer_id))
    return AuthenticatedCustomer(customer=customer, access_token=token)


@router.post("/auth/login", response_model=TokenResponse)
def login_customer(
    payload: CustomerLogin, db: Session = Depends(get_db)
) -> TokenResponse:
    repository = CustomerRepository(db)
    customer = repository.get(payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    token = create_access_token(str(customer.customer_id))
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=CustomerRead)
def get_me(customer=Depends(_get_current_customer)) -> CustomerRead:
    return customer


@router.get("/customers/me/energy/summary", response_model=EnergySummaryResponse)
def get_my_energy_summary(
    period: str = Query(default="today", pattern="^(today|7d|30d)$"),
    site_id: int | None = None,
    customer=Depends(_get_current_customer),
    db: Session = Depends(get_db),
) -> EnergySummaryResponse:
    service = EnergyService(db)
    return EnergySummaryResponse(
        **service.energy_summary(customer.customer_id, period=period, site_id=site_id)
    )


@router.get("/customers/me/energy/timeseries", response_model=EnergyTimeseriesResponse)
def get_my_energy_timeseries(
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    site_id: int | None = None,
    interval: str = "15m",
    customer=Depends(_get_current_customer),
    db: Session = Depends(get_db),
) -> EnergyTimeseriesResponse:
    if interval != "15m":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 15m interval is supported",
        )

    now = datetime.now(timezone.utc)
    if to_ts is None:
        to_ts = now
    else:
        to_ts = _ensure_aware_utc(to_ts, "to")

    if from_ts is None:
        from_ts = to_ts - timedelta(days=1)
    else:
        from_ts = _ensure_aware_utc(from_ts, "from")

    if from_ts >= to_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before to"
        )

    service = EnergyService(db)
    return EnergyTimeseriesResponse(
        **service.energy_timeseries(
            customer.customer_id, from_ts=from_ts, to_ts=to_ts, site_id=site_id
        )
    )


@router.get("/portfolio/export/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_export_summary(
    period: str = Query(default="today", pattern="^(today|7d|30d)$"),
    db: Session = Depends(get_db),
) -> PortfolioSummaryResponse:
    service = PortfolioService(db)
    return PortfolioSummaryResponse(**service.export_summary(period=period))


@router.get("/portfolio/export/timeseries", response_model=PortfolioTimeseriesResponse)
def get_portfolio_export_timeseries(
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    interval: str = "15m",
    db: Session = Depends(get_db),
) -> PortfolioTimeseriesResponse:
    if interval != "15m":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 15m interval is supported",
        )

    now = datetime.now(timezone.utc)
    if to_ts is None:
        to_ts = now
    else:
        to_ts = _ensure_aware_utc(to_ts, "to")

    if from_ts is None:
        from_ts = to_ts - timedelta(days=1)
    else:
        from_ts = _ensure_aware_utc(from_ts, "from")

    if from_ts >= to_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before to"
        )

    service = PortfolioService(db)
    return PortfolioTimeseriesResponse(
        **service.export_timeseries(from_ts=from_ts, to_ts=to_ts)
    )


@router.post("/customers/me/energy/simulate", response_model=EnergySimulationResponse)
def simulate_my_energy_data(
    days: int = Query(default=30, ge=1, le=120),
    customer=Depends(_get_current_customer),
    db: Session = Depends(get_db),
) -> EnergySimulationResponse:
    service = EnergyService(db)
    result = service.simulate_customer_data(customer, days=days)
    return EnergySimulationResponse(
        customer_id=result.customer_id,
        days=result.days,
        sites_processed=result.sites_processed,
        readings_created=result.readings_created,
        **{"from": result.from_ts, "to": result.to_ts},
    )


@router.get("/market/prices", response_model=MarketPriceTimeseriesResponse)
def get_market_prices(
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> MarketPriceTimeseriesResponse:
    now = datetime.now(timezone.utc)
    if to_ts is None:
        to_ts = now
    else:
        to_ts = _ensure_aware_utc(to_ts, "to")

    if from_ts is None:
        from_ts = to_ts - timedelta(days=1)
    else:
        from_ts = _ensure_aware_utc(from_ts, "from")

    if from_ts >= to_ts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="from must be before to"
        )

    payload = MarketPriceService(db).get_prices(from_ts=from_ts, to_ts=to_ts)
    return MarketPriceTimeseriesResponse(**payload)


@router.get("/market/prices/latest", response_model=MarketPriceTimeseriesResponse)
def get_latest_market_prices(
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> MarketPriceTimeseriesResponse:
    payload = MarketPriceService(db).get_latest_window(hours=hours)
    return MarketPriceTimeseriesResponse(**payload)


@router.post("/market/prices/refresh", response_model=MarketPriceRefreshResponse)
def refresh_market_prices(db: Session = Depends(get_db)) -> MarketPriceRefreshResponse:
    inserted = MarketPriceService(db).refresh_prices()
    return MarketPriceRefreshResponse(inserted=inserted)
