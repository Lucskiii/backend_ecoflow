from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.router import router as api_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

app.include_router(health_router)
app.include_router(api_router)
