"""Маппинг технических имён объектов метаданных 1С в физические имена таблиц БД.

Модуль предоставляет функцию list_tables, которая возвращает для каждого
объекта метаданных конфигурации 1С информацию о соответствующей физической
таблице в базе данных.

Единственная ответственность (SRP): предоставить готовый маппинг
"UUID / tech_name → имя физической таблицы" для использования командой
tables в CLI. Не занимается парсингом блобов или DBNames — делегирует
это build_llm_context.

Пример использования:
    from py1cv8.list_tables import list_tables

    tables = list_tables("postgresql://user:pass@host/db")
    for t in tables:
        print(t["tech_name"], "→", t["table_name"])
"""

from __future__ import annotations

from py1cv8.context import build_llm_context


def list_tables(db_url: str) -> list[dict]:
    """Возвращает маппинг всех объектов метаданных 1С на их физические таблицы.

    Переиспользует build_llm_context для получения полного контекста
    метаданных, включая DBNames-парсинг и маппинг type_num → категория.
    Таким образом, вся логика работы с блобами и params-таблицей
    централизована в context.py, а list_tables выступает тонкой
    обёрткой для CLI-команды tables.

    Args:
        db_url: SQLAlchemy URL подключения к базе данных 1С
            (например, postgresql://user:password@host:5432/database).

    Returns:
        Список словарей, каждый из которых содержит:
        - uuid: UUID объекта метаданных
        - tech_name: Техническое имя объекта
        - display_names: Словарь синонимов {код_языка: название}
        - type_num: Числовой код типа объекта (например, 57 для справочников)
        - category: Человекочитаемая категория ("Catalogs", "Documents", ...)
        - table_name: Физическое имя таблицы в БД ("_Reference53", ...)

    Raises:
        SQLAlchemyError: При проблемах подключения к базе данных.

    Example:
        >>> tables = list_tables("postgresql://user:pass@localhost/db")
        >>> tables[0]["table_name"]
        '_Reference53'
    """
    ctx = build_llm_context(db_url)
    return ctx["objects"]
