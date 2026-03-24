"""compatibility placeholder for historical daily consumption revision

Revision ID: 0003_add_core_daily_consumption
Revises: 0002_add_customer_password_hash
Create Date: 2026-03-10 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_core_daily_consumption"
down_revision = "0002_add_customer_password_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This repository version doesn't need to alter schema for this historical revision.
    # The revision is retained so existing databases stamped with this id can migrate forward.
    pass


def downgrade() -> None:
    pass
