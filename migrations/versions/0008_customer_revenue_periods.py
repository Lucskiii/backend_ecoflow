"""add persisted customer revenue periods

Revision ID: 0008_customer_revenue_periods
Revises: 0007_bi_run_city
Create Date: 2026-04-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_customer_revenue_periods"
down_revision = "0007_bi_run_city"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "core_customer_revenue_period"):
        return

    op.create_table(
        "core_customer_revenue_period",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("core_customer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_code", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("revenue_eur", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("calculated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("period_code IN ('all','30d','7d')", name="chk_customer_revenue_period_code"),
        sa.UniqueConstraint("customer_id", "period_code", name="uq_customer_revenue_period"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "core_customer_revenue_period"):
        op.drop_table("core_customer_revenue_period")
