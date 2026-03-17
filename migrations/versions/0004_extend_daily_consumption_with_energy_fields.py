"""extend core daily consumption with energy summary fields

Revision ID: 0004_extend_daily_consumption_with_energy_fields
Revises: 0003_add_core_daily_consumption
Create Date: 2026-03-17 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_extend_daily_consumption_with_energy_fields"
down_revision = "0003_add_core_daily_consumption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "core_daily_consumption",
        sa.Column("grid_import_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "core_daily_consumption",
        sa.Column("grid_export_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "core_daily_consumption",
        sa.Column("pv_generation_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "core_daily_consumption",
        sa.Column("self_consumption_share_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )

    op.create_check_constraint(
        "ck_daily_consumption_non_negative",
        "core_daily_consumption",
        "consumption_kwh >= 0",
    )
    op.create_check_constraint(
        "ck_daily_grid_import_non_negative",
        "core_daily_consumption",
        "grid_import_kwh >= 0",
    )
    op.create_check_constraint(
        "ck_daily_grid_export_non_negative",
        "core_daily_consumption",
        "grid_export_kwh >= 0",
    )
    op.create_check_constraint(
        "ck_daily_pv_generation_non_negative",
        "core_daily_consumption",
        "pv_generation_kwh >= 0",
    )
    op.create_check_constraint(
        "ck_daily_self_consumption_share_pct_range",
        "core_daily_consumption",
        "self_consumption_share_pct >= 0 AND self_consumption_share_pct <= 100",
    )

    op.alter_column("core_daily_consumption", "grid_import_kwh", server_default=None)
    op.alter_column("core_daily_consumption", "grid_export_kwh", server_default=None)
    op.alter_column("core_daily_consumption", "pv_generation_kwh", server_default=None)
    op.alter_column("core_daily_consumption", "self_consumption_share_pct", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_daily_self_consumption_share_pct_range", "core_daily_consumption", type_="check")
    op.drop_constraint("ck_daily_pv_generation_non_negative", "core_daily_consumption", type_="check")
    op.drop_constraint("ck_daily_grid_export_non_negative", "core_daily_consumption", type_="check")
    op.drop_constraint("ck_daily_grid_import_non_negative", "core_daily_consumption", type_="check")
    op.drop_constraint("ck_daily_consumption_non_negative", "core_daily_consumption", type_="check")

    op.drop_column("core_daily_consumption", "self_consumption_share_pct")
    op.drop_column("core_daily_consumption", "pv_generation_kwh")
    op.drop_column("core_daily_consumption", "grid_export_kwh")
    op.drop_column("core_daily_consumption", "grid_import_kwh")
