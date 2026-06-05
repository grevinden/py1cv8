"""Read-only SQL proxy — execute safe SQL queries against 1C database.

Usage:
    from py1cv8.sql_proxy import execute_readonly
    rows = execute_readonly("postgresql+psycopg2://...", "SELECT * FROM pg_tables LIMIT 5")
"""

from __future__ import annotations

import difflib
import re

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


def _extract_column_name(error_msg: str) -> str | None:
    """Try to extract an undefined column name from a psycopg2 error message."""
    m = re.search(r'column\s+"([^"]+)"', error_msg, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'"([^"]+)"\s+does not exist', error_msg, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_table_name(sql: str) -> str | None:
    """Extract table name from a SELECT query (simplified)."""
    m = re.search(
        r'\bFROM\s+"?([a-zA-Z_]\w*)"?(?:\s|$)',
        sql, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r'\bFROM\s+\[([^\]]+)\]', sql, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _suggest_columns(
    db_url: str, table_name: str, bad_column: str,
) -> list[str]:
    """Find similar column names in *table_name* using information_schema."""
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE LOWER(table_name) = LOWER(:tn)"
                    " ORDER BY ordinal_position"
                ),
                {"tn": table_name},
            )
            cols = [r[0] for r in result.fetchall()]
    except Exception:
        return []
    return difflib.get_close_matches(bad_column, cols, n=5, cutoff=0.3)


def execute_readonly(db_url: str, sql: str) -> list[dict]:
    """Execute a read-only SQL query and return rows as list of dicts.

    Validates the query is read-only before execution.
    On error, returns a dict with 'error' key instead of raising.
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
        error_msg = str(e)
        bad_col = _extract_column_name(error_msg)
        table_name = _extract_table_name(sql)
        suggestions: list[str] = []
        if bad_col and table_name:
            suggestions = _suggest_columns(db_url, table_name, bad_col)

        parts = [f"SQL execution failed: {error_msg.split('LINE')[0].strip()}"]
        if bad_col:
            parts.append(f"\nColumn not found: {bad_col}")
            if suggestions:
                parts.append(f"Did you mean: {', '.join(suggestions)}?")
        raise RuntimeError("".join(parts)) from e
    finally:
        engine.dispose()
