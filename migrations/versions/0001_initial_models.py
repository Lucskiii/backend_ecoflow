"""initial mysql schema foundation

Revision ID: 0001_initial_models
Revises:
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op

from app.database import Base
import app.models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001_initial_models"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
