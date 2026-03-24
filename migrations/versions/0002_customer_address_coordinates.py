"""add customer address and coordinate fields

Revision ID: 0002_customer_address_coordinates
Revises: 0001_initial_models
Create Date: 2026-03-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_customer_address_coordinates"
down_revision = "0001_initial_models"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    additions = [
        ("address_line1", sa.String(length=255), True),
        ("city", sa.String(length=120), True),
        ("postal_code", sa.String(length=32), True),
        ("country", sa.String(length=120), True),
        ("latitude", sa.Numeric(9, 6), True),
        ("longitude", sa.Numeric(9, 6), True),
    ]

    for column_name, column_type, nullable in additions:
        if not _has_column(inspector, "core_customer", column_name):
            op.add_column("core_customer", sa.Column(column_name, column_type, nullable=nullable))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for column_name in ("longitude", "latitude", "country", "postal_code", "city", "address_line1"):
        if _has_column(inspector, "core_customer", column_name):
            op.drop_column("core_customer", column_name)
