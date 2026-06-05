"""Read-only SQL proxy — execute safe SQL queries against 1C database.

Usage:
    from py1cv8.sql_proxy import execute_readonly
    rows = execute_readonly("postgresql+psycopg2://...", "SELECT * FROM pg_tables LIMIT 5")
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


class ReadOnlyError(ValueError):
    """Raised when a non-SELECT query is attempted."""


_READONLY_PREFIXES = ("SELECT", "EXPLAIN", "WITH", "SHOW", "DESCRIBE")


def _validate_readonly(sql: str) -> None:
    stripped = sql.strip()
    first_word = stripped.split()[0] if stripped.split() else "empty"
    if not stripped:
        raise ReadOnlyError("Empty query")
    for prefix in _READONLY_PREFIXES:
        if stripped.upper().startswith(prefix):
            return
    raise ReadOnlyError(
        f"Only SELECT/EXPLAIN/WITH queries allowed, got: {first_word}"
    )


def execute_readonly(db_url: str, sql: str) -> list[dict]:
    """Execute a read-only SQL query and return rows as list of dicts.

    Validates the query is read-only before execution.
    """
    _validate_readonly(sql)
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                columns = list(result.keys())
                return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
            return []
    except SQLAlchemyError as e:
        raise RuntimeError(f"SQL execution failed: {e}") from e
    finally:
        engine.dispose()
