"""add weighted weather-price analysis tables

Revision ID: 0006_add_weather_price_analysis_tables
Revises: 0005_add_core_analysis_city
Create Date: 2026-03-26 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_weather_price_analysis_tables"
down_revision = "0005_add_core_analysis_city"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "core_analysis_city_weather_observation"):
        op.create_table(
            "core_analysis_city_weather_observation",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("analysis_city_id", sa.BigInteger(), nullable=False),
            sa.Column("ts_utc", sa.DateTime(), nullable=False),
            sa.Column("temp_c", sa.Numeric(8, 3), nullable=True),
            sa.Column("wind_ms", sa.Numeric(8, 3), nullable=True),
            sa.Column("ghi_wm2", sa.Numeric(10, 3), nullable=True),
            sa.Column("cloud_pct", sa.Numeric(6, 3), nullable=True),
            sa.Column("quality_flag", sa.String(length=20), nullable=True),
            sa.Column("source_system", sa.String(length=50), nullable=False, server_default="open-meteo"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["analysis_city_id"], ["core_analysis_city.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("analysis_city_id", "ts_utc", name="uq_core_analysis_city_weather_city_ts"),
        )
        op.create_index("ix_core_analysis_city_weather_ts_utc", "core_analysis_city_weather_observation", ["ts_utc"])

    if not _has_table(inspector, "core_weather_price_analysis_run"):
        op.create_table(
            "core_weather_price_analysis_run",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("run_name", sa.String(length=255), nullable=True),
            sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table(inspector, "core_weather_price_analysis_run_city"):
        op.create_table(
            "core_weather_price_analysis_run_city",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("analysis_run_id", sa.BigInteger(), nullable=False),
            sa.Column("analysis_city_id", sa.BigInteger(), nullable=False),
            sa.Column("weight", sa.Numeric(10, 4), nullable=False),
            sa.ForeignKeyConstraint(["analysis_city_id"], ["core_analysis_city.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["analysis_run_id"], ["core_weather_price_analysis_run.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("analysis_run_id", "analysis_city_id", name="uq_analysis_run_city"),
        )

    if not _has_table(inspector, "core_weighted_weather_aggregate"):
        op.create_table(
            "core_weighted_weather_aggregate",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("analysis_run_id", sa.BigInteger(), nullable=False),
            sa.Column("ts_utc", sa.DateTime(), nullable=False),
            sa.Column("temp_c_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("wind_ms_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("ghi_wm2_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("cloud_pct_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["analysis_run_id"], ["core_weather_price_analysis_run.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("analysis_run_id", "ts_utc", name="uq_weighted_weather_run_ts"),
        )
        op.create_index("ix_weighted_weather_ts_utc", "core_weighted_weather_aggregate", ["ts_utc"])

    if not _has_table(inspector, "bi_weather_price_analysis"):
        op.create_table(
            "bi_weather_price_analysis",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("analysis_run_id", sa.BigInteger(), nullable=False),
            sa.Column("ts_utc", sa.DateTime(), nullable=False),
            sa.Column("temp_c_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("wind_ms_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("ghi_wm2_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("cloud_pct_weighted", sa.Numeric(10, 4), nullable=True),
            sa.Column("price_eur_mwh", sa.Numeric(18, 6), nullable=True),
            sa.Column("product_id", sa.BigInteger(), nullable=True),
            sa.Column("price_type", sa.String(length=20), nullable=True),
            sa.Column("source_system", sa.String(length=50), nullable=False, server_default="analysis-pipeline"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["analysis_run_id"], ["core_weather_price_analysis_run.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["core_market_product.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "analysis_run_id",
                "ts_utc",
                "product_id",
                "price_type",
                name="uq_bi_weather_price_run_ts_product_type",
            ),
        )
        op.create_index("ix_bi_weather_price_ts_utc", "bi_weather_price_analysis", ["ts_utc"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "bi_weather_price_analysis"):
        op.drop_index("ix_bi_weather_price_ts_utc", table_name="bi_weather_price_analysis")
        op.drop_table("bi_weather_price_analysis")

    if _has_table(inspector, "core_weighted_weather_aggregate"):
        op.drop_index("ix_weighted_weather_ts_utc", table_name="core_weighted_weather_aggregate")
        op.drop_table("core_weighted_weather_aggregate")

    if _has_table(inspector, "core_weather_price_analysis_run_city"):
        op.drop_table("core_weather_price_analysis_run_city")

    if _has_table(inspector, "core_weather_price_analysis_run"):
        op.drop_table("core_weather_price_analysis_run")

    if _has_table(inspector, "core_analysis_city_weather_observation"):
        op.drop_index("ix_core_analysis_city_weather_ts_utc", table_name="core_analysis_city_weather_observation")
        op.drop_table("core_analysis_city_weather_observation")
