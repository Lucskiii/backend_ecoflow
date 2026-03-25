import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.geocoding import router as geocoding_router
from app.api.router import router as api_router
from app.api.weather import router as weather_router
from app.config import get_settings
from app.database import SessionLocal
from app.services.energy_service import EnergyService
from app.services.customer_site_coordinate_service import CustomerSiteCoordinateService
from app.scheduler.weather_scheduler import WeatherScheduler
from app.services.market_price_scheduler import MarketPriceScheduler

settings = get_settings()
logger = logging.getLogger(__name__)
market_price_scheduler = MarketPriceScheduler()
weather_scheduler = WeatherScheduler()

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.on_event("startup")
def auto_seed_demo_energy_data() -> None:
    if not settings.auto_simulate_energy:
        logger.info("Auto energy simulation disabled via AUTO_SIMULATE_ENERGY")
        return

    db = SessionLocal()
    try:
        EnergyService(db).ensure_demo_energy_data_for_all_customers(
            days=settings.auto_simulate_days
        )
    finally:
        db.close()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(api_router)
app.include_router(weather_router)
app.include_router(geocoding_router)


@app.on_event("startup")
def start_market_price_scheduler() -> None:
    market_price_scheduler.start()


@app.on_event("startup")
def backfill_customer_site_coordinates() -> None:
    db = SessionLocal()
    try:
        CustomerSiteCoordinateService(db).backfill_missing_site_coordinates()
    finally:
        db.close()


@app.on_event("shutdown")
def stop_market_price_scheduler() -> None:
    market_price_scheduler.stop()


@app.on_event("startup")
def start_weather_scheduler() -> None:
    weather_scheduler.start()


@app.on_event("shutdown")
def stop_weather_scheduler() -> None:
    weather_scheduler.stop()
