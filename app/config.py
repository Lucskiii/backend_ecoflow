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
    cors_allow_origins: list[str] = Field(
        default=["http://localhost:4200"], alias="CORS_ALLOW_ORIGINS"
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
