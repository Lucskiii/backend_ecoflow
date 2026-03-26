"""add core analysis city table

Revision ID: 0005_add_core_analysis_city
Revises: 0004_move_customer_coords
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_add_core_analysis_city"
down_revision = "0004_move_customer_coords"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "core_analysis_city"):
        return

    op.create_table(
        "core_analysis_city",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("city_name", sa.String(length=255), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=True),
        sa.Column("country_name", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("open_meteo_location_id", sa.BigInteger(), nullable=True),
        sa.Column("admin1", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city_name", "country_code", name="uq_core_analysis_city_name_country"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "core_analysis_city"):
        op.drop_table("core_analysis_city")
