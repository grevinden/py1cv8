"""Описание структуры таблиц 1С через information_schema.

Модуль предоставляет единственную публичную функцию describe_table,
которая извлекает метаданные колонок таблицы: имя, тип данных, nullable,
максимальную длину и порядковую позицию.

При отсутствии таблицы модуль автоматически пытается найти похожие
таблицы по префиксу имени и предлагает альтернативы.

Ответственность (SRP): только работа со схемой таблиц через
information_schema. Никакой бизнес-логики, парсинга метаданных или
форматирования вывода.

Пример использования:
    >>> from py1cv8.schema_describe import describe_table
    >>> cols = describe_table("postgresql://...", "_Reference117")
    >>> for col in cols:
    ...     print(col["column_name"], col["data_type"])
    ...
    _idrref uuid
    _description varchar
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, text


def _extract_prefix(name: str) -> str:
    """Извлечь префикс имени таблицы, отбросив尾数字.

    Например, для '_InfoRg33' вернёт '_InfoRg',
    для '_Reference117' — '_Reference'.

    Args:
        name: Полное имя таблицы 1С (например, '_Reference117').

    Returns:
        Префикс таблицы без цифрового суффикса.
        Если цифр в конце нет, возвращает исходное имя.
    """
    return re.sub(r"\d+$", "", name, count=1)


def _find_similar_tables(engine, table_name: str) -> list[str]:
    """Найти существующие таблицы, похожие на указанную.

    Стратегия поиска:
    1. Сначала ищет таблицы с тем же префиксом (например, '_Reference%').
    2. Если ничего не найдено — возвращает первые 10 таблиц схемы 'public'
       как общую подсказку (исключая системные pg_*).

    Args:
        engine: Движок SQLAlchemy для подключения к БД.
        table_name: Имя таблицы для поиска аналогов.

    Returns:
        Список имён таблиц (до 10), похожих на искомую.
        Может быть пустым.
    """
    prefix = _extract_prefix(table_name)
    if not prefix or prefix == table_name:
        prefix = table_name

    with engine.connect() as conn:
        # Try prefix match first
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

        if not matches:
            # Fallback: show most common tables as a generic suggestion
            result = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name NOT LIKE 'pg_%' "
                    "ORDER BY table_name LIMIT 10"
                ),
            )
            matches = [r[0] for r in result.fetchall()]

    return matches


def describe_table(db_url: str, table_name: str) -> list[dict]:
    """Получить метаданные колонок таблицы через information_schema.

    Выполняет запрос к information_schema.columns для указанной таблицы
    и возвращает список колонок с их характеристиками.

    Если таблица не найдена, возвращает список с одним словарём,
    содержащим ключ 'error' с описанием ошибки и предложением похожих
    таблиц (через _find_similar_tables).

    Args:
        db_url: URL подключения к БД (SQLAlchemy-совместимый).
        table_name: Имя таблицы (регистронезависимое, через LOWER).

    Returns:
        Список словарей с ключами:
          - column_name — имя колонки
          - data_type — тип данных SQL
          - is_nullable — YES/NO
          - character_maximum_length — макс. длина (str) или None
          - ordinal_position — порядковая позиция (int)
        Если таблица не найдена:
          [{"error": "Table 'xxx' not found. Did you mean: ..."}]
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
