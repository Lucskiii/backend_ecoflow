"""Rename legacy core_customer.id to core_customer.customer_id

Revision ID: b2c3d4e5
Revises: a1b2c3d4
Create Date: 2026-03-17
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "b2c3d4e5"
down_revision = "a1b2c3d4"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    has_legacy_id = _column_exists("core_customer", "id")
    has_customer_id = _column_exists("core_customer", "customer_id")

    if has_legacy_id and not has_customer_id:
        op.execute(
            """
            ALTER TABLE core_customer
            CHANGE COLUMN id customer_id BIGINT NOT NULL AUTO_INCREMENT
            """
        )


def downgrade() -> None:
    has_legacy_id = _column_exists("core_customer", "id")
    has_customer_id = _column_exists("core_customer", "customer_id")

    if has_customer_id and not has_legacy_id:
        op.execute(
            """
            ALTER TABLE core_customer
            CHANGE COLUMN customer_id id BIGINT NOT NULL AUTO_INCREMENT
            """
        )
