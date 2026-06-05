"""Read-only SQL proxy — безопасное выполнение SQL-запросов к базе 1С.

Перед выполнением проверяет имена таблиц через ORM (InformationSchemaColumn),
и если таблица не найдена — ищет похожие и подсказывает.
"""

from __future__ import annotations

import difflib
import re

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from py1cv8.sql.orm.engine import is_mssql_url, session_scope
from py1cv8.sql.orm.models import InformationSchemaColumn


class ReadOnlyError(ValueError):
    """Запрос не является read-only."""


_READONLY_PREFIXES = ("SELECT", "EXPLAIN", "WITH", "SHOW", "DESCRIBE")


def _validate_readonly(sql: str) -> None:
    """Проверить, что SQL-запрос является read-only."""
    stripped = sql.strip()
    first_word = stripped.split()[0] if stripped.split() else "empty"
    if not stripped:
        raise ReadOnlyError("Empty query")
    for prefix in _READONLY_PREFIXES:
        if stripped.upper().startswith(prefix):
            return
    raise ReadOnlyError(f"Only SELECT/EXPLAIN/WITH queries allowed, got: {first_word}")


def _extract_table_name(sql: str) -> str | None:
    """Извлечь первое имя таблицы после FROM (упрощённый парсинг)."""
    m = re.search(r'\bFROM\s+"?([a-zA-Z_]\w*)"?(?:\s|$)', sql, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\bFROM\s+\[([^\]]+)\]", sql, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _validate_tables_orm(db_url: str, sql: str) -> str | None:
    """Проверить таблицу из SQL через ORM.

    Если таблица не найдена — вернуть сообщение с похожими именами.
    Если найдена — вернуть None (всё в порядке).
    """
    table_name = _extract_table_name(sql)
    if not table_name:
        return None  # Не удалось определить таблицу — пропускаем проверку

    schema = "dbo" if is_mssql_url(db_url) else "public"

    with session_scope(db_url) as session:
        # Проверяем существование таблицы через ORM
        stmt = (
            select(InformationSchemaColumn.table_name)
            .where(
                InformationSchemaColumn.table_name == table_name,
                InformationSchemaColumn.table_schema == schema,
            )
            .limit(1)
        )
        found = session.execute(stmt).scalar()

    if found:
        return None  # Таблица существует

    # Таблица не найдена — ищем похожие
    with session_scope(db_url) as session:
        stmt = (
            select(InformationSchemaColumn.table_name)
            .distinct()
            .where(InformationSchemaColumn.table_schema == schema)
            .order_by(InformationSchemaColumn.table_name)
        )
        all_tables = session.execute(stmt).scalars().all()

    close = difflib.get_close_matches(table_name, all_tables, n=5, cutoff=0.3)
    if close:
        return f"Table '{table_name}' not found. Did you mean: {', '.join(close)}?"
    return f"Table '{table_name}' not found in schema '{schema}'."


def execute_readonly(db_url: str, sql: str) -> list[dict]:
    """Выполнить read-only SQL-запрос с ORM-валидацией таблиц.

    Args:
        db_url: URL базы данных (postgresql:// или mssql://).
        sql: Read-only SQL-запрос (SELECT/EXPLAIN/WITH/SHOW/DESCRIBE).

    Returns:
        Список словарей {колонка: значение}.

    Raises:
        ReadOnlyError: Если запрос не read-only.
        RuntimeError: С человекочитаемым описанием ошибки.
    """
    _validate_readonly(sql)

    # ORM-валидация таблиц перед выполнением
    validation_error = _validate_tables_orm(db_url, sql)
    if validation_error:
        raise RuntimeError(validation_error)

    # Выполнение запроса (text() — легальное исключение для SQL-proxy)
    with session_scope(db_url) as session:
        try:
            result = session.execute(text(sql))
            if result.returns_rows:  # type: ignore[attr-defined]
                columns = list(result.keys())
                return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
            return []
        except SQLAlchemyError as e:
            error_msg = str(e)
            table_name = _extract_table_name(sql)
            bad_col = _extract_column_name(error_msg)

            parts = [f"SQL execution failed: {error_msg.split('LINE')[0].strip()}"]
            if bad_col:
                parts.append(f"\nColumn not found: {bad_col}")
                suggestions = _suggest_columns_orm(db_url, table_name, bad_col)
                if suggestions:
                    parts.append(f"Did you mean: {', '.join(suggestions)}?")
            raise RuntimeError("".join(parts)) from e


def _extract_column_name(error_msg: str) -> str | None:
    """Извлечь имя несуществующей колонки из текста ошибки."""
    m = re.search(r'column\s+"([^"]+)"', error_msg, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'"([^"]+)"\s+does not exist', error_msg, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _suggest_columns_orm(
    db_url: str,
    table_name: str | None,
    bad_column: str,
) -> list[str]:
    """Найти похожие колонки через ORM (InformationSchemaColumn)."""
    if not table_name:
        return []
    try:
        with session_scope(db_url) as session:
            stmt = (
                select(InformationSchemaColumn.column_name)
                .where(InformationSchemaColumn.table_name == table_name)
                .order_by(InformationSchemaColumn.ordinal_position)
            )
            cols = session.execute(stmt).scalars().all()
    except Exception:
        return []
    return difflib.get_close_matches(bad_column, cols, n=5, cutoff=0.3)
