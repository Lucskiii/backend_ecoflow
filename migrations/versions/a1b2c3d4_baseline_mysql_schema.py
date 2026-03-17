"""Baseline schema from mysql_schema.sql

Revision ID: a1b2c3d4
Revises:
Create Date: 2026-03-17
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

# Keep revision ids short so alembic_version.version_num (VARCHAR(32) on MySQL) never overflows.
revision = "a1b2c3d4"
down_revision = None
branch_labels = None
depends_on = None


def _schema_statements() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    schema_file = repo_root / "sql" / "mysql_schema.sql"
    sql_text = schema_file.read_text(encoding="utf-8")
    statements: list[str] = []
    for raw_statement in sql_text.split(";"):
        statement = raw_statement.strip()
        if not statement:
            continue
        upper = statement.upper()
        if upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
            continue
        statements.append(statement)
    return statements


def upgrade() -> None:
    for statement in _schema_statements():
        op.execute(statement)


def downgrade() -> None:
    # Baseline migration: downgrade is intentionally empty.
    pass
