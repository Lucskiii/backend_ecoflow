"""add core daily consumption table

Revision ID: 0003_add_core_daily_consumption
Revises: 0002_add_customer_password_hash
Create Date: 2026-03-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_add_core_daily_consumption"
down_revision = "0002_add_customer_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "core_daily_consumption" not in inspector.get_table_names():
        op.create_table(
            "core_daily_consumption",
            sa.Column("consumption_id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.BigInteger(), nullable=False),
            sa.Column("consumption_date", sa.Date(), nullable=False),
            sa.Column("consumption_kwh", sa.Numeric(10, 3), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="simulated"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["customer_id"], ["core_customer.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("consumption_id"),
            sa.UniqueConstraint("customer_id", "consumption_date", name="uq_daily_consumption_customer_date"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("core_daily_consumption")}
    if "ix_daily_consumption_customer_date" not in existing_indexes:
        op.create_index(
            "ix_daily_consumption_customer_date",
            "core_daily_consumption",
            ["customer_id", "consumption_date"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "core_daily_consumption" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("core_daily_consumption")}
    if "ix_daily_consumption_customer_date" in existing_indexes:
        op.drop_index("ix_daily_consumption_customer_date", table_name="core_daily_consumption")
    op.drop_table("core_daily_consumption")
