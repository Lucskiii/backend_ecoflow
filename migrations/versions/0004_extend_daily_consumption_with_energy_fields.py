"""extend core daily consumption with energy summary fields

Revision ID: 0004_extend_daily_consumption_with_energy_fields
Revises: 0003_add_core_daily_consumption
Create Date: 2026-03-17 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from datetime import date
from decimal import Decimal
import random

# revision identifiers, used by Alembic.
revision = "0004_extend_daily_consumption_with_energy_fields"
down_revision = "0003_add_core_daily_consumption"
branch_labels = None
depends_on = None


def _pv_seasonal_factor(month: int) -> float:
    if month in (12, 1, 2):
        return 0.28
    if month in (3, 4, 5):
        return 0.85
    if month in (6, 7, 8):
        return 1.0
    return 0.62


def _round3(value: float) -> Decimal:
    return Decimal(str(round(max(value, 0.0), 3)))


def _simulate_pv_generation_kwh(customer_id: int, consumption_date: date) -> Decimal:
    rng = random.Random((customer_id * 200000) + consumption_date.toordinal())
    seasonal = _pv_seasonal_factor(consumption_date.month)
    cloud_factor = rng.uniform(0.0, 1.15)
    has_low_solar_day = rng.random() < (0.35 if consumption_date.month in (11, 12, 1, 2) else 0.14)
    value = 0.0 if has_low_solar_day else 10.2 * seasonal * cloud_factor
    return _round3(value)


def _backfill_energy_fields() -> None:
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT consumption_id, customer_id, consumption_date, consumption_kwh
                FROM core_daily_consumption
                """
            )
        )
    )

    updates: list[dict[str, object]] = []
    for row in rows:
        consumption_kwh = Decimal(str(row.consumption_kwh)).quantize(Decimal("0.001"))
        pv_generation_kwh = _simulate_pv_generation_kwh(row.customer_id, row.consumption_date).quantize(Decimal("0.001"))

        self_consumption_kwh = min(consumption_kwh, pv_generation_kwh)
        grid_import_kwh = max(consumption_kwh - self_consumption_kwh, Decimal("0")).quantize(Decimal("0.001"))
        grid_export_kwh = max(pv_generation_kwh - self_consumption_kwh, Decimal("0")).quantize(Decimal("0.001"))

        if pv_generation_kwh > 0:
            self_consumption_share_pct = (
                ((pv_generation_kwh - grid_export_kwh) / pv_generation_kwh) * Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            self_consumption_share_pct = Decimal("0.00")

        updates.append(
            {
                "consumption_id": row.consumption_id,
                "grid_import_kwh": grid_import_kwh,
                "grid_export_kwh": grid_export_kwh,
                "pv_generation_kwh": pv_generation_kwh,
                "self_consumption_share_pct": self_consumption_share_pct,
            }
        )

    if updates:
        bind.execute(
            sa.text(
                """
                UPDATE core_daily_consumption
                SET
                    grid_import_kwh = :grid_import_kwh,
                    grid_export_kwh = :grid_export_kwh,
                    pv_generation_kwh = :pv_generation_kwh,
                    self_consumption_share_pct = :self_consumption_share_pct
                WHERE consumption_id = :consumption_id
                """
            ),
            updates,
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("core_daily_consumption")}

    if "grid_import_kwh" not in existing_columns:
        op.add_column(
            "core_daily_consumption",
            sa.Column("grid_import_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
        )
    if "grid_export_kwh" not in existing_columns:
        op.add_column(
            "core_daily_consumption",
            sa.Column("grid_export_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
        )
    if "pv_generation_kwh" not in existing_columns:
        op.add_column(
            "core_daily_consumption",
            sa.Column("pv_generation_kwh", sa.Numeric(10, 3), nullable=False, server_default="0"),
        )
    if "self_consumption_share_pct" not in existing_columns:
        op.add_column(
            "core_daily_consumption",
            sa.Column("self_consumption_share_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        )

    _backfill_energy_fields()

    existing_constraints = {constraint["name"] for constraint in inspector.get_check_constraints("core_daily_consumption")}

    if "ck_daily_consumption_non_negative" not in existing_constraints:
        op.create_check_constraint(
            "ck_daily_consumption_non_negative",
            "core_daily_consumption",
            "consumption_kwh >= 0",
        )
    if "ck_daily_grid_import_non_negative" not in existing_constraints:
        op.create_check_constraint(
            "ck_daily_grid_import_non_negative",
            "core_daily_consumption",
            "grid_import_kwh >= 0",
        )
    if "ck_daily_grid_export_non_negative" not in existing_constraints:
        op.create_check_constraint(
            "ck_daily_grid_export_non_negative",
            "core_daily_consumption",
            "grid_export_kwh >= 0",
        )
    if "ck_daily_pv_generation_non_negative" not in existing_constraints:
        op.create_check_constraint(
            "ck_daily_pv_generation_non_negative",
            "core_daily_consumption",
            "pv_generation_kwh >= 0",
        )
    if "ck_daily_self_consumption_share_pct_range" not in existing_constraints:
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_constraints = {constraint["name"] for constraint in inspector.get_check_constraints("core_daily_consumption")}

    if "ck_daily_self_consumption_share_pct_range" in existing_constraints:
        op.drop_constraint("ck_daily_self_consumption_share_pct_range", "core_daily_consumption", type_="check")
    if "ck_daily_pv_generation_non_negative" in existing_constraints:
        op.drop_constraint("ck_daily_pv_generation_non_negative", "core_daily_consumption", type_="check")
    if "ck_daily_grid_export_non_negative" in existing_constraints:
        op.drop_constraint("ck_daily_grid_export_non_negative", "core_daily_consumption", type_="check")
    if "ck_daily_grid_import_non_negative" in existing_constraints:
        op.drop_constraint("ck_daily_grid_import_non_negative", "core_daily_consumption", type_="check")
    if "ck_daily_consumption_non_negative" in existing_constraints:
        op.drop_constraint("ck_daily_consumption_non_negative", "core_daily_consumption", type_="check")

    existing_columns = {column["name"] for column in inspector.get_columns("core_daily_consumption")}
    if "self_consumption_share_pct" in existing_columns:
        op.drop_column("core_daily_consumption", "self_consumption_share_pct")
    if "pv_generation_kwh" in existing_columns:
        op.drop_column("core_daily_consumption", "pv_generation_kwh")
    if "grid_export_kwh" in existing_columns:
        op.drop_column("core_daily_consumption", "grid_export_kwh")
    if "grid_import_kwh" in existing_columns:
        op.drop_column("core_daily_consumption", "grid_import_kwh")
