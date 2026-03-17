"""initial mysql schema foundation

Revision ID: 0001_initial_models
Revises:
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from app.database import Base
import app.models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001_initial_models"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()

    # Keep this migration deterministic: it must represent the initial schema only.
    # New tables/columns are added in later revisions and must not be created here.
    sa.Table(
        "core_customer",
        metadata,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("external_ref", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("external_ref"),
    )

    for table in Base.metadata.sorted_tables:
        if table.name in {"core_customer", "core_daily_consumption"}:
            continue
        table.to_metadata(metadata)

    metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name == "core_daily_consumption":
            continue
        table.to_metadata(metadata)

    metadata.drop_all(bind=bind)
