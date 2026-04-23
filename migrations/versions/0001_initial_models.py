"""initial mysql schema foundation

Revision ID: 0001_initial_models
Revises:
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_models"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bi_dim_time",
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("quarter_hour", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("time_key"),
        sa.UniqueConstraint("ts"),
    )
    op.create_table(
        "core_bidding_zone",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "core_customer",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("external_ref", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_table(
        "core_market",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "core_quality_flag",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "raw_ingestion_batch",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_topic", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="received", nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bi_dim_customer",
        sa.Column("customer_key", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["core_customer.id"]),
        sa.PrimaryKeyConstraint("customer_key"),
        sa.UniqueConstraint("customer_id"),
    )
    op.create_table(
        "bi_dim_quality",
        sa.Column("quality_key", sa.BigInteger(), nullable=False),
        sa.Column("quality_flag_id", sa.BigInteger(), nullable=False),
        sa.Column("quality_code", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["quality_flag_id"], ["core_quality_flag.id"]),
        sa.PrimaryKeyConstraint("quality_key"),
        sa.UniqueConstraint("quality_flag_id"),
    )
    op.create_table(
        "core_contract",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("contract_code", sa.String(length=64), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("terms", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["core_customer.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_code"),
    )
    op.create_table(
        "core_grid_zone",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bidding_zone_id", sa.BigInteger(), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["bidding_zone_id"], ["core_bidding_zone.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "core_market_product",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.Column("granularity_minutes", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=True),
        # MariaDB rejects explicit NOT NULL on generated columns in this form.
        sa.Column("q_product_code", sa.String(length=64), sa.Computed("ifnull(product_code,'__NULL__')")),
        sa.CheckConstraint("granularity_minutes > 0", name="ck_market_product_granularity_positive"),
        sa.ForeignKeyConstraint(["market_id"], ["core_market.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "q_product_code", name="uq_core_market_product_dedup"),
    )
    op.create_table(
        "raw_raw_payload",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingestion_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["raw_ingestion_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ingestion_batch_id", "payload_hash", name="uq_raw_payload_batch_hash"),
    )
    op.create_index("ix_raw_payload_batch_received", "raw_raw_payload", ["ingestion_batch_id", "received_at"], unique=False)
    op.create_table(
        "bi_dim_market_product",
        sa.Column("market_product_key", sa.BigInteger(), nullable=False),
        sa.Column("market_product_id", sa.BigInteger(), nullable=False),
        sa.Column("market_code", sa.String(length=32), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["market_product_id"], ["core_market_product.id"]),
        sa.PrimaryKeyConstraint("market_product_key"),
        sa.UniqueConstraint("market_product_id"),
    )
    op.create_table(
        "core_grid_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("grid_zone_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["grid_zone_id"], ["core_grid_zone.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "core_settlement_statement",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.BigInteger(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["core_contract.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "period_start", "period_end", name="uq_settlement_contract_period"),
    )
    op.create_table(
        "core_site",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("grid_zone_id", sa.BigInteger(), nullable=True),
        sa.Column("site_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["core_customer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grid_zone_id"], ["core_grid_zone.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_code"),
    )
    op.create_table(
        "core_ts_market_price",
        sa.Column("market_product_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("bidding_zone_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=False),
        sa.ForeignKeyConstraint(["bidding_zone_id"], ["core_bidding_zone.id"]),
        sa.ForeignKeyConstraint(["market_product_id"], ["core_market_product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("market_product_id", "bidding_zone_id", "ts", name="pk_core_ts_market_price"),
    )
    op.create_index("ix_market_price_ts", "core_ts_market_price", ["ts"], unique=False)
    op.create_table(
        "bi_dim_site",
        sa.Column("site_key", sa.BigInteger(), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_key", sa.BigInteger(), nullable=False),
        sa.Column("site_name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["customer_key"], ["bi_dim_customer.customer_key"]),
        sa.ForeignKeyConstraint(["site_id"], ["core_site.id"]),
        sa.PrimaryKeyConstraint("site_key"),
        sa.UniqueConstraint("site_id"),
    )
    op.create_table(
        "bi_fact_market_price",
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("market_product_key", sa.BigInteger(), nullable=False),
        sa.Column("bidding_zone_id", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.ForeignKeyConstraint(["bidding_zone_id"], ["core_bidding_zone.id"]),
        sa.ForeignKeyConstraint(["market_product_key"], ["bi_dim_market_product.market_product_key"]),
        sa.ForeignKeyConstraint(["time_key"], ["bi_dim_time.time_key"]),
        sa.PrimaryKeyConstraint("time_key", "market_product_key", "bidding_zone_id", name="pk_bi_fact_market_price"),
    )
    op.create_index("ix_bi_market_price_product_time", "bi_fact_market_price", ["market_product_key", "time_key"], unique=False)
    op.create_table(
        "bi_fact_settlement",
        sa.Column("settlement_statement_id", sa.BigInteger(), nullable=False),
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("customer_key", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["customer_key"], ["bi_dim_customer.customer_key"]),
        sa.ForeignKeyConstraint(["settlement_statement_id"], ["core_settlement_statement.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["time_key"], ["bi_dim_time.time_key"]),
        sa.PrimaryKeyConstraint("settlement_statement_id", "time_key", "customer_key", name="pk_bi_fact_settlement"),
    )
    op.create_index("ix_bi_settlement_customer_time", "bi_fact_settlement", ["customer_key", "time_key"], unique=False)
    op.create_table(
        "core_asset",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("rated_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("commissioned_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["core_site.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_code"),
    )
    op.create_table(
        "core_dispatch_plan",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column("market_product_id", sa.BigInteger(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.ForeignKeyConstraint(["market_product_id"], ["core_market_product.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["core_site.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "core_weather_location",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_location_key", sa.String(length=128), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["core_site.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_location_key", name="uq_weather_provider_location"),
    )
    op.create_table(
        "bi_dim_asset",
        sa.Column("asset_key", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("site_key", sa.BigInteger(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"]),
        sa.ForeignKeyConstraint(["site_key"], ["bi_dim_site.site_key"]),
        sa.PrimaryKeyConstraint("asset_key"),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_table(
        "core_asset_capability",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("capability_type", sa.String(length=64), nullable=False),
        sa.Column("min_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("max_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("min_soc_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("max_soc_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "capability_type", name="uq_core_asset_capability_type"),
    )
    op.create_table(
        "core_dispatch_step",
        sa.Column("dispatch_plan_id", sa.BigInteger(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("target_power_kw", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatch_plan_id"], ["core_dispatch_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dispatch_plan_id", "step_index", name="pk_core_dispatch_step"),
    )
    op.create_index("ix_dispatch_step_asset_ts", "core_dispatch_step", ["asset_id", "ts"], unique=False)
    op.create_table(
        "core_meter",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=True),
        sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("meter_code", sa.String(length=64), nullable=False),
        sa.Column("meter_role", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=16), server_default="kWh", nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["core_site.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meter_code"),
    )
    op.create_table(
        "core_ts_asset_telemetry",
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("quality_flag_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quality_flag_id"], ["core_quality_flag.id"]),
        sa.PrimaryKeyConstraint("asset_id", "ts", "metric", name="pk_core_ts_asset_telemetry"),
    )
    op.create_index("ix_asset_telemetry_ts", "core_ts_asset_telemetry", ["ts"], unique=False)
    op.create_table(
        "core_ts_forecast",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("forecast_type", sa.String(length=64), nullable=False),
        sa.Column("forecast_time", sa.DateTime(), nullable=False),
        sa.Column("issue_time", sa.DateTime(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("weather_location_id", sa.BigInteger(), nullable=True),
        sa.Column("scenario", sa.String(length=64), nullable=True),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=False),
        # MariaDB rejects explicit NOT NULL on generated columns in this form.
        sa.Column("q_asset_id", sa.BigInteger(), sa.Computed("ifnull(asset_id,0)")),
        sa.Column("q_weather_location_id", sa.BigInteger(), sa.Computed("ifnull(weather_location_id,0)")),
        sa.Column("q_scenario", sa.String(length=64), sa.Computed("ifnull(scenario,'__NULL__')")),
        sa.ForeignKeyConstraint(["asset_id"], ["core_asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["weather_location_id"], ["core_weather_location.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "forecast_type",
            "forecast_time",
            "issue_time",
            "q_asset_id",
            "q_weather_location_id",
            "q_scenario",
            name="uq_core_ts_forecast_dedup",
        ),
    )
    op.create_index("ix_core_ts_forecast_time", "core_ts_forecast", ["forecast_time", "issue_time"], unique=False)
    op.create_table(
        "core_ts_weather_observation",
        sa.Column("weather_location_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.ForeignKeyConstraint(["weather_location_id"], ["core_weather_location.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("weather_location_id", "ts", "metric", name="pk_core_ts_weather_observation"),
    )
    op.create_index("ix_weather_observation_ts", "core_ts_weather_observation", ["ts"], unique=False)
    op.create_table(
        "bi_fact_dispatch",
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.BigInteger(), nullable=False),
        sa.Column("dispatch_plan_id", sa.BigInteger(), nullable=False),
        sa.Column("target_power_kw", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("actual_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.ForeignKeyConstraint(["asset_key"], ["bi_dim_asset.asset_key"]),
        sa.ForeignKeyConstraint(["dispatch_plan_id"], ["core_dispatch_plan.id"]),
        sa.ForeignKeyConstraint(["time_key"], ["bi_dim_time.time_key"]),
        sa.PrimaryKeyConstraint("time_key", "asset_key", "dispatch_plan_id", name="pk_bi_fact_dispatch"),
    )
    op.create_index("ix_bi_dispatch_asset_time", "bi_fact_dispatch", ["asset_key", "time_key"], unique=False)
    op.create_table(
        "bi_fact_energy_interval",
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("site_key", sa.BigInteger(), nullable=False),
        sa.Column("asset_key", sa.BigInteger(), nullable=False),
        sa.Column("quality_key", sa.BigInteger(), nullable=True),
        sa.Column("energy_kwh", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.ForeignKeyConstraint(["asset_key"], ["bi_dim_asset.asset_key"]),
        sa.ForeignKeyConstraint(["quality_key"], ["bi_dim_quality.quality_key"]),
        sa.ForeignKeyConstraint(["site_key"], ["bi_dim_site.site_key"]),
        sa.ForeignKeyConstraint(["time_key"], ["bi_dim_time.time_key"]),
        sa.PrimaryKeyConstraint("time_key", "site_key", "asset_key", name="pk_bi_fact_energy_interval"),
    )
    op.create_index("ix_bi_energy_site_time", "bi_fact_energy_interval", ["site_key", "time_key"], unique=False)
    op.create_table(
        "bi_fact_forecast_accuracy",
        sa.Column("time_key", sa.Integer(), nullable=False),
        sa.Column("asset_key", sa.BigInteger(), nullable=False),
        sa.Column("forecast_type", sa.String(length=64), nullable=False),
        sa.Column("mape", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("mae", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.ForeignKeyConstraint(["asset_key"], ["bi_dim_asset.asset_key"]),
        sa.ForeignKeyConstraint(["time_key"], ["bi_dim_time.time_key"]),
        sa.PrimaryKeyConstraint("time_key", "asset_key", "forecast_type", name="pk_bi_fact_forecast_accuracy"),
    )
    op.create_index("ix_bi_forecast_accuracy_asset_time", "bi_fact_forecast_accuracy", ["asset_key", "time_key"], unique=False)
    op.create_table(
        "core_dispatch_execution",
        sa.Column("dispatch_plan_id", sa.BigInteger(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actual_power_kw", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.ForeignKeyConstraint(
            ["dispatch_plan_id", "step_index"],
            ["core_dispatch_step.dispatch_plan_id", "core_dispatch_step.step_index"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["dispatch_plan_id"], ["core_dispatch_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dispatch_plan_id", "step_index", "executed_at", name="pk_core_dispatch_execution"),
    )
    op.create_table(
        "core_ts_meter_reading",
        sa.Column("meter_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("quality_flag_id", sa.BigInteger(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("ingestion_batch_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["raw_ingestion_batch.id"]),
        sa.ForeignKeyConstraint(["meter_id"], ["core_meter.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quality_flag_id"], ["core_quality_flag.id"]),
        sa.PrimaryKeyConstraint("meter_id", "ts", name="pk_core_ts_meter_reading"),
    )
    op.create_index("ix_meter_reading_ts", "core_ts_meter_reading", ["ts"], unique=False)
    op.create_index("ix_meter_reading_quality", "core_ts_meter_reading", ["quality_flag_id", "ts"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_meter_reading_ts", table_name="core_ts_meter_reading")
    op.drop_index("ix_meter_reading_quality", table_name="core_ts_meter_reading")
    op.drop_table("core_ts_meter_reading")
    op.drop_table("core_dispatch_execution")
    op.drop_index("ix_bi_forecast_accuracy_asset_time", table_name="bi_fact_forecast_accuracy")
    op.drop_table("bi_fact_forecast_accuracy")
    op.drop_index("ix_bi_energy_site_time", table_name="bi_fact_energy_interval")
    op.drop_table("bi_fact_energy_interval")
    op.drop_index("ix_bi_dispatch_asset_time", table_name="bi_fact_dispatch")
    op.drop_table("bi_fact_dispatch")
    op.drop_index("ix_weather_observation_ts", table_name="core_ts_weather_observation")
    op.drop_table("core_ts_weather_observation")
    op.drop_index("ix_core_ts_forecast_time", table_name="core_ts_forecast")
    op.drop_table("core_ts_forecast")
    op.drop_index("ix_asset_telemetry_ts", table_name="core_ts_asset_telemetry")
    op.drop_table("core_ts_asset_telemetry")
    op.drop_table("core_meter")
    op.drop_index("ix_dispatch_step_asset_ts", table_name="core_dispatch_step")
    op.drop_table("core_dispatch_step")
    op.drop_table("core_asset_capability")
    op.drop_table("bi_dim_asset")
    op.drop_table("core_weather_location")
    op.drop_table("core_dispatch_plan")
    op.drop_table("core_asset")
    op.drop_index("ix_bi_settlement_customer_time", table_name="bi_fact_settlement")
    op.drop_table("bi_fact_settlement")
    op.drop_index("ix_bi_market_price_product_time", table_name="bi_fact_market_price")
    op.drop_table("bi_fact_market_price")
    op.drop_table("bi_dim_site")
    op.drop_index("ix_market_price_ts", table_name="core_ts_market_price")
    op.drop_table("core_ts_market_price")
    op.drop_table("core_site")
    op.drop_table("core_settlement_statement")
    op.drop_table("core_grid_event")
    op.drop_table("bi_dim_market_product")
    op.drop_index("ix_raw_payload_batch_received", table_name="raw_raw_payload")
    op.drop_table("raw_raw_payload")
    op.drop_table("core_market_product")
    op.drop_table("core_grid_zone")
    op.drop_table("core_contract")
    op.drop_table("bi_dim_quality")
    op.drop_table("bi_dim_customer")
    op.drop_table("raw_ingestion_batch")
    op.drop_table("core_quality_flag")
    op.drop_table("core_market")
    op.drop_table("core_customer")
    op.drop_table("core_bidding_zone")
    op.drop_table("bi_dim_time")
