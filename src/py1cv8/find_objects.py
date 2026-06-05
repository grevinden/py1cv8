"""Поиск объектов метаданных 1С по ключевому слову в имени или синониме.

Модуль реализует поиск объектов метаданных конфигурации 1С (справочников,
документов, регистров, обработок и т.д.) по текстовому ключевому слову.
Поиск выполняется в два этапа: сначала точное подстроковое совпадение
в техническом имени (tech_name) или синонимах (display_names), затем
нечёткое сравнение (fuzzy matching) через difflib.get_close_matches.

Использует build_llm_context для получения полного списка объектов
метаданных, избегая дублирования логики парсинга блобов и DBNames.

Пример использования:
    from py1cv8.find_objects import find_objects

    results = find_objects("postgresql://user:pass@host/db", "Товары")
    for obj in results:
        print(obj["tech_name"], obj.get("display_names", {}).get("ru"))
"""

from __future__ import annotations

import difflib

from py1cv8.context import build_llm_context


def find_objects(
    db_url: str,
    keyword: str,
    limit: int = 50,
) -> list[dict]:
    """Поиск объектов метаданных, содержащих ключевое слово в имени или синониме.

    Выполняет поиск в два этапа:
    1. Подстроковое совпадение (case-insensitive) — ищет keyword в tech_name
       и во всех display_names каждого объекта.
    2. Нечёткое совпадение (fuzzy) — если после этапа 1 осталось место
       до лимита, применяет difflib.get_close_matches с порогом 0.6.

    Результаты дедуплицируются по UUID: каждый объект попадает в вывод
    только один раз, даже если совпадение найдено в нескольких полях.

    Args:
        db_url: SQLAlchemy URL подключения к базе данных 1С
            (например, postgresql://user:password@host:5432/database).
        keyword: Ключевое слово для поиска. Регистр не учитывается.
        limit: Максимальное количество возвращаемых объектов (по умолчанию 50).
            Если установлено в 0, возвращаются все найденные совпадения.

    Returns:
        Список словарей с найденными объектами метаданных. Каждый словарь
        содержит те же поля, что и вывод context: uuid, tech_name,
        display_names, type_num, category, table_name и т.д.
        Результаты отсортированы по релевантности: сначала точные
        подстроковые совпадения, затем нечёткие.

    Raises:
        SQLAlchemyError: При проблемах подключения к базе данных.

    Example:
        >>> objs = find_objects("postgresql://user:pass@localhost/db", "Счёт")
        >>> len(objs)
        3
        >>> objs[0]["tech_name"]
        'Счета'
    """
    ctx = build_llm_context(db_url)
    keyword_lower = keyword.lower()

    seen: set[str] = set()
    results: list[dict] = []

    # Phase 1: substring matching
    for obj in ctx["objects"]:
        obj_uuid = obj.get("uuid", "")
        tech_name = obj.get("tech_name") or ""
        display_names = obj.get("display_names") or {}

        if keyword_lower in tech_name.lower():
            if obj_uuid not in seen:
                seen.add(obj_uuid)
                results.append(obj)
            continue

        for name in display_names.values():
            if keyword_lower in name.lower():
                if obj_uuid not in seen:
                    seen.add(obj_uuid)
                    results.append(obj)
                break

        if len(results) >= limit:
            return results[:limit]

    # Phase 2: fuzzy matching (if room)
    if len(results) < limit:
        fuzzy_pool: list[tuple[str, str]] = []  # (uuid, name)
        for obj in ctx["objects"]:
            obj_uuid = obj.get("uuid", "")
            if obj_uuid in seen:
                continue
            tech = obj.get("tech_name") or ""
            if tech:
                fuzzy_pool.append((obj_uuid, tech))
            for name in (obj.get("display_names") or {}).values():
                if name:
                    fuzzy_pool.append((obj_uuid, name))

        pool_map: dict[str, str] = {}
        for uid, name in fuzzy_pool:
            if uid not in pool_map:
                pool_map[uid] = name

        fuzzy_matches = difflib.get_close_matches(
            keyword_lower,
            [v.lower() for v in pool_map.values()],
            n=limit - len(results),
            cutoff=0.6,
        )

        for obj in ctx["objects"]:
            if len(results) >= limit:
                break
            obj_uuid = obj.get("uuid", "")
            if obj_uuid in seen:
                continue
            tech = (obj.get("tech_name") or "").lower()
            display_vals = [v.lower() for v in (obj.get("display_names") or {}).values()]
            if tech in fuzzy_matches or any(v in fuzzy_matches for v in display_vals):
                seen.add(obj_uuid)
                results.append(obj)

    return results[:limit]
