from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Computed,
    ForeignKeyConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RawIngestionBatch(Base):
    __tablename__ = "raw_ingestion_batch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_topic: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="received")
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RawRawPayload(Base):
    __tablename__ = "raw_raw_payload"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingestion_batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("raw_ingestion_batch.id", ondelete="CASCADE"), nullable=False
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ingestion_batch_id", "payload_hash", name="uq_raw_payload_batch_hash"),
        Index("ix_raw_payload_batch_received", "ingestion_batch_id", "received_at"),
    )


class CoreBiddingZone(Base):
    __tablename__ = "core_bidding_zone"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class CoreGridZone(Base):
    __tablename__ = "core_grid_zone"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bidding_zone_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_bidding_zone.id"))
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Customer(Base):
    __tablename__ = "core_customer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Site(Base):
    __tablename__ = "core_site"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_customer.id", ondelete="CASCADE"), nullable=False)
    grid_zone_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_grid_zone.id"))
    site_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="UTC")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))


class Asset(Base):
    __tablename__ = "core_asset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_site.id", ondelete="CASCADE"), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rated_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime)


class CoreAssetCapability(Base):
    __tablename__ = "core_asset_capability"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_asset.id", ondelete="CASCADE"), nullable=False)
    capability_type: Mapped[str] = mapped_column(String(64), nullable=False)
    min_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    max_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    min_soc_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    max_soc_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    __table_args__ = (
        UniqueConstraint("asset_id", "capability_type", name="uq_core_asset_capability_type"),
    )


class CoreMeter(Base):
    __tablename__ = "core_meter"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_site.id", ondelete="CASCADE"))
    asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_asset.id", ondelete="CASCADE"))
    meter_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    meter_role: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, server_default="kWh")


class CoreQualityFlag(Base):
    __tablename__ = "core_quality_flag"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class CoreTsMeterReading(Base):
    __tablename__ = "core_ts_meter_reading"

    meter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_meter.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    quality_flag_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_quality_flag.id"))
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    ingestion_batch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("raw_ingestion_batch.id"))

    __table_args__ = (
        PrimaryKeyConstraint("meter_id", "ts", name="pk_core_ts_meter_reading"),
        Index("ix_meter_reading_ts", "ts"),
        Index("ix_meter_reading_quality", "quality_flag_id", "ts"),
    )


class CoreTsAssetTelemetry(Base):
    __tablename__ = "core_ts_asset_telemetry"

    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_asset.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quality_flag_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_quality_flag.id"))

    __table_args__ = (
        PrimaryKeyConstraint("asset_id", "ts", "metric", name="pk_core_ts_asset_telemetry"),
        Index("ix_asset_telemetry_ts", "ts"),
    )


class CoreWeatherLocation(Base):
    __tablename__ = "core_weather_location"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_site.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_location_key: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_location_key", name="uq_weather_provider_location"),
    )


class CoreTsWeatherObservation(Base):
    __tablename__ = "core_ts_weather_observation"

    weather_location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_weather_location.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("weather_location_id", "ts", "metric", name="pk_core_ts_weather_observation"),
        Index("ix_weather_observation_ts", "ts"),
    )


class CoreTsForecast(Base):
    __tablename__ = "core_ts_forecast"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    forecast_type: Mapped[str] = mapped_column(String(64), nullable=False)
    forecast_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    issue_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    asset_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_asset.id", ondelete="CASCADE"))
    weather_location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_weather_location.id", ondelete="CASCADE")
    )
    scenario: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    q_asset_id: Mapped[int] = mapped_column(BigInteger, Computed("ifnull(asset_id,0)"), nullable=False)
    q_weather_location_id: Mapped[int] = mapped_column(
        BigInteger, Computed("ifnull(weather_location_id,0)"), nullable=False
    )
    q_scenario: Mapped[str] = mapped_column(String(64), Computed("ifnull(scenario,'__NULL__')"), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "forecast_type",
            "forecast_time",
            "issue_time",
            "q_asset_id",
            "q_weather_location_id",
            "q_scenario",
            name="uq_core_ts_forecast_dedup",
        ),
        Index("ix_core_ts_forecast_time", "forecast_time", "issue_time"),
    )


class CoreMarket(Base):
    __tablename__ = "core_market"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class CoreMarketProduct(Base):
    __tablename__ = "core_market_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_market.id", ondelete="CASCADE"), nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(64))
    granularity_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    q_product_code: Mapped[str] = mapped_column(String(64), Computed("ifnull(product_code,'__NULL__')"), nullable=False)

    __table_args__ = (
        UniqueConstraint("market_id", "q_product_code", name="uq_core_market_product_dedup"),
        CheckConstraint("granularity_minutes > 0", name="ck_market_product_granularity_positive"),
    )


class CoreTsMarketPrice(Base):
    __tablename__ = "core_ts_market_price"

    market_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_market_product.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    bidding_zone_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_bidding_zone.id"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")

    __table_args__ = (
        PrimaryKeyConstraint("market_product_id", "bidding_zone_id", "ts", name="pk_core_ts_market_price"),
        Index("ix_market_price_ts", "ts"),
    )


class CoreGridEvent(Base):
    __tablename__ = "core_grid_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    grid_zone_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_grid_zone.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    description: Mapped[str | None] = mapped_column(Text)


class CoreDispatchPlan(Base):
    __tablename__ = "core_dispatch_plan"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_site.id", ondelete="CASCADE"), nullable=False)
    market_product_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("core_market_product.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")


class CoreDispatchStep(Base):
    __tablename__ = "core_dispatch_step"

    dispatch_plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_dispatch_plan.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_asset.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    target_power_kw: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("dispatch_plan_id", "step_index", name="pk_core_dispatch_step"),
        Index("ix_dispatch_step_asset_ts", "asset_id", "ts"),
    )


class CoreDispatchExecution(Base):
    __tablename__ = "core_dispatch_execution"

    dispatch_plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_dispatch_plan.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actual_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    __table_args__ = (
        PrimaryKeyConstraint("dispatch_plan_id", "step_index", "executed_at", name="pk_core_dispatch_execution"),
        ForeignKeyConstraint(["dispatch_plan_id", "step_index"], ["core_dispatch_step.dispatch_plan_id", "core_dispatch_step.step_index"], ondelete="CASCADE"),
    )


class CoreContract(Base):
    __tablename__ = "core_contract"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_customer.id", ondelete="CASCADE"), nullable=False)
    contract_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    terms: Mapped[dict | None] = mapped_column(JSON)


class CoreSettlementStatement(Base):
    __tablename__ = "core_settlement_statement"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_contract.id", ondelete="CASCADE"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")

    __table_args__ = (
        UniqueConstraint("contract_id", "period_start", "period_end", name="uq_settlement_contract_period"),
    )


class BiDimTime(Base):
    __tablename__ = "bi_dim_time"

    time_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, unique=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter_hour: Mapped[int] = mapped_column(Integer, nullable=False)


class BiDimCustomer(Base):
    __tablename__ = "bi_dim_customer"

    customer_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_customer.id"), nullable=False, unique=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)


class BiDimSite(Base):
    __tablename__ = "bi_dim_site"

    site_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_site.id"), nullable=False, unique=True)
    customer_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_customer.customer_key"), nullable=False)
    site_name: Mapped[str] = mapped_column(String(255), nullable=False)


class BiDimAsset(Base):
    __tablename__ = "bi_dim_asset"

    asset_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_asset.id"), nullable=False, unique=True)
    site_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_site.site_key"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)


class BiDimMarketProduct(Base):
    __tablename__ = "bi_dim_market_product"

    market_product_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    market_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_market_product.id"), nullable=False, unique=True
    )
    market_code: Mapped[str] = mapped_column(String(32), nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(64))


class BiDimQuality(Base):
    __tablename__ = "bi_dim_quality"

    quality_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    quality_flag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_quality_flag.id"), nullable=False, unique=True)
    quality_code: Mapped[str] = mapped_column(String(32), nullable=False)


class BiFactEnergyInterval(Base):
    __tablename__ = "bi_fact_energy_interval"

    time_key: Mapped[int] = mapped_column(Integer, ForeignKey("bi_dim_time.time_key"), nullable=False)
    site_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_site.site_key"), nullable=False)
    asset_key: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bi_dim_asset.asset_key"))
    quality_key: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bi_dim_quality.quality_key"))
    energy_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("time_key", "site_key", "asset_key", name="pk_bi_fact_energy_interval"),
        Index("ix_bi_energy_site_time", "site_key", "time_key"),
    )


class BiFactMarketPrice(Base):
    __tablename__ = "bi_fact_market_price"

    time_key: Mapped[int] = mapped_column(Integer, ForeignKey("bi_dim_time.time_key"), nullable=False)
    market_product_key: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bi_dim_market_product.market_product_key"), nullable=False
    )
    bidding_zone_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_bidding_zone.id"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("time_key", "market_product_key", "bidding_zone_id", name="pk_bi_fact_market_price"),
        Index("ix_bi_market_price_product_time", "market_product_key", "time_key"),
    )


class BiFactDispatch(Base):
    __tablename__ = "bi_fact_dispatch"

    time_key: Mapped[int] = mapped_column(Integer, ForeignKey("bi_dim_time.time_key"), nullable=False)
    asset_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_asset.asset_key"), nullable=False)
    dispatch_plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_dispatch_plan.id"), nullable=False)
    target_power_kw: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    actual_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

    __table_args__ = (
        PrimaryKeyConstraint("time_key", "asset_key", "dispatch_plan_id", name="pk_bi_fact_dispatch"),
        Index("ix_bi_dispatch_asset_time", "asset_key", "time_key"),
    )


class BiFactForecastAccuracy(Base):
    __tablename__ = "bi_fact_forecast_accuracy"

    time_key: Mapped[int] = mapped_column(Integer, ForeignKey("bi_dim_time.time_key"), nullable=False)
    asset_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_asset.asset_key"), nullable=False)
    forecast_type: Mapped[str] = mapped_column(String(64), nullable=False)
    mape: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))

    __table_args__ = (
        PrimaryKeyConstraint("time_key", "asset_key", "forecast_type", name="pk_bi_fact_forecast_accuracy"),
        Index("ix_bi_forecast_accuracy_asset_time", "asset_key", "time_key"),
    )


class BiFactSettlement(Base):
    __tablename__ = "bi_fact_settlement"

    settlement_statement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_settlement_statement.id", ondelete="CASCADE"), nullable=False
    )
    time_key: Mapped[int] = mapped_column(Integer, ForeignKey("bi_dim_time.time_key"), nullable=False)
    customer_key: Mapped[int] = mapped_column(BigInteger, ForeignKey("bi_dim_customer.customer_key"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("settlement_statement_id", "time_key", "customer_key", name="pk_bi_fact_settlement"),
        Index("ix_bi_settlement_customer_time", "customer_key", "time_key"),
    )
