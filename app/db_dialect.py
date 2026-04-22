from __future__ import annotations


def is_mysql_family(dialect_name: str | None) -> bool:
    """Return True for MySQL-compatible dialects (including MariaDB)."""
    if not dialect_name:
        return False
    normalized = dialect_name.lower()
    return normalized.startswith("mysql") or normalized.startswith("mariadb")


def normalize_database_url(url: str) -> str:
    """Normalize user-friendly DB URLs to SQLAlchemy dialect+driver URLs."""
    value = url.strip()
    if value.startswith("mariadb://"):
        return "mysql+pymysql://" + value[len("mariadb://"):]
    if value.startswith("mysql://"):
        return "mysql+pymysql://" + value[len("mysql://"):]
    return value
