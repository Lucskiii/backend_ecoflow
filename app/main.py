import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.consumption import router as consumption_router
from app.api.health import router as health_router
from app.api.router import router as api_router
from app.config import get_settings
from app.database import SessionLocal
from app.services.energy_service import EnergyService
from app.services.market_price_scheduler import MarketPriceScheduler

settings = get_settings()
logger = logging.getLogger(__name__)
market_price_scheduler = MarketPriceScheduler()

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
app.include_router(consumption_router)


@app.on_event("startup")
def start_market_price_scheduler() -> None:
    market_price_scheduler.start()


@app.on_event("shutdown")
def stop_market_price_scheduler() -> None:
    market_price_scheduler.stop()
