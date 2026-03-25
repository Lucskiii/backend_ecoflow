"""move customer coordinates to site

Revision ID: 0004_move_customer_coordinates_to_site
Revises: 0002_customer_address_coords
Create Date: 2026-03-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_move_customer_coordinates_to_site"
down_revision = "0002_customer_address_coords"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "core_customer", "latitude"):
        op.drop_column("core_customer", "latitude")
    if _has_column(inspector, "core_customer", "longitude"):
        op.drop_column("core_customer", "longitude")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "core_customer", "latitude"):
        op.add_column("core_customer", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    if not _has_column(inspector, "core_customer", "longitude"):
        op.add_column("core_customer", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))
