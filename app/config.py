from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    app_name: str = "EcoFlow Backend"
    app_version: str = "0.1.0"
    database_url: str = Field(
        default="mysql+pymysql://user:password@localhost:3306/ecoflow",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")
    auto_simulate_energy: bool = Field(default=True, alias="AUTO_SIMULATE_ENERGY")
    auto_simulate_days: int = Field(default=30, alias="AUTO_SIMULATE_DAYS")
    awattar_api_url: str = Field(
        default="https://api.awattar.at/v1/marketdata", alias="AWATTAR_API_URL"
    )
    market_price_refresh_minutes: int = Field(
        default=60, ge=1, alias="MARKET_PRICE_REFRESH_MINUTES"
    )
    market_price_scheduler_enabled: bool = Field(
        default=True, alias="MARKET_PRICE_SCHEDULER_ENABLED"
    )
    open_meteo_historical_url: str = Field(
        default="https://archive-api.open-meteo.com/v1/archive",
        alias="OPEN_METEO_HISTORICAL_URL",
    )
    open_meteo_forecast_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        alias="OPEN_METEO_FORECAST_URL",
    )
    open_meteo_geocoding_url: str = Field(
        default="https://geocoding-api.open-meteo.com/v1/search",
        alias="OPEN_METEO_GEOCODING_URL",
    )
    open_meteo_timeout_seconds: int = Field(
        default=30, ge=1, alias="OPEN_METEO_TIMEOUT_SECONDS"
    )
    open_meteo_max_days_per_request: int = Field(
        default=30, ge=1, alias="OPEN_METEO_MAX_DAYS_PER_REQUEST"
    )
    weather_default_backfill_days: int = Field(
        default=365, ge=1, alias="WEATHER_DEFAULT_BACKFILL_DAYS"
    )
    weather_recent_days_window: int = Field(
        default=5, ge=1, alias="WEATHER_RECENT_DAYS_WINDOW"
    )
    weather_scheduler_interval_minutes: int = Field(
        default=60, ge=1, alias="WEATHER_SCHEDULER_INTERVAL_MINUTES"
    )
    weather_scheduler_enabled: bool = Field(
        default=True, alias="WEATHER_SCHEDULER_ENABLED"
    )
    weather_store_raw_payload: bool = Field(
        default=True, alias="WEATHER_STORE_RAW_PAYLOAD"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
