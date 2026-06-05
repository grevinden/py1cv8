"""Describe table structure via information_schema."""

from __future__ import annotations

import re

from sqlalchemy import create_engine, text


def _extract_prefix(name: str) -> str:
    """Strip trailing digits to get the table name prefix.

    Example: ``_InfoRg33`` → ``_InfoRg``, ``_Reference117`` → ``_Reference``.
    """
    return re.sub(r"\d+$", "", name, count=1)


def _find_similar_tables(engine, table_name: str) -> list[str]:
    """Return list of existing table names that share the same prefix."""
    prefix = _extract_prefix(table_name)
    if not prefix or prefix == table_name:
        prefix = table_name

    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name ILIKE :pattern "
                "ORDER BY table_name LIMIT 10"
            ),
            {"pattern": f"{prefix}%"},
        )
        matches = [r[0] for r in result.fetchall()]

    return matches


def describe_table(db_url: str, table_name: str) -> list[dict]:
    """Return column metadata for *table_name* from information_schema.

    When the table is not found, returns an error dict with suggestions.
    """
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            sql = text(
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    character_maximum_length,
                    ordinal_position
                FROM information_schema.columns
                WHERE LOWER(table_name) = LOWER(:table_name)
                ORDER BY ordinal_position
                """
            )
            result = conn.execute(sql, {"table_name": table_name})
            columns = list(result.keys())
            rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

        if not rows:
            similar = _find_similar_tables(engine, table_name)
            msg = f"Table '{table_name}' not found"
            if similar:
                msg += f". Did you mean: {', '.join(similar[:5])}?"
            return [{"error": msg}]

        return rows
    finally:
        engine.dispose()
