"""add password hash to core customer

Revision ID: 0002_add_customer_password_hash
Revises: 0001_initial_models
Create Date: 2026-03-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_customer_password_hash"
down_revision = "0001_initial_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_customer", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("core_customer", "password_hash")
