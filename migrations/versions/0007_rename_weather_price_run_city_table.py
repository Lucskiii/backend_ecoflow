"""rename weather-price run-city table to bi schema

Revision ID: 0007_rename_weather_price_run_city
Revises: 0006_weather_price_analysis
Create Date: 2026-03-27 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_rename_weather_price_run_city"
down_revision = "0006_weather_price_analysis"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    has_old = _has_table(inspector, "core_weather_price_analysis_run_city")
    has_new = _has_table(inspector, "bi_weather_price_analysis_run_city")

    if has_old and not has_new:
        op.rename_table("core_weather_price_analysis_run_city", "bi_weather_price_analysis_run_city")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    has_old = _has_table(inspector, "core_weather_price_analysis_run_city")
    has_new = _has_table(inspector, "bi_weather_price_analysis_run_city")

    if has_new and not has_old:
        op.rename_table("bi_weather_price_analysis_run_city", "core_weather_price_analysis_run_city")
