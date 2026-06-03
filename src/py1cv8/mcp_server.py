# ruff: noqa: E501
"""MCP server for 1C data access — tools for AI to query & understand 1C metadata.

## Система: 1С-база данных с метаданными

В системе есть объекты следующих типов:
- **Справочники (Catalogs)** — списки сущностей: контрагенты, товары, сотрудники и т.д.
- **Документы (Documents)** — события/операции: накладные, счета, акты, заказы.
- **Регистры сведений (InformationRegisters)** — периодические значения: курсы валют, цены, настройки.
- **Регистры накопления (AccumulationRegisters)** — остатки и обороты: товары на складах, деньги.
- **Регистры бухгалтерии (AccountingRegisters)** — бухгалтерские проводки (Дт/Кт).
- **Перечисления (Enums)** — фиксированные наборы значений (типы, статусы).
- **Константы (Constants)** — одиночные настройки системы.
- **Подсистемы (Subsystems)** — логическая группировка объектов метаданных, не имеют таблиц в БД.
- **Планы видов характеристик (ChartsOfCharacteristicTypes)** — определяемые пользователем реквизиты.

## Терминология (что говорят пользователи → что искать в системе)
- **Контрагент** → справочник Контрагенты (Catalog: Reference)
- **Товар, Номенклатура** → справочник Номенклатура (Catalog: Reference)
- **Склад** → справочник Склады (Catalog: Reference)
- **Накладная, Реализация** → документ продажи (Document)
- **Счёт (на оплату)** → документ СчётНаОплату (Document)
- **Акт** → документ АктВыполненныхРабот (Document)
- **Проводка** → запись в регистре бухгалтерии (AccountingRegister)
- **Остатки** → регистр накопления (AccumulationRegister)
- **Обороты** → обороты по регистру за период
- **Проведение** — действие, при котором документ создаёт движения в регистрах
- **GUID/UUID** — уникальный идентификатор объекта в 1С (строка 36 символов)

## Соглашения об именах таблиц
- Основные таблицы: `_reference{N}`, `_document{N}`, `_inforg{N}`, `_const{N}`, `_enum{N}`
- Подтаблицы: `_{main}_{type}{N}` (например, `_reference53_vt59` — табличная часть)
- Системные таблицы: `_accopt`, `_bots`, `_node`, `_ext{...}`

## Форматы данных
- Даты: ISO 8601 (ГГГГ-ММ-ДД) или ДД.ММ.ГГГГ
- Суммы: числа с плавающей точкой (рубли с копейками)
- GUID: строка вида `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
"""

from __future__ import annotations

import dataclasses
import json
import re as _re
from collections.abc import Callable

from mcp.server import Server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)
from pydantic import AnyUrl
from sqlalchemy import text

from py1cv8.compress import extract_code_blocks, try_decompress
from py1cv8.config import AVAILABLE_DBS, DB_DIALECT, EXPORT_DIR
from py1cv8.metadata_xml import DIR_TO_TYPE
from py1cv8.query_translator import extract_queries_from_bsl
from py1cv8.schema import ObjectInfo, SchemaLoader, SchemaRegistry, ServiceTableInfo

_loader: SchemaLoader = SchemaLoader()

# ── Helpers ─────────────────────────────────────────────────────────────


def _serialize(val: object) -> object:
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray, memoryview)):
        n = len(val) if isinstance(val, (bytes, bytearray)) else val.nbytes
        return f"<binary {n} bytes>"
    return val


def _xml_summary(obj: ObjectInfo) -> dict:
    """Extract a human-readable summary from XML metadata."""
    xm = obj.metadata_xml
    if xm is None:
        return {}
    summary: dict = {
        "synonym": xm.synonym,
        "comment": xm.comment,
    }
    if xm.attributes:
        summary["attributes"] = sorted(
            [
                {
                    "name": a.name,
                    "synonym": a.synonym,
                    "type": a.type_info.display,
                    "indexing": a.indexing,
                    "password_mode": a.password_mode,
                    "full_text_search": a.full_text_search,
                }
                for a in xm.attributes
            ],
            key=lambda a: a["name"],
        )
    if xm.tabular_sections:
        summary["tabular_sections"] = [
            {
                "name": ts.name,
                "synonym": ts.synonym,
                "attributes": len(ts.attributes),
            }
            for ts in xm.tabular_sections
        ]
    if xm.enum_values:
        summary["enum_values"] = [
            {"name": v.name, "synonym": v.synonym} for v in xm.enum_values
        ]
    if xm.forms:
        summary["forms"] = xm.forms
    if xm.commands:
        summary["commands"] = [
            {"name": c.name, "synonym": c.synonym, "modifies_data": c.modifies_data}
            for c in xm.commands
        ]
    if xm.generated_types:
        summary["generated_types"] = [
            {"name": g.name, "category": g.category}
            for g in xm.generated_types
        ]
    biz: dict = {}
    for key in (
        "hierarchical", "hierarchy_type", "subordination_use",
        "code_length", "description_length", "code_type",
        "check_unique", "autonumbering", "posting",
        "number_type", "number_length", "number_periodicity",
        "periodicity", "write_mode", "edit_type", "choice_mode",
        "data_lock_control_mode", "full_text_search", "data_history",
        "create_on_input", "input_by_string",
    ):
        val = getattr(xm, key, None)
        if val is not None and val != "" and val != []:
            biz[key] = val
    if biz:
        summary["business_logic"] = biz
    if xm.object_presentation:
        summary["object_presentation"] = xm.object_presentation
    if xm.list_presentation:
        summary["list_presentation"] = xm.list_presentation
    return summary


def _obj_to_dict(obj: ObjectInfo) -> dict:
    result: dict = {
        "uuid": obj.uuid,
        "tech_name": obj.tech_name,
        "display_ru": obj.display_ru,
        "type_num": obj.type_num,
        "category": obj.category,
        "main_table": obj.main_table,
        "table_number": obj.table_number,
        "columns": len(obj.columns),
        "sub_tables": obj.sub_tables,
    }
    xs = _xml_summary(obj)
    if xs:
        result["metadata"] = xs
    return result


def _svc_to_dict(svc: ServiceTableInfo) -> dict:
    return {"table": svc.db_name, "description": svc.description, "columns": len(svc.columns)}


def _bsl_file_for(obj: ObjectInfo) -> str | None:
    """Find and read the BSL module file for a metadata object, if it exists.

    Looks for ``Ext/Module.bsl`` in the object's export directory.
    Returns the file content as string, or None if not found.
    """
    if obj.metadata_xml is None:
        return None
    xm = obj.metadata_xml
    dir_name = DIR_TO_TYPE.get(xm.type_name, xm.type_name)
    # Try to reverse: find the dir key for this type_name
    for dir_key, type_val in DIR_TO_TYPE.items():
        if type_val == xm.type_name:
            dir_name = dir_key
            break
    bsl_path = EXPORT_DIR / dir_name / xm.name / "Ext" / "Module.bsl"
    if not bsl_path.is_file():
        # Also check test_database
        bsl_path = EXPORT_DIR / "test_database" / dir_name / xm.name / "Ext" / "Module.bsl"
    if not bsl_path.is_file():
        return None
    try:
        return bsl_path.read_text("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def _get_bsl_code_from_db(dbname: str, module_name: str) -> list[dict]:
    """Extract BSL module code directly from ConfigStorage in DB.

    Scans all Config blobs, decompresses them, and matches by tech_name/UUID.
    Returns list of {uuid, tech_name, code_blocks} dicts.
    """

    from sqlalchemy import select

    from py1cv8.db import get_session
    from py1cv8.models import Config

    # 1. Build metadata_map from the registry (includes non-table objects)
    reg = _loader(dbname)
    meta_map = reg.metadata_map

    # 2. Build reverse: tech_name → uuid
    name_to_uuid: dict[str, str] = {}
    uuid_to_name: dict[str, str] = {}
    for uuid_val, info in meta_map.items():
        tn = info.get("tech_name", "")
        if tn:
            name_to_uuid[tn.lower()] = uuid_val
            uuid_to_name[uuid_val] = tn

    # 3. Find matching UUIDs
    q = module_name.lower()
    matched_uuids: set[str] = set()
    for tn_lower, uuid_val in name_to_uuid.items():
        if q in tn_lower:
            matched_uuids.add(uuid_val)
    # Also match by UUID fragment
    if not matched_uuids:
        for uuid_val in uuid_to_name:
            if q in uuid_val.lower():
                matched_uuids.add(uuid_val)
    # Also match by display_ru
    if not matched_uuids:
        for uuid_val, info in meta_map.items():
            display = info.get("display_names", {}).get("ru", "")
            if q in display.lower():
                matched_uuids.add(uuid_val)

    # Also search by SchemaRegistry objects: table names, 1С names, UUIDs
    if not matched_uuids:
        q_clean = q.replace("_", "")
        for obj in reg.objects.values():
            main_table = obj.main_table.lower()
            table_clean = main_table.lstrip("_").replace("_", "")
            if q in main_table or q in table_clean or q_clean in table_clean or obj.tech_name and q in obj.tech_name.lower() or obj.display_ru and q in obj.display_ru.lower() or q in obj.uuid.lower():
                matched_uuids.add(obj.uuid)

    if not matched_uuids:
        return []

    # 4. Query Config for .0 blobs matching these UUIDs
    session = get_session(dbname)
    try:
        results: list[dict] = []
        for uuid_val in sorted(matched_uuids):
            # Try exact match and .0 suffix
            uuid_lower = uuid_val.lower()
            q = (
                select(Config)
                .where(
                    (Config.filename == uuid_lower)
                    | (Config.filename == f"{uuid_lower}.0")
                )
                .order_by(Config.partno)
            )
            rows = session.scalars(q).all()

            code_blocks: list[str] = []
            for row in rows:
                if not row.binarydata:
                    continue
                raw = bytes(row.binarydata)
                dec = try_decompress(raw)
                if not dec:
                    continue
                blocks = extract_code_blocks(dec)
                code_blocks.extend(blocks)

            tech_name = uuid_to_name.get(uuid_val, "unknown")
            results.append({
                "uuid": uuid_val,
                "tech_name": tech_name,
                "code_blocks": code_blocks,
                "block_count": len(code_blocks),
            })
    finally:
        session.close()

    return results


def _resolve_table_names(sql: str, reg: SchemaRegistry) -> str:
    """Replace 1C object names in SQL with physical table names.

    Handles:
      - `_reference{N}`, `_document{N}` patterns (already physical, kept as-is)
      - `tech_name` like `ирУведомления`, `Уведомления`
      - `display_ru` like `Алгоритмы (ИР)`
    """
    # Build reverse: all known names → physical table name
    replacements: list[tuple[str, str]] = []
    for obj in reg.objects.values():
        table = obj.main_table
        if obj.tech_name and obj.tech_name not in ("", table):
            # Tech name like "Reference_53" or "ирУведомления"
            replacements.append((obj.tech_name, table))
        if obj.display_ru and obj.display_ru not in ("", obj.tech_name, table):
            # Russian display name
            safe_name = obj.display_ru
            if " " not in safe_name:  # only if single word
                replacements.append((safe_name, table))

    # Sort by length descending to match longer names first
    replacements.sort(key=lambda x: -len(x[0]))

    for name, table in replacements:
        escaped = _re.escape(name)
        sql = _re.sub(
            rf'(?:"(?:\s*){escaped}(?:\s*)")|(?:(?<![a-zA-Z_]){escaped}(?![a-zA-Z_0-9]))',
            table,
            sql,
        )

    return sql


def _make_resolver(reg: SchemaRegistry) -> Callable[[str, str], str | None]:
    """Build a resolver callable for table name mapping from a registry."""
    type_to_cat = {
        "Document": "Documents",
        "Reference": "Catalogs",
        "InfoRg": "InformationRegisters",
        "Enum": "Enums",
        "Const": "Constants",
        "Chrc": "ChartsOfCharacteristicTypes",
        "AccumulationRegister": "AccumulationRegisters",
        "AccountingRegister": "AccountingRegisters",
    }
    def resolver(obj_type: str, obj_name: str) -> str | None:
        for o in reg.objects.values():
            if o.metadata_xml is not None and o.metadata_xml.type_name == obj_type and o.metadata_xml.name == obj_name:
                    return o.main_table
            if o.tech_name == obj_name:
                expected_cat = type_to_cat.get(obj_type)
                if expected_cat and o.category.startswith(expected_cat):
                    return o.main_table
        return None
    return resolver


def _bsl_queries_for(obj: ObjectInfo, reg: SchemaRegistry, dbname: str) -> list[dict] | None:
    """Extract and translate 1C queries from an object's BSL module."""
    bsl_text = _bsl_file_for(obj)
    if bsl_text is None:
        return None
    dialect = DB_DIALECT.get(dbname, "postgresql")
    resolver = _make_resolver(reg)
    result = extract_queries_from_bsl(bsl_text, resolver, dialect=dialect)
    if result.count == 0:
        return None
    return [
        {
            "sql": q.sql,
            "tables_ref": q.referenced_tables,
            "params": q.parameters,
            "note": q.note,
        }
        for q in result.queries
    ]


def _columns_to_dicts(info: ObjectInfo | ServiceTableInfo) -> list[dict]:
    return [
        {"name": c.name, "type": c.data_type, "nullable": c.nullable, "pk": c.is_pk}
        for c in info.columns
    ]


# ── Server info ─────────────────────────────────────────────────────────


_META_TYPE_DESCRIPTIONS: dict[str, str] = {
    "Catalogs": (
        "Справочник — реестр сущностей (контрагенты, товары, сотрудники, склады). "
        "Содержит элементы с уникальным кодом и наименованием. "
        "Если пользователь просит «найти», «показать», «завести» — это справочник."
    ),
    "Documents": (
        "Документ — фиксация события/операции (накладная, счёт, акт, заказ). "
        "Имеет дату, номер, табличные части, может быть проведён (создавать движения в регистрах). "
        "Непроведённый документ — черновик, не влияет на отчёты и остатки."
    ),
    "Subsystems": (
        "Подсистема — логическая группировка объектов метаданных. "
        "Не имеет собственной таблицы в БД. "
        "Используется для ролевого доступа и интерфейсной группировки разделов."
    ),
    "Constants": (
        "Константа — одиночная настройка системы (ставка НДС, название организации). "
        "Всего одно значение на всю систему. Если пользователь спрашивает «какая ставка» или «настройки» — это константы."
    ),
    "Enums": (
        "Перечисление — фиксированный набор значений (типы, статусы, виды операций). "
        "Изменяется только в конфигурации. Используется как аналитика в документах и регистрах."
    ),
    "InformationRegisters": (
        "Регистр сведений — периодические значения: курсы валют, цены номенклатуры, настройки на дату. "
        "Позволяет получить значение на любую дату. Разрез периодичности (день, месяц) задаётся в метаданных."
    ),
    "AccumulationRegisters": (
        "Регистр накопления — хранит остатки и обороты (товары на складах, деньги, продажи). "
        "Движения создаются при проведении документов. "
        "Если пользователь спрашивает «сколько осталось», «остатки», «приход/расход» — это регистр накопления."
    ),
    "AccountingRegisters": (
        "Регистр бухгалтерии — содержит бухгалтерские проводки (корреспонденция счетов Дт/Кт с субконто). "
        "Используется для построения ОСВ, анализа оборотов по счетам, отбора по аналитике."
    ),
    "ChartsOfCharacteristicTypes": (
        "План видов характеристик — определяемые пользователем реквизиты и субконто. "
        "Позволяет расширять аналитику без изменения конфигурации."
    ),
    "ScheduledJobs": "Системный объект: регламентное задание — фоновый процесс, выполняемый по расписанию.",
    "Bots": (
        "Системный объект: бот — программный автомат, обрабатывающий события "
        "(например, WebSocket-соединения). Не является учётным объектом."
    ),
    "Tasks": "Системный объект: задача — элемент workflow, используется в бизнес-процессах.",
    "DocumentJournals": "Журнал документов — список документов, отфильтрованных по определённым критериям.",
    "IntegrationService": "Системный объект: сервис интеграции для обмена данными с внешними системами.",
}


def _build_db_overview(dbname: str) -> dict:
    """Build a comprehensive overview dict for a database."""
    reg = _loader(dbname)
    overview: dict = {
        "database": dbname,
        "total_tables": reg.summary["total_tables"],
        "total_metadata_objects": reg.summary["objects_with_tables"],
        "entity_types": {},
    }
    # Build per-category listings
    for cat in sorted(_META_TYPE_DESCRIPTIONS):
        objects_in_cat = [o for o in reg.objects.values() if o.category == cat]
        if objects_in_cat:
            description = _META_TYPE_DESCRIPTIONS.get(cat, "")
            obj_list = []
            for obj in objects_in_cat:
                syn_ru = ""
                if obj.metadata_xml and obj.metadata_xml.synonym:
                    syn_ru = obj.metadata_xml.synonym.get("ru", "")
                obj_list.append({
                    "name": obj.tech_name,
                    "main_table": obj.main_table,
                    "synonym_ru": syn_ru,
                    "uuid": obj.uuid,
                })
            overview["entity_types"][cat] = {
                "count": len(objects_in_cat),
                "description": description,
                "objects": sorted(obj_list, key=lambda x: x["name"]),
            }
    # Service table count
    svc_count = sum(1 for t in reg.tables.values() if isinstance(t, ServiceTableInfo))
    overview["service_tables"] = svc_count
    return overview


# ── Create server ───────────────────────────────────────────────────────

server = Server("py1cv8")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_db_overview",
            description=(
                "Показывает полный обзор базы данных: какие типы объектов есть "
                "(справочники, документы, регистры и т.д.), сколько их, их человеческие имена "
                "и соответствующие таблицы. Используй этот метод ПЕРВЫМ, "
                "когда пользователь обращается к системе — чтобы понять, "
                "какие данные доступны и как они называются."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"База данных: {', '.join(AVAILABLE_DBS)}.",
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="run_sql",
            description=(
                "Выполняет read-only SQL SELECT к базе 1С. "

                "КАКИЕ ЗАПРОСЫ ДЕЛАТЬ ЧЕРЕЗ ЭТОТ МЕТОД:\n"
                "- Получить данные из таблицы: список элементов справочника, реквизиты документа, "
                "остатки, обороты.\n"
                "- Поиск по наименованию, дате, сумме.\n"
                "- Выборка с фильтрацией, группировкой, сортировкой.\n"
                "- JOIN нескольких таблиц (например, документ + справочник контрагента).\n"

                "КАК НЕ ИСПОЛЬЗОВАТЬ:\n"
                "- Для получения структуры метаданных (какие объекты есть) — используй get_db_overview.\n"
                "- Для детального описания таблицы (колонки, типы) — используй get_schema.\n"
                "- Для понимания связей между таблицами — используй analyze_object.\n"

                "ПРИМЕРЫ ЗАПРОСОВ ПОЛЬЗОВАТЕЛЯ И СООТВЕТСТВУЮЩИЙ SQL (MessageCenter):\n"
                "- «Найти алгоритм по имени» → SELECT * FROM _reference53 WHERE _description ILIKE '%алгоритм%'\n"
                "- «Показать уведомления за сегодня» → SELECT * FROM _document209 WHERE _date_DateTime >= CURRENT_DATE\n"
                "- «Какие каналы отправки есть?» → SELECT _description, _code FROM _reference132\n"
                "- «Подписки пользователя X» → SELECT * FROM _inforg148 WHERE _description = 'Имя пользователя'\n"
                "- «Параметры отправки для канала Y» → SELECT * FROM _inforg119 WHERE _fld86_RRef = '<GUID канала>'\n"

                "СОГЛАШЕНИЯ:\n"
                "- Все запросы только SELECT или WITH (read-only).\n"
                "- Имена таблиц: _reference{N}, _document{N}, _inforg{N}, _const{N}.\n"
                "- Можно указывать resolve_names=true, чтобы использовать 1С-имена вместо физических.\n"
                "- Поля _description, _name, _number, _date, _amount — типовые.\n"
                "- Ссылочные поля оканчиваются на _RRef, _RTRef, _Owner, _Parent.\n"
                "- Даты в формате ISO (ГГГГ-ММ-ДД).\n"
                "- Ограничение: до 1000 строк (параметр limit).\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"База данных. Доступны: {', '.join(AVAILABLE_DBS)}. "
                        f"MessageCenter — система уведомлений, test — тестовая конфигурация.",
                    },
                    "sql": {
                        "type": "string",
                        "description": (
                            "SQL SELECT запрос (только чтение). "
                            "Пример: SELECT * FROM _reference53 WHERE _description ILIKE '%поиск%' LIMIT 10. "
                            "Используй ILIKE для регистронезависимого поиска по строкам. "
                            "GUID в 1С хранятся как строки вида 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'."
                            "Если resolve_names=true, можно писать имена 1С-объектов вместо _reference53."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100,
                        "description": "Максимум строк в ответе (до 1000). Если пользователь хочет «все», используй лимит 1000.",
                    },
                    "resolve_names": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Автоматически заменять 1С-имена объектов на физические имена таблиц. "
                            "Пример: при resolve_names=true запрос 'SELECT * FROM Алгоритмы' "
                            "станет 'SELECT * FROM _reference53'. "
                            "Работает с tech_name (Reference_53), display_ru (Алгоритмы (ИР)) "
                            "и физическими именами таблиц."
                        ),
                    },
                },
                "required": ["dbname", "sql"],
            },
        ),
        Tool(
            name="get_schema",
            description=(
                "Показывает структуру таблицы (колонки, типы данных, PRIMARY KEY, NULL-ability) "
                "или список ВСЕХ таблиц базы данных с их 1С-объектами и категориями. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Пользователь спрашивает структуру объекта: «какие реквизиты у документа?», "
                "«из каких полей состоит справочник?».\n"
                "- Перед написанием SQL-запроса к незнакомой таблице — сначала получи её схему.\n"
                "- Нужно узнать, какие таблицы вообще существуют в базе.\n"

                "ПАРАМЕТРЫ:\n"
                "- Если не передавать table — вернётся список ВСЕХ таблиц, сгруппированный по категориям.\n"
                "- Если передать table — вернётся детальное описание таблицы: колонки, типы, ключи.\n"

                "ТИПЫ ДАННЫХ В КОЛОНКАХ:\n"
                "- serial/integer — числовой идентификатор (автоинкремент).\n"
                "- character varying / text — строковое поле.\n"
                "- numeric — число (сумма, количество).\n"
                "- timestamp — дата и время.\n"
                "- uuid — GUID-ссылка на другую таблицу (поле _RRef, _RTRef и т.д.).\n"
                "- bytea — бинарные данные (ValueStorage, картинка).\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "table": {
                        "type": "string",
                        "description": (
                            "Имя таблицы (например, _reference53, _document209). "
                            "Если не указано — вернётся список всех таблиц с категориями. "
                            "Имена таблиц можно получить через get_db_overview или вызовом get_schema без параметра table."
                        ),
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="search_metadata",
            description=(
                "Поиск и просмотр метаданных 1С-объектов (их названия, синонимы, UUID, "
                "привязанные таблицы). "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Пользователь спрашивает «что такое X?» — объект X найден по uuid/category/search.\n"
                "- Нужно найти UUID объекта для дальнейшего анализа.\n"
                "- Нужно узнать, к какой таблице привязан объект.\n"
                "- Пользователь спрашивает на русском: «покажи все справочники», "
                "«какие документы бывают?», «найди объект по имени».\n"

                "ПАРАМЕТРЫ ФИЛЬТРАЦИИ (можно комбинировать):\n"
                "- uuid — GUID объекта (полный или частичное совпадение).\n"
                "- category — категория: Catalogs (справочники), Documents (документы), "
                "InformationRegisters (регистры сведений), Constants (константы), "
                "Enums (перечисления) и т.д.\n"
                "- search — поиск по техническому имени или displayName (русскому синониму).\n"

                "ЕСЛИ НИ ОДИН ФИЛЬТР НЕ ЗАДАН — возвращается сводка по всей БД "
                "(сколько объектов, по категориям, общее число таблиц).\n"

                "ПРИМЕРЫ:\n"
                "- category=Catalogs → все справочники.\n"
                "- search=контрагент → объекты, в имени которых есть «контрагент».\n"
                "- uuid=cd070a4a... → конкретный объект.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "uuid": {
                        "type": "string",
                        "description": (
                            "UUID/GUID объекта метаданных в формате "
                            "'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'. "
                            "Можно указать частично для поиска. "
                            "Где взять: из get_db_overview, search_metadata, get_schema."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Фильтр по категории. Доступные категории: "
                            "Catalogs (справочники), Documents (документы), "
                            "InformationRegisters (регистры сведений), "
                            "AccumulationRegisters (регистры накопления), "
                            "AccountingRegisters (регистры бухгалтерии), "
                            "Constants (константы), Enums (перечисления), "
                            "ChartsOfCharacteristicTypes (планы видов характеристик). "
                            "Фильтр регистронезависимый, частичное совпадение."
                        ),
                    },
                    "search": {
                        "type": "string",
                        "description": (
                            "Поиск по техническому имени или русскому синониму объекта. "
                            "Пример: search=уведомление найдёт все объекты, "
                            "связанные с уведомлениями. Регистронезависимый поиск."
                        ),
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="analyze_object",
            description=(
                "Детальный бизнес-анализ объекта 1С или таблицы — объединяет метаданные, "
                "структуру таблиц, XML-описание и связи между таблицами. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Пользователь спрашивает подробности об объекте: "
                "«расскажи про этот документ», «какие реквизиты у справочника», "
                "«как устроен этот регистр».\n"
                "- Нужно понять связи объекта с другими таблицами перед написанием сложного SQL.\n"
                "- Нужно получить полную бизнес-логику объекта: "
                "иерархичность, подчинённость, типы номеров, периодичность.\n"
                "- Пользователь спрашивает «почему так работает» или «как это устроено». "

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- UUID, имя, русский синоним, категорию.\n"
                "- Основную таблицу и подтаблицы (табличные части, движения).\n"
                "- Список колонок с типами и признаками NULL/PK.\n"
                "- Если есть XML-метаданные: реквизиты (атрибуты), табличные части, "
                "синонимы, команды, формы, бизнес-логику (иерархия, posting, number_type и т.д.).\n"
                "- Связи (RRef/RTRef/Owner/Parent/Recorder) с другими таблицами.\n"

                "ЧТО ИСКАТЬ В ПАРАМЕТРЕ name:\n"
                "- Имя таблицы: _reference53, _document209, _inforg119.\n"
                "- Техническое имя: ирАлгоритмы, Уведомления, Константа1.\n"
                "- Русский синоним: Алгоритмы, Уведомления.\n"
                "- UUID: полный или частичный.\n"

                "ПРИМЕРЫ для MessageCenter:\n"
                "- analyze_object('_document209') — детальный анализ документа Уведомления\n"
                "- analyze_object('_reference53') — анализ справочника Алгоритмы\n"
                "- analyze_object('_inforg148') — анализ регистра Подписки на уведомления\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Имя объекта для анализа. Может быть: "
                            "именем таблицы (_reference53), техническим именем (ирАлгоритмы), "
                            "русским синонимом (Алгоритмы), UUID. "
                            "Поиск регистронезависимый, частичное совпадение."
                        ),
                    },
                },
                "required": ["dbname", "name"],
            },
        ),
        Tool(
            name="get_bsl_code",
            description=(
                "Извлекает исходный код BSL (1С:Предприятие) модуля напрямую из "
                "ConfigStorage базы данных — без необходимости в файловой выгрузке (.export_from_1c). "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно прочитать код общего модуля, формы или другого объекта метаданных.\n"
                "- Пользователь спрашивает «как работает этот модуль?», «покажи код».\n"
                "- Нужно найти, какие запросы выполняет модуль.\n"
                "- Нужно понять бизнес-логику, реализованную в 1С.\n"

                "ЧТО ИСКАТЬ В ПАРАМЕТРЕ module_name:\n"
                "- Техническое имя: ирУведомленияСервер, ирУведомленияКлиент\n"
                "- Русский синоним: (ищется по всем объектам метаданных)\n"
                "- UUID: полный или частичный\n"

                "ПРИМЕРЫ (MessageCenter):\n"
                "- get_bsl_code('ирУведомленияСервер') — модуль серверных уведомлений\n"
                "- get_bsl_code('РегламентДоставки') — модуль регламентного задания доставки\n"

                "ПРИМЕЧАНИЕ:\n"
                "- Если модуль найден — возвращается его полный BSL-код.\n"
                "- Если не найден — возвращается пустой результат.\n"
                "- Может вернуть несколько вариантов, если имя не уникально.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "module_name": {
                        "type": "string",
                        "description": (
                            "Имя модуля для поиска. "
                            "Может быть техническим именем (ирУведомленияСервер), "
                            "русским синонимом или UUID. "
                            "Поиск регистронезависимый, частичное совпадение."
                        ),
                    },
                },
                "required": ["dbname", "module_name"],
            },
        ),
        Tool(
            name="get_relationship_map",
            description=(
                "Показывает полный граф связей таблицы — как исходящие ссылки "
                "(RRef/RTRef/Owner/Parent/Recorder), так и входящие (какие таблицы "
                "ссылаются на эту). "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно понять, с какими таблицами связан объект.\n"
                "- Перед написанием сложного JOIN.\n"
                "- Нужно найти, какие объекты ссылаются на данный.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- outgoing: колонки текущей таблицы, ссылающиеся на другие.\n"
                "- incoming: таблицы, у которых есть ссылки на текущую.\n"
                "- У каждой связи: имя колонки, тип ссылки, целевая таблица.\n"

                "ПРИМЕРЫ (MessageCenter):\n"
                "- get_relationship_map('_document209') — какие объекты ссылаются на Уведомления\n"
                "- get_relationship_map('_reference132') — на какие таблицы ссылаются Каналы\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Имя таблицы или объекта для построения графа связей. "
                            "Может быть: именем таблицы (_reference53), "
                            "техническим именем (ирАлгоритмы), "
                            "русским синонимом (Алгоритмы) или UUID."
                        ),
                    },
                },
                "required": ["dbname", "name"],
            },
        ),
        Tool(
            name="explain_object",
            description=(
                "Комбинированный анализ объекта 1С: метаданные + связи + примеры данных. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно быстро понять, что за объект и как он устроен.\n"
                "- Пользователь спрашивает «расскажи про этот объект».\n"
                "- Нужно одним вызовом получить полную картину: структуру, связи, данные.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Название, синоним, категорию, основную таблицу.\n"
                "- Колонки и подтаблицы.\n"
                "- Связи с другими таблицами (входящие/исходящие).\n"
                "- Примеры данных (до 3 записей).\n"
                "- Ключевую бизнес-логику (проведение, иерархия, типы номеров).\n"

                "ПРИМЕРЫ:\n"
                "- explain_object('_document209') — полный разбор документа Уведомления\n"
                "- explain_object('_reference53') — разбор справочника Алгоритмы\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Имя объекта для анализа. "
                            "Может быть: именем таблицы (_reference53), "
                            "техническим именем (ирАлгоритмы), "
                            "русским синонимом (Алгоритмы) или UUID."
                        ),
                    },
                },
                "required": ["dbname", "name"],
            },
        ),
        Tool(
            name="get_notification_analytics",
            description=(
                "Аналитика по уведомлениям MessageCenter: статистика отправки, "
                "доставки, распределение по каналам. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно узнать сколько уведомлений отправлено.\n"
                "- Нужно увидеть распределение по каналам и статусам.\n"
                "- Нужна статистика за период.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Общее количество уведомлений.\n"
                "- Статусы проведения.\n"
                "- Топ каналов отправки.\n"
                "- Распределение по дням.\n"
                "- Количество подписок и каналов.\n"

                "ПАРАМЕТРЫ:\n"
                "- start_date / end_date (опционально) — фильтр по дате в формате 'ГГГГ-ММ-ДД'.\n"

                "ПРИМЕРЫ:\n"
                "- get_notification_analytics() — полная статистика\n"
                "- get_notification_analytics(start_date='2025-01-01') — за период\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Начало периода в формате 'ГГГГ-ММ-ДД' (опционально).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Конец периода в формате 'ГГГГ-ММ-ДД' (опционально).",
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="search_bsl_code",
            description=(
                "Поиск фрагмента текста во всех BSL-модулях конфигурации. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно найти, где используется функция или переменная.\n"
                "- Нужно найти все модули, работающие с определённым объектом.\n"
                "- Пользователь спрашивает «найди в коде, где вызывается X».\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Список модулей, где найден текст.\n"
                "- Контекст с совпадением (строка и окружение).\n"
                "- Количество совпадений в каждом модуле.\n"

                "ПАРАМЕТРЫ:\n"
                "- query — текст для поиска (минимум 2 символа).\n"
                "- max_results — максимум результатов (до 100, по умолч. 20).\n"

                "ПРИМЕРЫ:\n"
                "- search_bsl_code(query='Получатели') — поиск по получателям\n"
                "- search_bsl_code(query='ОтправитьУведомление') — поиск функции\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Текст для поиска в BSL-коде (минимум 2 символа).",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 20,
                        "description": "Максимум результатов (до 100).",
                    },
                },
                "required": ["dbname", "query"],
            },
        ),
        Tool(
            name="search_1c_queries",
            description=(
                "Поиск 1С-запросов в BSL-модулях с переводом в SQL. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно найти, какой модуль формирует определённый SQL-запрос.\n"
                "- Нужно понять, как работает бизнес-логика на уровне 1С-запросов.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Модули, где найден текст.\n"
                "- Извлечённые 1С-запросы с переводом в SQL.\n"
                "- Параметры запросов.\n"

                "ПАРАМЕТРЫ:\n"
                "- query — текст для поиска в коде.\n"
                "- max_results — максимум результатов (до 50, по умолч. 10).\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Текст для поиска в BSL-коде (минимум 2 символа).",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Максимум результатов (до 50).",
                    },
                },
                "required": ["dbname", "query"],
            },
        ),
        Tool(
            name="get_config_snapshot",
            description=(
                "Показывает полный снимок конфигурации 1С из configsave.versions. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно увидеть, какие объекты входят в сохранённую (ещё не применённую) "
                "конфигурацию.\n"
                "- Нужно узнать версию каждого объекта конфигурации.\n"
                "- Нужно получить сводку по категориям объектов.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Общее количество объектов и под-объектов.\n"
                "- Распределение по категориям (справочники, документы, регистры и т.д.).\n"
                "- Список всех объектов с UUID, именем, configVersion.\n"
                "- Временная метка сохранения.\n"

                "ПАРАМЕТРЫ:\n"
                "- source (опционально) — откуда читать: 'configsave' (по умолч.) или 'config'.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Откуда читать: 'configsave' (по умолчанию, ожидающие изменения) или 'config' (текущее состояние).",
                        "default": "configsave",
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="find_changed_objects",
            description=(
                "Сравнивает configsave (ожидающие изменения) и config (текущее состояние), "
                "показывая что изменилось. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Разработчик внёс изменения в конфигурацию, но ещё не применил их.\n"
                "- Нужно оценить объём и характер будущих изменений.\n"
                "- Нужно понять, какие объекты были изменены, добавлены или удалены.\n"
                "- Нужно провести ревью изменений перед применением.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Сводку: сколько объектов изменилось, добавлено, удалено.\n"
                "- Список изменённых объектов: UUID, имя, старая и новая версии.\n"
                "- Список UUID новых и удалённых объектов.\n"

                "ПРИМЕРЫ:\n"
                "- find_changed_objects() — все ожидающие изменения.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="get_object_config_history",
            description=(
                "Показывает историю configVersion для конкретного объекта. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно отследить, менялся ли объект в новой конфигурации.\n"
                "- Нужно сравнить версию объекта в live и в pending.\n"
                "- Нужно найти различия в под-объектах (модули, формы).\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Все записи о версиях объекта из config (live) и configsave (pending).\n"
                "- Разбивка по под-объектам (сам объект, модуль, форма).\n"
                "- Список различий между live и pending.\n"

                "ПАРАМЕТРЫ:\n"
                "- uuid или name — идентификатор объекта.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "uuid": {
                        "type": "string",
                        "description": "UUID объекта (полный или фрагмент).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Имя объекта (tech_name или display_ru). Альтернатива uuid.",
                    },
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="table_stats",
            description=(
                "Показывает статистику таблицы: количество строк, NULL-ability, "
                "distinct-значения, диапазоны дат, топ-значения. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно быстро понять объём данных в таблице.\n"
                "- Нужно оценить качество данных (сколько NULL, сколько уникальных).\n"
                "- Нужно увидеть распределение значений в строковых полях.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Общее количество строк.\n"
                "- Для каждой колонки: тип, % не-NULL, distinct-значений.\n"
                "- Для дат: минимальная/максимальная.\n"
                "- Для чисел: минимум, максимум, среднее.\n"
                "- Для строк: топ-10 значений.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "table": {
                        "type": "string",
                        "description": "Имя таблицы (например, _reference53, _document209).",
                    },
                },
                "required": ["dbname", "table"],
            },
        ),
        Tool(
            name="find_by_value",
            description=(
                "Глобальный поиск значения по всем строковым колонкам таблиц. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно найти, где используется GUID, номер документа, имя контрагента.\n"
                "- Нужно понять, в каких таблицах встречается определённое значение.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Таблицы и колонки, где найдено значение.\n"
                "- Количество совпадений.\n"
                "- Примеры _idrref найденных записей.\n"

                "ПАРАМЕТРЫ:\n"
                "- value — значение для поиска (LIKE-поиск, регистронезависимый).\n"
                "- table (опционально) — ограничить поиск одной таблицей.\n"
                "- max_results (опционально, по умолч. 20) — максимум результатов.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Значение для поиска (регистронезависимый ILIKE %value%).",
                    },
                    "table": {
                        "type": "string",
                        "description": "Ограничить поиск одной таблицей (опционально).",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 20,
                        "description": "Максимум результатов (до 100).",
                    },
                },
                "required": ["dbname", "value"],
            },
        ),
        Tool(
            name="config_diff_detail",
            description=(
                "Детальный diff объекта метаданных между configsave и config. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- После find_changed_objects нужно увидеть, ЧТО конкретно изменилось в объекте.\n"
                "- Нужно провести ревью изменений конфигурации на уровне содержимого.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Содержимое объекта из configsave (pending) и config (live).\n"
                "- Унифицированный diff (строки с + добавлены, с - удалены).\n"
                "- Метаданные объекта (имя, UUID, категория).\n"

                "ПАРАМЕТРЫ:\n"
                "- uuid — UUID объекта метаданных или entry_uuid из versions blob.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "uuid": {
                        "type": "string",
                        "description": "UUID объекта метаданных или entry_uuid из versions blob.",
                    },
                },
                "required": ["dbname", "uuid"],
            },
        ),
        Tool(
            name="orphaned_records",
            description=(
                "Находит битые ссылки — записи, чьи RRef/RTRef поля указывают "
                "на несуществующие ID. "

                "ИСПОЛЬЗУЙ ЭТОТ МЕТОД, КОГДА:\n"
                "- Нужно проверить целостность данных.\n"
                "- После обмена/переноса данных — найти потерянные ссылки.\n"
                "- Нужно почистить мусор в справочниках и регистрах.\n"

                "РЕЗУЛЬТАТ СОДЕРЖИТ:\n"
                "- Для каждой связи: сколько битых ссылок, примеры UUID.\n"
                "- Фильтрация по таблице (опционально).\n"

                "ПАРАМЕТРЫ:\n"
                "- table (опционально) — проверить только одну таблицу.\n"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {
                        "type": "string",
                        "enum": AVAILABLE_DBS,
                        "description": f"Доступны: {', '.join(AVAILABLE_DBS)}.",
                    },
                    "table": {
                        "type": "string",
                        "description": "Имя таблицы для проверки (опционально, без фильтра — все таблицы).",
                    },
                },
                "required": ["dbname"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    dbname = arguments.get("dbname", "")

    if name == "get_db_overview":
        return _render_overview(dbname)
    elif name == "run_sql":
        return await _run_sql(dbname, arguments)
    elif name == "get_schema":
        return await _get_schema(dbname, arguments)
    elif name == "search_metadata":
        return await _search_metadata(dbname, arguments)
    elif name == "analyze_object":
        return _analyze_object(dbname, arguments)
    elif name == "get_bsl_code":
        return _get_bsl_code(dbname, arguments)
    elif name == "get_relationship_map":
        return _get_relationship_map(dbname, arguments)
    elif name == "explain_object":
        return _explain_object(dbname, arguments)
    elif name == "get_notification_analytics":
        return _get_notification_analytics(dbname, arguments)
    elif name == "search_bsl_code":
        return _search_bsl_code(dbname, arguments)
    elif name == "search_1c_queries":
        return _search_1c_queries(dbname, arguments)
    elif name == "get_config_snapshot":
        return _get_config_snapshot(dbname, arguments)
    elif name == "find_changed_objects":
        return _find_changed_objects(dbname, arguments)
    elif name == "get_object_config_history":
        return _get_object_config_history(dbname, arguments)
    elif name == "table_stats":
        return _table_stats(dbname, arguments)
    elif name == "find_by_value":
        return _find_by_value(dbname, arguments)
    elif name == "config_diff_detail":
        return _config_diff_detail(dbname, arguments)
    elif name == "orphaned_records":
        return _orphaned_records(dbname, arguments)
    raise ValueError(f"Unknown tool: {name}")


# ── Tool implementations ────────────────────────────────────────────────


def _render_overview(dbname: str) -> list[TextContent]:
    overview = _build_db_overview(dbname)
    return [TextContent(
        type="text",
        text=json.dumps(overview, ensure_ascii=False, indent=2),
    )]


async def _run_sql(dbname: str, args: dict) -> list[TextContent]:
    """Execute user-provided SQL via SQLAlchemy text().

    NOTE: text() is used intentionally for user-provided SQL.
    All internal queries use ORM constructs.
    """
    from py1cv8.db import get_session

    sql = args.get("sql", "").strip()
    limit = min(args.get("limit", 100), 1000)
    resolve = args.get("resolve_names", False)

    # Apply name resolution if requested
    if resolve:
        reg = _loader(dbname)
        sql = _resolve_table_names(sql, reg)

    stripped = sql.strip().lstrip("(")
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        return [TextContent(
            type="text", text="Only SELECT / WITH queries allowed (read-only mode).",
        )]

    safe_sql = f"SELECT * FROM ({sql}) AS _q LIMIT {limit}"

    session = get_session(dbname)
    try:
        result = session.execute(text(safe_sql))
        cols = list(result.keys())
        rows = [{c: _serialize(r[c]) for c in cols} for r in result.mappings().all()]
        data = {
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
        }
        text_out = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        return [TextContent(type="text", text=text_out)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


async def _get_schema(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    table_name = args.get("table", "")

    if table_name:
        info = reg.get_object_by_table(table_name)
        if not info:
            return [TextContent(type="text", text=f"Table '{table_name}' not found.")]
        base = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
        base["columns"] = _columns_to_dicts(info)
        base["column_count"] = len(info.columns)
        return [TextContent(type="text", text=json.dumps(base, ensure_ascii=False, indent=2))]
    else:
        cats: dict[str, list[str]] = {}
        for tname, info in sorted(reg.tables.items()):
            cat = info.category if isinstance(info, ObjectInfo) else "System"
            cats.setdefault(cat, []).append(
                f"{tname} ({info.tech_name if isinstance(info, ObjectInfo) else info.db_name})"
            )
        data = {"database": dbname, "total_tables": len(reg.tables), "by_category": cats}
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


async def _search_metadata(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    uuid_filter = (args.get("uuid") or "").lower()
    category_filter = (args.get("category") or "").lower()
    search_q = (args.get("search") or "").lower()

    if not uuid_filter and not category_filter and not search_q:
        text_out = json.dumps(reg.summary, ensure_ascii=False, indent=2)
        return [TextContent(type="text", text=text_out)]

    matched: list[dict] = []
    for obj in reg.objects.values():
        if uuid_filter and uuid_filter not in obj.uuid:
            continue
        if category_filter and category_filter not in obj.category.lower():
            continue
        if search_q and (
            search_q not in obj.tech_name.lower()
            and search_q not in obj.display_ru.lower()
        ):
            continue
        matched.append(_obj_to_dict(obj))

    return [TextContent(
        type="text",
        text=json.dumps({"count": len(matched), "objects": matched}, ensure_ascii=False, indent=2),
    )]


def _xml_full(obj: ObjectInfo) -> dict | None:
    """Full XML metadata detail for analyze."""
    xm = obj.metadata_xml
    if xm is None:
        return None
    result = {}
    for f in dataclasses.fields(xm):
        val = getattr(xm, f.name)
        if val is not None and val != "" and val != []:
            if f.name == "attributes":
                result[f.name] = [
                    {
                        "name": a.name,
                        "synonym": a.synonym,
                        "type": a.type_info.display,
                        "type_raw": a.type_info.types,
                        "qualifiers": {
                            k: v for k, v in dataclasses.asdict(a.type_info.qualifiers).items()
                            if v is not None
                        },
                        "comment": a.comment,
                        "indexing": a.indexing,
                        "full_text_search": a.full_text_search,
                        "password_mode": a.password_mode,
                        "multiline": a.multiline,
                    }
                    for a in val
                ]
            elif f.name == "tabular_sections":
                result[f.name] = [
                    {
                        "name": ts.name,
                        "synonym": ts.synonym,
                        "attributes": [
                            {
                                "name": a.name,
                                "type": a.type_info.display,
                            }
                            for a in ts.attributes
                        ],
                        "generated_types": [
                            {"name": g.name, "category": g.category}
                            for g in ts.generated_types
                        ],
                    }
                    for ts in val
                ]
            elif f.name == "enum_values":
                result[f.name] = [
                    {"name": v.name, "synonym": v.synonym} for v in val
                ]
            elif f.name == "commands":
                result[f.name] = [
                    {
                        "name": c.name,
                        "synonym": c.synonym,
                        "comment": c.comment,
                        "modifies_data": c.modifies_data,
                        "representation": c.representation,
                    }
                    for c in val
                ]
            elif f.name == "generated_types":
                result[f.name] = [
                    {"name": g.name, "category": g.category}
                    for g in val
                ]
            elif f.name in ("forms", "templates", "synonym", "comment"):
                result[f.name] = val
            elif f.name in ("object_presentation", "list_presentation", "explanation"):
                if val:
                    result[f.name] = val
            elif f.name in (
                "hierarchical", "hierarchy_type", "subordination_use",
                "code_length", "description_length", "code_type",
                "check_unique", "autonumbering", "posting",
                "number_type", "number_length", "number_periodicity",
                "periodicity", "write_mode", "edit_type", "choice_mode",
                "data_lock_control_mode", "full_text_search", "data_history",
                "create_on_input", "input_by_string", "default_presentation",
                "quick_choice", "numerator",
            ):
                result[f.name] = val
    return result if result else None


def _analyze_object(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    name = (args.get("name") or "").lower()

    if not name:
        return [TextContent(type="text", text="Provide a name to analyze.")]

    candidates: list[dict] = []
    for tname, info in reg.tables.items():
        if name not in tname.lower():
            if isinstance(info, ObjectInfo):
                if (
                    name not in info.tech_name.lower()
                    and name not in info.display_ru.lower()
                    and name not in info.uuid.lower()
                ):
                    continue
            else:
                continue

        base = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
        base["columns"] = _columns_to_dicts(info)
        if isinstance(info, ObjectInfo) and info.main_table in reg.relationships:
            base["references"] = reg.relationships[info.main_table]
        if isinstance(info, ObjectInfo) and info.metadata_xml is not None:
            xf = _xml_full(info)
            if xf:
                base["metadata_detail"] = xf
        if isinstance(info, ObjectInfo):
            bq = _bsl_queries_for(info, reg, dbname)
            if bq:
                base["bsl_queries"] = bq
        candidates.append(base)

    if not candidates:
        return [TextContent(type="text", text=f"No results for '{args.get('name')}'.")]

    return [TextContent(
        type="text",
        text=json.dumps(
            {"count": len(candidates), "objects": candidates},
            ensure_ascii=False, indent=2,
        ),
    )]


# ── Resources ───────────────────────────────────────────────────────────


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    resources: list[Resource] = []
    for dbname in AVAILABLE_DBS:
        reg = _loader(dbname)
        # Overview resource
        resources.append(Resource(
            uri=AnyUrl(f"1c://{dbname}/overview"),
            name=f"{dbname}: overview of entity types and terminology",
            description=(
                f"Обзор базы {dbname}: список всех типов объектов (справочники, документы, "
                f"регистры сведений, константы, перечисления) с их количеством, "
                f"русскими названиями и таблицами. Используй как отправную точку."
            ),
            mimeType="application/json",
        ))
        # Per-table resources
        for tname, info in reg.tables.items():
            label = info.tech_name if isinstance(info, ObjectInfo) else info.db_name
            desc = info.display_ru if isinstance(info, ObjectInfo) else info.description
            type_hint = ""
            if isinstance(info, ObjectInfo):
                type_hint = {
                    "Catalogs": "Справочник",
                    "Documents": "Документ",
                    "Constants": "Константа",
                    "Enums": "Перечисление",
                    "InformationRegisters": "Регистр сведений",
                    "AccumulationRegisters": "Регистр накопления",
                    "AccountingRegisters": "Регистр бухгалтерии",
                    "ChartsOfCharacteristicTypes": "План видов характеристик",
                }.get(info.category, info.category)
            resources.append(Resource(
                uri=AnyUrl(f"1c://{dbname}/tables/{tname}"),
                name=f"{tname} ({label}) — {type_hint}" if type_hint else f"{tname} ({label})",
                description=desc or f"{type_hint}: {label}" if type_hint else f"Table {tname}",
                mimeType="application/json",
            ))
    return resources


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    m = _re.match(r"1c://([^/]+)/(overview|tables)/(.*)", uri)
    if not m:
        raise ValueError(f"Unknown resource: {uri}")
    dbname, kind, rest = m.group(1), m.group(2), m.group(3)

    if kind == "overview":
        overview = _build_db_overview(dbname)
        return json.dumps(overview, ensure_ascii=False, indent=2)

    # kind == "tables"
    tname = rest
    reg = _loader(dbname)
    info = reg.get_object_by_table(tname)
    if not info:
        raise ValueError(f"Table {tname} not found.")

    result = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
    result["columns"] = _columns_to_dicts(info)
    if isinstance(info, ObjectInfo) and info.main_table in reg.relationships:
        result["references"] = reg.relationships[info.main_table]
    return json.dumps(result, ensure_ascii=False, indent=2)


def _get_bsl_code(dbname: str, args: dict) -> list[TextContent]:
    """Извлечение BSL-кода модуля из ConfigStorage БД."""
    module_name = args.get("module_name", "").strip()
    if not module_name:
        return [TextContent(type="text", text="Provide a module_name to search for.")]

    results = _get_bsl_code_from_db(dbname, module_name)

    if not results:
        return [TextContent(
            type="text",
            text=f"No BSL code found for module '{module_name}'.\n\n"
                 "Search metadata_map for available modules. Try searching by:\n"
                 "- tech_name (e.g. 'ирУведомленияСервер')\n"
                 "- UUID fragment\n"
                 "- display name",
        )]

    # Format code blocks as text with language hints
    if len(results) == 1 and results[0]["block_count"] > 0:
        r = results[0]
        text_parts = [f"// Module: {r['tech_name']}\n// UUID: {r['uuid']}\n"]
        for i, block in enumerate(r["code_blocks"]):
            if r["block_count"] > 1:
                text_parts.append(f"\n// --- Block {i + 1} ---\n")
            text_parts.append(block)
        return [TextContent(type="text", text="\n".join(text_parts))]
    else:
        return [TextContent(
            type="text",
            text=json.dumps(results, ensure_ascii=False, indent=2),
        )]


def _get_relationship_map(dbname: str, args: dict) -> list[TextContent]:
    """Полный граф связей таблицы: входящие + исходящие."""
    reg = _loader(dbname)
    name = (args.get("name") or "").lower()

    if not name:
        return [TextContent(type="text", text="Provide a name to analyze.")]

    # 1. Find the table
    table_name = None
    for tname, info in reg.tables.items():
        if name in tname.lower():
            table_name = tname
            break
        if isinstance(info, ObjectInfo) and (
            name in info.tech_name.lower()
            or name in info.display_ru.lower()
            or name in info.uuid.lower()
        ):
            table_name = tname
            break

    if not table_name:
        return [TextContent(type="text", text=f"Table/object '{args.get('name')}' not found.")]

    # 2. Outgoing references
    outgoing = reg.relationships.get(table_name, [])

    # 3. Incoming references (reverse)
    incoming: list[dict] = []
    for src_table, refs in reg.relationships.items():
        for ref in refs:
            target = ref.get("target_table", "")
            if target == table_name:
                src_name = ""
                src_info = reg.tables.get(src_table)
                if isinstance(src_info, ObjectInfo):
                    src_name = src_info.tech_name
                incoming.append({
                    "source_table": src_table,
                    "source_name": src_name,
                    "column": ref["column"],
                    "ref_type": ref["ref_type"],
                })

    # 4. Info about this table
    info = reg.tables.get(table_name)
    table_info = {}
    if isinstance(info, ObjectInfo):
        table_info = {
            "tech_name": info.tech_name,
            "display_ru": info.display_ru,
            "uuid": info.uuid,
            "category": info.category,
        }

    result = {
        "table": table_name,
        "table_info": table_info,
        "outgoing_refs": outgoing,
        "outgoing_count": len(outgoing),
        "incoming_refs": incoming,
        "incoming_count": len(incoming),
    }

    return [TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2),
    )]


# ── New tool helpers ──────────────────────────────────────────────────────


def _sample_data_for_table(dbname: str, table_name: str, limit: int = 3) -> list[dict] | None:
    """Fetch sample rows from a table for explain_object."""
    from py1cv8.db import get_session

    try:
        session = get_session(dbname)
        try:
            result = session.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
            cols = list(result.keys())
            rows = [{c: _serialize(r[c]) for c in cols} for r in result.mappings().all()]
            return rows
        except Exception:
            return None
        finally:
            session.close()
    except Exception:
        return None


def _explain_object(dbname: str, args: dict) -> list[TextContent]:
    """Combined analysis: metadata + relationships + sample data."""
    name = args.get("name", "").strip()
    if not name:
        return [TextContent(type="text", text="Provide a name to analyze.")]

    # 1. Full object analysis
    analysis_result = _analyze_object(dbname, {"name": name})
    analysis = json.loads(analysis_result[0].text)

    if analysis.get("count", 0) == 0:
        return analysis_result

    obj = analysis["objects"][0]

    # 2. Relationships
    rels_result = _get_relationship_map(dbname, {"name": obj.get("main_table", name)})
    rels = json.loads(rels_result[0].text)

    # 3. Sample data
    main_table = obj.get("main_table", "")
    samples = _sample_data_for_table(dbname, main_table) if main_table else None

    # 4. Build explanation
    explanation_parts = []

    # Header
    tech_name = obj.get("tech_name", "?")
    display_ru = obj.get("display_ru", "")
    category = obj.get("category", "")
    header = f"{tech_name}"
    if display_ru:
        header += f" ({display_ru})"
    header += f" — {category}"
    explanation_parts.append(header)

    # Structure
    cols = obj.get("columns", [])
    sub_tables = obj.get("sub_tables", {})
    col_names = [c["name"] for c in cols]
    explanation_parts.append(f"\nТаблица: {main_table} ({len(cols)} колонок, {len(sub_tables)} подтаблиц)")
    explanation_parts.append(f"Колонки: {', '.join(col_names[:10])}{'...' if len(col_names) > 10 else ''}")

    # Relationships
    outgoing = rels.get("outgoing_refs", [])
    incoming = rels.get("incoming_refs", [])
    if outgoing:
        out_targets = [r.get("target_table", "?") for r in outgoing[:5]]
        explanation_parts.append(f"→ Ссылается на: {', '.join(out_targets)}{'...' if len(outgoing) > 5 else ''}")
    if incoming:
        in_sources = [r.get("source_table", "?") for r in incoming[:5]]
        explanation_parts.append(f"← Ссылаются на неё: {', '.join(in_sources)}{'...' if len(incoming) > 5 else ''}")

    # Sample data
    if samples:
        explanation_parts.append(f"\nПримеры данных ({len(samples)} записей):")
        for i, row in enumerate(samples):
            vals = [f"{k}={v}" for k, v in list(row.items())[:6] if v is not None]
            explanation_parts.append(f"  [{i + 1}] {', '.join(vals[:4])}")

    # Metadata detail
    meta = obj.get("metadata", {})
    biz = meta.get("business_logic", {})
    if biz:
        biz_str = ", ".join(f"{k}={v}" for k, v in biz.items())
        explanation_parts.append(f"\nБизнес-логика: {biz_str}")

    text_out = "\n".join(explanation_parts)

    return [TextContent(type="text", text=text_out)]


def _get_notification_analytics(dbname: str, args: dict) -> list[TextContent]:
    """Аналитика по уведомлениям: статистика отправки, доставки, ошибок."""
    start_date = args.get("start_date", "")
    end_date = args.get("end_date", "")

    from py1cv8.db import get_session

    parts = []
    date_filter = ""
    if start_date and end_date:
        date_filter = f"AND d._date_time >= '{start_date}'::timestamp AND d._date_time < ('{end_date}'::timestamp + INTERVAL '1 day')"
    elif start_date:
        date_filter = f"AND d._date_time >= '{start_date}'::timestamp"
    elif end_date:
        date_filter = f"AND d._date_time < ('{end_date}'::timestamp + INTERVAL '1 day')"

    session = get_session(dbname)
    try:
        # 1. Total count
        result = session.execute(text(
            "SELECT COUNT(*) AS total FROM _document209 d WHERE 1=1 " + date_filter
        ))
        total = result.scalar() or 0
        parts.append(f"Всего уведомлений: {total}")

        # 2. Posted vs unposted
        result = session.execute(text(
            "SELECT _posted, COUNT(*) AS cnt FROM _document209 d WHERE 1=1 "
            + date_filter + " GROUP BY _posted ORDER BY _posted"
        ))
        parts.append("По статусу проведения:")
        for row in result.all():
            status = "Проведено" if row[0] else "Не проведено"
            parts.append(f"  {status}: {row[1]}")

        # 3. By channel
        result = session.execute(text(
            "SELECT ch._code AS channel, COUNT(*) AS cnt "
            "FROM _document209 d "
            "LEFT JOIN _reference132 ch ON d._fld246rref = ch._idrref "
            "WHERE 1=1 " + date_filter
            + " GROUP BY ch._code ORDER BY cnt DESC LIMIT 10"
        ))
        any_channel = False
        for row in result.all():
            if not any_channel:
                parts.append("По каналам отправки:")
                any_channel = True
            parts.append(f"  {row[0] or '(без канала)'}: {row[1]}")
        if not any_channel:
            parts.append("По каналам отправки: нет данных")

        # 4. By date
        result = session.execute(text(
            "SELECT _date_time::date AS dt, COUNT(*) AS cnt "
            "FROM _document209 d "
            "WHERE 1=1 " + date_filter
            + " GROUP BY dt ORDER BY dt DESC LIMIT 14"
        ))
        parts.append("По дням (последние 14):")
        for row in result.all():
            parts.append(f"  {row[0]}: {row[1]}")

        # 5. Subscriptions count
        result = session.execute(text("SELECT COUNT(*) AS cnt FROM _inforg148"))
        subs = result.scalar() or 0
        active_result = session.execute(text("SELECT COUNT(*) AS cnt FROM _inforg148 WHERE _fld154 = true"))
        active_subs = active_result.scalar() or 0
        parts.append(f"\nПодписок всего: {subs}, активных: {active_subs}")

        # 6. Channel count
        result = session.execute(text("SELECT COUNT(*) AS cnt FROM _reference132"))
        channels = result.scalar() or 0
        parts.append(f"Каналов отправки: {channels}")

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()

    return [TextContent(type="text", text="\n".join(parts))]


# ── Search BSL in ConfigStorage ─────────────────────────────────────────


def _search_bsl_in_config(
    dbname: str,
    query: str,
    max_results: int = 20,
) -> list[dict]:
    """Search BSL code in all ConfigStorage .0 blobs for a text pattern."""
    from sqlalchemy import select

    from py1cv8.db import get_session
    from py1cv8.models import Config

    if not query or len(query) < 2:
        return []

    reg = _loader(dbname)
    meta_map = reg.metadata_map

    # Build uuid → tech_name mapping
    uuid_to_tech: dict[str, str] = {}
    for uuid_val, info in meta_map.items():
        tn = info.get("tech_name", "")
        if tn:
            uuid_to_tech[uuid_val] = tn
        else:
            uuid_to_tech[uuid_val] = uuid_val

    session = get_session(dbname)
    try:
        # Query all .0 blobs
        rows = session.execute(
            select(Config)
            .where(Config.filename.like("%.0"))
            .order_by(Config.filename, Config.partno)
        ).scalars().all()

        # Group by filename, assemble multi-part blobs
        blobs: dict[str, bytearray] = {}
        for row in rows:
            name = row.filename
            if name not in blobs:
                blobs[name] = bytearray()
            if row.binarydata:
                blobs[name].extend(row.binarydata)

        query_lower = query.lower()
        results: list[dict] = []
        seen_uuids: set[str] = set()

        for filename, raw_blob in blobs.items():
            if len(results) >= max_results:
                break

            # Extract UUID from filename (strip .0 suffix)
            uuid_key = filename
            if uuid_key.endswith(".0"):
                uuid_key = uuid_key[:-2]

            if uuid_key in seen_uuids:
                continue

            dec = try_decompress(bytes(raw_blob))
            if not dec:
                continue

            # Fast byte-level search before full text decode
            query_bytes = query_lower.encode("utf-8")
            if query_bytes not in dec.lower():
                continue

            # Decode and extract BSL blocks
            blocks = extract_code_blocks(dec)
            matching_blocks: list[dict] = []
            for block in blocks:
                block_lower = block.lower()
                idx = block_lower.find(query_lower)
                if idx < 0:
                    continue
                # Extract surrounding context
                start = max(0, idx - 60)
                end = min(len(block), idx + len(query) + 60)
                ctx = block[start:end]
                lines = ctx.split("\n")
                context = "\n".join(lines[:6])
                matching_blocks.append({
                    "block_index": len(matching_blocks),
                    "line_number": block[:idx].count("\n") + 1,
                    "context": context,
                    "block_size": len(block),
                })

            if matching_blocks:
                tech_name = uuid_to_tech.get(uuid_key, uuid_key)
                seen_uuids.add(uuid_key)
                results.append({
                    "uuid": uuid_key,
                    "tech_name": tech_name,
                    "matches": matching_blocks,
                    "match_count": len(matching_blocks),
                    "total_blocks": len(blocks),
                })

        # Sort by match count descending
        results.sort(key=lambda r: -r["match_count"])
        return results[:max_results]

    finally:
        session.close()


def _search_bsl_code(dbname: str, args: dict) -> list[TextContent]:
    """Search BSL code in all modules for a text fragment."""
    query = args.get("query", "").strip()
    max_results = min(args.get("max_results", 20), 100)

    if not query or len(query) < 2:
        return [TextContent(type="text", text="Provide a search query (min 2 chars).")]

    results = _search_bsl_in_config(dbname, query, max_results)

    if not results:
        return [TextContent(type="text", text=f"No matches found for '{query}'.")]

    parts = [f"Поиск по BSL-коду: «{query}» — найдено в {len(results)} модулях\n"]
    for r in results:
        parts.append(f"{r['tech_name']} ({r['uuid'][:8]}...) — {r['match_count']} совпадений")
        for m in r["matches"][:3]:
            parts.append(f"  Строка {m['line_number']}: {m['context'].strip()[:120]}")
        if r["match_count"] > 3:
            parts.append(f"  ... и ещё {r['match_count'] - 3} совпадений")
        parts.append("")

    return [TextContent(type="text", text="\n".join(parts))]


def _search_1c_queries(dbname: str, args: dict) -> list[TextContent]:
    """Search for 1C query patterns in BSL modules and translate them."""
    query = args.get("query", "").strip()
    max_results = min(args.get("max_results", 10), 50)

    if not query or len(query) < 2:
        return [TextContent(type="text", text="Provide a search query (min 2 chars).")]

    # Use BSL search to find modules
    bsl_results = _search_bsl_in_config(dbname, query, max_results)

    if not bsl_results:
        return [TextContent(type="text", text=f"No matches found for '{query}'.")]

    from py1cv8.query_translator import extract_queries_from_bsl

    reg = _loader(dbname)
    resolver = _make_resolver(reg)
    dialect = DB_DIALECT.get(dbname, "postgresql")

    parts = [f"Поиск 1С-запросов: «{query}» — найдено в {len(bsl_results)} модулях\n"]

    for r in bsl_results:
        parts.append(f"{r['tech_name']} ({r['uuid'][:8]}...)")

        # Re-read the full code for this module to extract queries
        code_results = _get_bsl_code_from_db(dbname, r["uuid"])
        if not code_results:
            continue

        for cr in code_results:
            for block in cr.get("code_blocks", []):
                if query.lower() not in block.lower():
                    continue
                try:
                    translated = extract_queries_from_bsl(block, resolver, dialect=dialect)
                    for q in translated.queries:
                        parts.append(f"\n  SQL: {q.sql[:200]}")
                        if q.parameters:
                            parts.append(f"  Параметры: {q.parameters}")
                        if q.note:
                            parts.append(f"  Примечание: {q.note}")
                except Exception:
                    parts.append("  (не удалось распарсить запрос)")

        parts.append("")

    return [TextContent(type="text", text="\n".join(parts))]


# ── Config versions ──────────────────────────────────────────────────────


def _parse_versions_blob(txt: str) -> dict[str, str]:
    """Parse versions blob {1,N,"",uuid,"ver",...} into {entry_uuid: version_string}."""
    import re
    pat = re.compile(
        r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
        r',"([^"]*)"'
    )
    return {m.group(1).lower(): m.group(2) for m in pat.finditer(txt)}


def _read_versions_blob(session, table: str) -> dict[str, str] | None:
    """Read and parse the 'versions' blob from config or configsave table."""
    import zlib

    from sqlalchemy import text as sql_text
    try:
        row = session.execute(
            sql_text(f"SELECT binarydata FROM {table} WHERE filename='versions'")
        ).one()
    except Exception:
        return None
    data = bytes(row[0])
    try:
        dec = zlib.decompress(data, -15)
    except zlib.error:
        return None
    return _parse_versions_blob(dec.decode("utf-8-sig", errors="replace"))


_resolve_cache: dict[str, dict | None] = {}

# Map 1C type_num → human-readable category
# Derived from metadata_map analysis of known objects
_TYPE_NUM_TO_CATEGORY: dict[int, str] = {
    0: "Settings",
    1: "ScheduledJobs",
    2: "IntegrationServices",
    3: "CommonModules",
    4: "Sessions",
    6: "Subsystems",
    7: "EventSubscriptions",
    12: "Bots",
    16: "Constants",
    17: "CommonForms",
    19: "CommandGroups",
    20: "Enums",
    22: "FunctionalOptions",
    33: "InformationRegisters",
    34: "ChartsOfCharacteristicTypes",
    40: "Documents",
    57: "Catalogs",
    68: "ConfigSave",
}


def _category_from_type_num(type_num: int | None) -> str:
    """Infer category from 1C metadata type number."""
    if type_num is None:
        return ""
    return _TYPE_NUM_TO_CATEGORY.get(type_num, "")


def _resolve_metadata_from_file(
    session, version_uuid: str, reg: SchemaRegistry,
) -> dict | None:
    """Resolve a version UUID to metadata info with caching and direct lookup.

    1. Fast-path: check if version_uuid is already in metadata_map.
    2. Read the blob from configsave/config, extract {1,0,...} metadata UUID.
    3. Results are cached for the lifetime of the session.
    """
    import re
    import zlib

    from sqlalchemy import text as sql_text

    # Strip .0, .N suffixes
    base_uuid = re.sub(r'\.[0-9]+$', '', version_uuid.lower())

    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', base_uuid, re.IGNORECASE):
        return None

    # Check cache
    if base_uuid in _resolve_cache:
        return _resolve_cache[base_uuid]

    # Fast-path: direct metadata_map lookup
    meta_info = reg.metadata_map.get(base_uuid)
    if meta_info is not None:
        obj_info = reg.get_object_by_uuid(base_uuid)
        cat = (
            obj_info.category
            if obj_info
            else _category_from_type_num(meta_info.get("type_num"))
        )
        result = {
            "metadata_uuid": base_uuid,
            "tech_name": meta_info.get("tech_name", ""),
            "category": cat,
            "display_ru": obj_info.display_ru if obj_info else meta_info.get("display_names", {}).get("ru", ""),
            "storage_table": "(metadata_map)",
        }
        _resolve_cache[base_uuid] = result
        return result

    # Fallback: try to read the blob
    # Try both the original version string (may include .N suffix for multi-part files)
    # and the base UUID (for special files like ConfigSave descriptor)
    filenames_to_try = [version_uuid.lower(), base_uuid]
    for tbl in ("configsave", "config"):
        for fn in filenames_to_try:
            try:
                row = session.execute(
                    sql_text(f"SELECT binarydata FROM {tbl} WHERE filename='{fn}' LIMIT 1")
                ).one_or_none()
                if row is None:
                    continue
                data = bytes(row[0])
                dec = zlib.decompress(data, -15)
                txt = dec.decode("utf-8-sig", errors="replace")
                m = re.search(
                    r'\{1,0,([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\}',
                    txt,
                )
                if m:
                    meta_uuid = m.group(1).lower()
                    meta_info2 = reg.metadata_map.get(meta_uuid, {})
                    obj_info2 = reg.get_object_by_uuid(meta_uuid)
                    cat2 = (
                        obj_info2.category
                        if obj_info2
                        else _category_from_type_num(meta_info2.get("type_num"))
                    )
                    result = {
                        "metadata_uuid": meta_uuid,
                        "tech_name": meta_info2.get("tech_name", ""),
                        "category": cat2,
                        "display_ru": obj_info2.display_ru if obj_info2 else meta_info2.get("display_names", {}).get("ru", ""),
                        "storage_table": tbl,
                    }
                    _resolve_cache[base_uuid] = result
                    return result
                # Blob exists but no {1,0,...} pattern — detect sub-object type
                type_hint = ""
                if "{5,1," in txt:
                    type_hint = "Form (HTML)"
                elif "{1,1," in txt and "Module" in txt:
                    type_hint = "Module (BSL)"
                elif "{1,1," in txt:
                    type_hint = "Sub-object"
                obj_info2 = reg.get_object_by_uuid(base_uuid)
                result = {
                    "metadata_uuid": base_uuid,
                    "tech_name": obj_info2.tech_name if obj_info2 else type_hint,
                    "category": obj_info2.category if obj_info2 else "SubObject",
                    "display_ru": obj_info2.display_ru if obj_info2 else "",
                    "storage_table": tbl,
                    "note": f"Version string references a sub-object ({type_hint or 'no metadata reference'})",
                }
                _resolve_cache[base_uuid] = result
                return result
            except Exception:
                continue

    _resolve_cache[base_uuid] = None
    return None


def _preload_blob_locations(session) -> tuple[set[str], set[str]]:
    """Pre-load sets of filenames from configsave and config tables."""
    from sqlalchemy import text as sql_text
    cs_files = {r[0].lower() for r in session.execute(sql_text("SELECT filename FROM configsave"))}
    cfg_files = {r[0].lower() for r in session.execute(sql_text("SELECT filename FROM config"))}
    return cs_files, cfg_files


def _get_config_snapshot(dbname: str, args: dict) -> list[TextContent]:
    """Parse configsave.versions and return a snapshot of all config objects.

    Maps internal version UUIDs to metadata objects by reading the blobs.
    """
    from py1cv8.db import get_session

    session = get_session(dbname)
    try:
        source = args.get("source", "configsave")
        if source not in ("configsave", "config"):
            return [TextContent(type="text", text="source must be 'configsave' or 'config'.")]

        versions = _read_versions_blob(session, source)
        if versions is None:
            return [TextContent(
                type="text",
                text=f"Не удалось прочитать {source}.versions. "
                     "Убедитесь, что есть сохранённая конфигурация.",
            )]

        reg = _loader(dbname)
        cs_files, cfg_files = _preload_blob_locations(session)

        # Categorise entries
        by_cat: dict[str, list[dict]] = {}
        other_count = 0

        for entry_uuid, ver_str in sorted(versions.items()):
            # Special entries
            if ver_str in ("root", "version", "versions"):
                other_count += 1
                continue

            # Try to resolve version UUID to metadata
            meta = _resolve_metadata_from_file(session, ver_str, reg)
            cat = (meta or {}).get("category") or "Unresolved"
            entry: dict = {
                "entry_uuid": entry_uuid,
                "version": ver_str,
            }
            if meta:
                entry["metadata_uuid"] = meta["metadata_uuid"]
                if meta["tech_name"]:
                    entry["tech_name"] = meta["tech_name"]
                if meta["display_ru"]:
                    entry["display_ru"] = meta["display_ru"]
                if meta["metadata_uuid"] is None:
                    entry["note"] = f"Версия есть в {meta['storage_table']}, но без ссылки на объект метаданных"
            else:
                # Check if the version UUID is a known file but metadata not found
                if ver_str in cs_files or ver_str in cfg_files:
                    entry["note"] = "Файл существует, UUID объекта метаданных не найден"
                else:
                    entry["note"] = "Не удалось найти файл для этой версии"

            by_cat.setdefault(cat, []).append(entry)

        ts_row = session.execute(
            text("SELECT creation FROM configsave WHERE filename='versions' LIMIT 1")
        ).one_or_none()
        timestamp = str(ts_row[0]) if ts_row else None

        result = {
            "source": source,
            "timestamp": timestamp,
            "total_entries": len(versions),
            "by_category": {
                cat: {"count": len(entries), "objects": entries[:100]}
                for cat, entries in sorted(by_cat.items(), key=lambda x: -len(x[1]))
            },
            "special_entries": other_count,
        }

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


def _find_changed_objects(dbname: str, args: dict) -> list[TextContent]:
    """Compare configsave (pending) vs config (live) to find pending changes.

    Resolves version UUIDs to metadata object names by reading the blobs.
    Highlights what the developer changed but hasn't applied yet.
    """
    from py1cv8.db import get_session

    session = get_session(dbname)
    try:
        saved = _read_versions_blob(session, "configsave")
        live = _read_versions_blob(session, "config")

        if saved is None or live is None:
            return [TextContent(type="text", text="Не удалось прочитать configsave.versions или config.versions.")]

        reg = _loader(dbname)
        cs_files, cfg_files = _preload_blob_locations(session)

        saved_keys = set(saved.keys())
        live_keys = set(live.keys())
        common = saved_keys & live_keys

        # Changed: same entry UUID but different version string
        changed: list[dict] = []
        for k in sorted(common):
            sv = saved[k]
            lv = live[k]
            if sv != lv:
                meta_sv = _resolve_metadata_from_file(session, sv, reg)
                meta_lv = _resolve_metadata_from_file(session, lv, reg)
                changed.append({
                    "entry_uuid": k,
                    "saved_version": sv,
                    "live_version": lv,
                    "saved_object": meta_sv["tech_name"] if meta_sv and meta_sv["tech_name"] else "?",
                    "saved_metadata_uuid": (meta_sv or {}).get("metadata_uuid") or "",
                    "live_object": meta_lv["tech_name"] if meta_lv and meta_lv["tech_name"] else "?",
                    "live_metadata_uuid": (meta_lv or {}).get("metadata_uuid") or "",
                })

        # New: only in saved
        new_list: list[dict] = []
        for k in sorted(saved_keys - live_keys):
            sv = saved[k]
            meta = _resolve_metadata_from_file(session, sv, reg)
            new_list.append({
                "entry_uuid": k,
                "version": sv,
                "object_name": meta["tech_name"] if meta and meta["tech_name"] else "?",
                "metadata_uuid": (meta or {}).get("metadata_uuid"),
            })

        # Removed: only in live
        removed_list: list[dict] = []
        for k in sorted(live_keys - saved_keys):
            lv = live[k]
            meta = _resolve_metadata_from_file(session, lv, reg)
            removed_list.append({
                "entry_uuid": k,
                "version": lv,
                "object_name": meta["tech_name"] if meta and meta["tech_name"] else "?",
                "metadata_uuid": (meta or {}).get("metadata_uuid"),
            })

        result = {
            "summary": {
                "total_saved": len(saved),
                "total_live": len(live),
                "changed": len(changed),
                "new": len(new_list),
                "removed": len(removed_list),
                "has_pending_changes": len(changed) > 0 or len(new_list) > 0 or len(removed_list) > 0,
            },
            "changed_objects": changed,
            "new_objects": new_list,
            "removed_objects": removed_list,
        }

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


def _find_metadata_uuid_by_name(name_query: str, reg: SchemaRegistry) -> str | None:
    """Search for a metadata object by name across all available fields."""
    q = name_query.strip().lower()

    # 1. SchemaRegistry objects: tech_name, display_ru, uuid, main_table, table_number
    for obj in reg.objects.values():
        if q in obj.uuid.lower() or q in obj.tech_name.lower() or q in obj.display_ru.lower():
            return obj.uuid
        if obj.main_table and q in obj.main_table.lower():
            return obj.uuid
        # Also match by table_number (e.g. "53" → _reference53)
        tbl_num = str(obj.table_number) if obj.table_number else ""
        if tbl_num and tbl_num in q:
            return obj.uuid

    # 2. metadata_map all objects (includes non-table objects like modules)
    for uuid_val, info in reg.metadata_map.items():
        tn = info.get("tech_name", "")
        if tn and q in tn.lower():
            return uuid_val
        display_names = info.get("display_names", {})
        for lang_name in display_names.values():
            if lang_name and q in lang_name.lower():
                return uuid_val

    # 3. Try matching table names like "Reference_53", "reference53"
    q_clean = q.replace("_", "").replace("-", "").replace(" ", "").lower()
    for obj in reg.objects.values():
        if obj.main_table:
            tbl_clean = obj.main_table.lstrip("_").replace("_", "").lower()
            if q_clean and q_clean in tbl_clean:
                return obj.uuid
        # Also try "reference_53" → from tech_name or other fields
        if q in "reference" and obj.table_number and str(obj.table_number) in q:
            return obj.uuid

    return None


def _get_object_config_history(dbname: str, args: dict) -> list[TextContent]:
    """Show config version history for an object across save points.

    Finds the object's metadata UUID in configsave/config blobs via
    {1,0,...} patterns, then traces which versions blob entries reference it.
    """
    from py1cv8.db import get_session

    uuid_query = (args.get("uuid") or "").strip().lower()
    name_query = (args.get("name") or "").strip()

    if not uuid_query and not name_query:
        return [TextContent(type="text", text="Укажите uuid или name объекта.")]

    session = get_session(dbname)
    try:
        if not uuid_query and name_query:
            reg = _loader(dbname)
            uuid_query = _find_metadata_uuid_by_name(name_query, reg)
            if not uuid_query:
                return [TextContent(type="text", text=f"Объект '{name_query}' не найден.")]

        reg = _loader(dbname)
        obj = reg.get_object_by_uuid(uuid_query)
        meta_info = reg.metadata_map.get(uuid_query, {})
        tech_name = (obj.tech_name if obj else meta_info.get("tech_name", "")) or "?"
        display_ru = obj.display_ru if obj else meta_info.get("display_names", {}).get("ru", "")

        saved = _read_versions_blob(session, "configsave")
        live = _read_versions_blob(session, "config")

        history: list[dict] = []
        seen_entries: set[str] = set()

        def _find_matches(versions, source_label):
            """Find versions blob entries whose blob contains the metadata UUID."""
            for entry_uuid, ver_str in (versions or {}).items():
                if ver_str in ("root", "version", "versions"):
                    continue
                try:
                    meta = _resolve_metadata_from_file(session, ver_str, reg)
                    if meta and meta.get("metadata_uuid") == uuid_query:
                        key = f"{source_label}:{entry_uuid}"
                        if key not in seen_entries:
                            seen_entries.add(key)
                            history.append({
                                "source": source_label,
                                "entry_uuid": entry_uuid,
                                "version": ver_str,
                                "metadata_uuid": uuid_query,
                                "tech_name": tech_name,
                            })
                except Exception:
                    continue

        _find_matches(live, "config (live)")
        _find_matches(saved, "configsave (pending)")

        result: dict = {
            "uuid": uuid_query,
            "tech_name": tech_name,
        }
        if display_ru:
            result["display_ru"] = display_ru

        if history:
            result["history"] = history

            # Diff between sources
            if live and saved:
                live_map = {h["entry_uuid"]: h for h in history if "live" in h["source"]}
                saved_map = {h["entry_uuid"]: h for h in history if "pending" in h["source"]}
                diffs = []
                all_keys = set(live_map) | set(saved_map)
                for k in sorted(all_keys):
                    lv = live_map.get(k)
                    sv = saved_map.get(k)
                    if lv and sv and lv["version"] != sv["version"]:
                        diffs.append({
                            "entry_uuid": k,
                            "live_version": lv["version"],
                            "saved_version": sv["version"],
                            "status": "changed",
                        })
                    elif sv and not lv:
                        diffs.append({"entry_uuid": k, "saved_version": sv["version"], "status": "new"})
                    elif lv and not sv:
                        diffs.append({"entry_uuid": k, "live_version": lv["version"], "status": "removed"})
                if diffs:
                    result["differences"] = diffs
        else:
            result["note"] = "Объект не найден в истории конфигурации (возможно, это сервисный объект без version entry)."

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


# ── New tools: table_stats, find_by_value, config_diff_detail, orphaned_records ──


def _table_stats(dbname: str, args: dict) -> list[TextContent]:
    """Show row counts, NULL ratios, distinct values, date ranges, top values."""
    from sqlalchemy import text as sqlt

    from py1cv8.db import get_session

    table_name = (args.get("table") or "").strip()
    if not table_name:
        return [TextContent(type="text", text="Укажите имя таблицы.")]

    session = get_session(dbname)
    try:
        reg = _loader(dbname)
        info = reg.get_object_by_table(table_name)
        obj_name = info.tech_name if info and isinstance(info, ObjectInfo) else ""
        obj_ru = info.display_ru if info and isinstance(info, ObjectInfo) else ""

        # Get columns from information_schema
        cols = session.execute(
            sqlt(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = :t "
                "ORDER BY ordinal_position",
            ),
            {"t": table_name},
        ).all()

        if not cols:
            return [TextContent(type="text", text=f"Таблица '{table_name}' не найдена.")]

        # Row count
        row_count = session.execute(sqlt(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0

        # Per-column stats: batch into groups by type
        date_cols: list[str] = []
        num_cols: list[str] = []
        str_cols: list[str] = []
        bool_cols: list[str] = []
        other_cols: list[str] = []

        for col_name, data_type, _is_nullable in cols:
            dtype = data_type.upper()
            if dtype in ("DATE", "TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP WITH TIME ZONE"):
                date_cols.append(col_name)
            elif dtype in ("INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "REAL", "DOUBLE PRECISION", "MONEY"):
                num_cols.append(col_name)
            elif dtype in ("CHARACTER VARYING", "VARCHAR", "TEXT", "CHARACTER", "CHAR", "NAME", "USER-DEFINED"):
                str_cols.append(col_name)
            elif dtype == "BOOLEAN":
                bool_cols.append(col_name)
            else:
                other_cols.append(col_name)

        # Non-null counts for all columns (batch via UNION ALL, up to 20 per batch)
        non_null_map: dict[str, int] = {}
        distinct_map: dict[str, int] = {}
        all_col_names = [c[0] for c in cols]
        for i in range(0, len(all_col_names), 20):
            batch_names = all_col_names[i:i + 20]
            parts = []
            for cn in batch_names:
                parts.append(f"SELECT '{cn}' AS col, COUNT({cn}) AS nn, COUNT(DISTINCT {cn}) AS dist FROM {table_name}")
            batch_row = session.execute(
                sqlt(" UNION ALL ".join(parts))
            ).all()
            for r in batch_row:
                non_null_map[r[0]] = r[1]
                distinct_map[r[0]] = r[2]

        # Date ranges
        date_ranges: dict[str, dict[str, str]] = {}
        if date_cols:
            parts = [f"SELECT '{cn}' AS col, MIN({cn}) AS mn, MAX({cn}) AS mx FROM {table_name}" for cn in date_cols]
            dr_rows = session.execute(sqlt(" UNION ALL ".join(parts))).all()
            for drr in dr_rows:
                date_ranges[drr[0]] = {"min": str(drr[1] or ""), "max": str(drr[2] or "")}

        # Numeric stats
        num_stats: dict[str, dict[str, str]] = {}
        if num_cols:
            parts = [
                f"SELECT '{cn}' AS col, MIN({cn}) AS mn, MAX({cn}) AS mx, AVG({cn})::numeric(20,4) AS avg FROM {table_name}"
                for cn in num_cols
            ]
            ns_rows = session.execute(sqlt(" UNION ALL ".join(parts))).all()
            for nsr in ns_rows:
                num_stats[nsr[0]] = {"min": str(nsr[1] or ""), "max": str(nsr[2] or ""), "avg": str(nsr[3] or "")}

        # Top values for string columns (limit to 10 best)
        # Also try USER-DEFINED columns (1C custom types) by casting to text
        top_values: dict[str, list[dict]] = {}
        all_str = str_cols + [c for c in other_cols]
        for sc in all_str[:10]:
            try:
                cast_sc = f"{sc}::text" if sc in other_cols else sc
                tv = session.execute(
                    sqlt(f"SELECT {cast_sc} AS val, COUNT(*) AS cnt FROM {table_name} WHERE {sc} IS NOT NULL AND {cast_sc} != '' GROUP BY {cast_sc} ORDER BY cnt DESC LIMIT 10")
                ).all()
                if tv:
                    top_values[sc] = [
                        {"value": str(tvr[0])[:80] if tvr[0] else "(empty)", "count": tvr[1]}
                        for tvr in tv
                    ]
            except Exception:
                pass

        # Build result
        header_parts = [f"Таблица: {table_name}"]
        if obj_name:
            header_parts.append(f" ({obj_name})")
        if obj_ru:
            header_parts.append(f" — {obj_ru}")
        header_parts.append(f" — {row_count} строк")

        result_lines = ["".join(header_parts), ""]
        result_lines.append(f"{'Колонка':35s} {'Тип':20s} {'Всего':>8s} {'Не-NULL':>8s} {'%':>5s} {'Distinct':>10s}")
        result_lines.append("-" * 90)
        for col_name, data_type, _is_nullable in cols:
            nn = non_null_map.get(col_name, 0)
            dist = distinct_map.get(col_name, 0)
            nn_pct = (nn / row_count * 100) if row_count > 0 else 0.0
            dtype_short = data_type[:18] if len(data_type) > 18 else data_type
            result_lines.append(
                f"{col_name:35s} {dtype_short:20s} {row_count:>8d} {nn:>8d} {nn_pct:>4.0f}% {dist:>10d}"
            )

        # Date ranges
        if date_ranges:
            result_lines.extend(["", "Даты:"])
            for cn, dr in sorted(date_ranges.items()):
                result_lines.append(f"  {cn}: {dr['min']} → {dr['max']}")

        # Numeric stats
        if num_stats:
            result_lines.extend(["", "Числа:"])
            for cn, ns in sorted(num_stats.items()):
                result_lines.append(f"  {cn}: min={ns['min']}, max={ns['max']}, avg={ns['avg']}")

        # Top values
        if top_values:
            result_lines.extend(["", "Топ-10 значений:"])
            for cn, vals in top_values.items():
                result_lines.append(f"  {cn}:")
                for v in vals[:5]:
                    result_lines.append(f"    {v['value'][:60]:60s} ({v['count']})")
                if len(vals) > 5:
                    result_lines.append(f"    ... и ещё {len(vals) - 5} значений")
                    result_lines.append("")

        return [TextContent(type="text", text="\n".join(result_lines))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


def _find_by_value(dbname: str, args: dict) -> list[TextContent]:
    """Search for a value across all text/varchar columns in all or specified table."""
    from sqlalchemy import text as sqlt

    from py1cv8.db import get_session

    value = (args.get("value") or "").strip()
    table_filter = (args.get("table") or "").strip()
    max_results = min(args.get("max_results", 20), 100)

    if not value or len(value) < 2:
        return [TextContent(type="text", text="Значение должно быть минимум 2 символа.")]

    session = get_session(dbname)
    try:
        # Get all tables with their text-compatible columns
        # 1C stores strings as USER-DEFINED types; also check standard text types
        text_types = "'character varying', 'varchar', 'text', 'character', 'char', 'name', 'USER-DEFINED'"
        if table_filter:
            tables_sql = f"SELECT table_name, column_name FROM information_schema.columns WHERE table_name = :t AND data_type IN ({text_types}) ORDER BY ordinal_position"
            tables = session.execute(sqlt(tables_sql), {"t": table_filter}).all()
        else:
            tables_sql = f"SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' AND data_type IN ({text_types}) ORDER BY table_name, ordinal_position"
            tables = session.execute(sqlt(tables_sql)).all()

        # Group columns by table
        table_columns: dict[str, list[str]] = {}
        for t, c in tables:
            table_columns.setdefault(t, []).append(c)

        reg = _loader(dbname)
        from typing import Any as _Any
        results: list[dict[str, _Any]] = []
        like_pattern = f"%{value}%"

        for tbl, str_cols in table_columns.items():
            if len(results) >= max_results:
                break

            # Check if _idrref exists in this table
            has_idrref = session.execute(
                sqlt("SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='_idrref'"),
                {"t": tbl},
            ).scalar() is not None
            id_field = "_idrref" if has_idrref else "ctid::text"

            # Build per-column queries (each must be parenthesized for LIMIT in UNION)
            col_parts = []
            for sc in str_cols:
                safe_sc = sc.replace("'", "''")
                col_parts.append(
                    f"(SELECT '{safe_sc}' AS col, {id_field} AS row_id, {sc}::text AS matched "
                    f"FROM {tbl} WHERE {sc}::text ILIKE '{like_pattern.replace(chr(39), chr(39)+chr(39))}' LIMIT 5)"
                )
            if not col_parts:
                continue

            try:
                union_sql = " UNION ALL ".join(col_parts)
                rows = session.execute(sqlt(union_sql)).all()
                if not rows:
                    continue
                # Get total match count (wrap sum in outer SELECT)
                count_parts = []
                for sc in str_cols:
                    count_parts.append(
                        f"(SELECT COUNT(*) FROM {tbl} WHERE {sc}::text ILIKE '{like_pattern.replace(chr(39), chr(39)+chr(39))}')"
                    )
                count_sql = "SELECT " + " + ".join(count_parts)
                total_matches = session.execute(sqlt(count_sql)).scalar() or 0

                obj_info = reg.get_object_by_table(tbl)
                tbl_name_display = obj_info.tech_name if obj_info and isinstance(obj_info, ObjectInfo) else tbl
                samples = []
                for r in rows:
                    row_id_str = str(r[1])[:24] if r[1] else ""
                    matched_str = str(r[2])[:60] if r[2] else ""
                    samples.append({"column": r[0], "row_id": row_id_str, "matched": matched_str})

                results.append({
                    "table": tbl,
                    "table_name": tbl_name_display,
                    "match_count": total_matches,
                    "samples": samples[:5],
                })
            except Exception:
                continue

        if not results:
            return [TextContent(type="text", text=f"Значение '{value}' не найдено.")]

        summary = f"Поиск «{value}» — найдено в {len(results)} таблицах"
        text_parts = [summary, ""]
        for res in results:
            text_parts.append(f"{res['table']} ({res['table_name']}): {res['match_count']} совпадений")
            for s in res["samples"]:
                text_parts.append(f"  [{s['column']}] {s['matched'][:60]}")
            text_parts.append("")

        return [TextContent(type="text", text="\n".join(text_parts[:80]))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


def _config_diff_detail(dbname: str, args: dict) -> list[TextContent]:
    """Show detailed diff of a metadata object between configsave and config."""
    import difflib
    import zlib

    from sqlalchemy import text as sqlt

    from py1cv8.db import get_session

    obj_uuid = (args.get("uuid") or "").strip().lower()
    if not obj_uuid:
        return [TextContent(type="text", text="Укажите uuid объекта.")]

    session = get_session(dbname)
    try:
        reg = _loader(dbname)

        # Try to resolve the UUID: check metadata_map, then try blob read
        meta_info = reg.metadata_map.get(obj_uuid)
        obj_info = reg.get_object_by_uuid(obj_uuid)

        tech_name = (obj_info.tech_name if obj_info else (meta_info or {}).get("tech_name", "")) or "?"
        display_ru = obj_info.display_ru if obj_info else (meta_info or {}).get("display_names", {}).get("ru", "")
        category = obj_info.category if obj_info else (_category_from_type_num((meta_info or {}).get("type_num")) or "?")

        # Read blob from configsave and config
        # Try both obj_uuid and obj_uuid + .N patterns
        def _read_blob(tbl: str, uid: str) -> str | None:
            """Read and decompress a blob from config or configsave."""
            for fn in (uid, f"{uid}.0"):
                try:
                    row = session.execute(
                        sqlt(f"SELECT binarydata FROM {tbl} WHERE filename='{fn}' LIMIT 1")
                    ).one_or_none()
                    if row is None:
                        continue
                    data = bytes(row[0])
                    dec = zlib.decompress(data, -15)
                    return dec.decode("utf-8-sig", errors="replace")
                except Exception:
                    continue
            return None

        saved_text = _read_blob("configsave", obj_uuid)
        live_text = _read_blob("config", obj_uuid)

        parts = [f"Объект: {tech_name} ({display_ru})" if display_ru else f"Объект: {tech_name}"]
        parts.append(f"UUID: {obj_uuid}")
        parts.append(f"Категория: {category}")
        parts.append("")

        if saved_text is None and live_text is None:
            parts.append("Объект не найден ни в configsave, ни в config.")
            return [TextContent(type="text", text="\n".join(parts))]

        if saved_text is None:
            parts.append("Объект есть только в config (live) — удалён из pending.")
            parts.append("")
            if live_text:
                parts.append(live_text[:2000])
            return [TextContent(type="text", text="\n".join(parts))]

        if live_text is None:
            parts.append("Объект есть только в configsave (pending) — новый объект.")
            parts.append("")
            if saved_text:
                parts.append(saved_text[:2000])
            return [TextContent(type="text", text="\n".join(parts))]

        if saved_text == live_text:
            parts.append("Объект идентичен в configsave и config — изменений нет.")
            return [TextContent(type="text", text="\n".join(parts))]

        # Show unified diff
        saved_lines = saved_text.splitlines(keepends=True)
        live_lines = live_text.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            live_lines, saved_lines,
            fromfile="config (live)",
            tofile="configsave (pending)",
            lineterm="",
        ))

        parts.append(f"Размер live: {len(live_text)} байт, размер pending: {len(saved_text)} байт")
        parts.append(f"Изменений: {len(diff_lines)} строк")
        parts.append("")

        # Limit diff output
        if len(diff_lines) > 200:
            diff_lines = diff_lines[:200] + [f"... и ещё {len(diff_lines) - 200} строк"]

        parts.extend(diff_lines)
        return [TextContent(type="text", text="\n".join(parts))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


def _orphaned_records(dbname: str, args: dict) -> list[TextContent]:
    """Find records with broken RRef/RTRef/Owner/Parent/Recorder/Folder references."""
    from sqlalchemy import text as sqlt

    from py1cv8.db import get_session

    table_filter = (args.get("table") or "").strip()
    session = get_session(dbname)

    try:
        reg = _loader(dbname)
        results: list[dict] = []
        unresolved: list[str] = []

        # Collect ALL ref columns (from relationships + direct info_schema scan)
        scanned_tables: set[tuple[str, str]] = set()
        need_data_resolve: list[tuple[str, str, str]] = []  # (table, col, ref_type)

        # 1) Process columns from reg.relationships
        for src_table, refs in reg.relationships.items():
            if table_filter and src_table != table_filter:
                continue
            info = reg.get_object_by_table(src_table)
            src_name = info.tech_name if info and isinstance(info, ObjectInfo) else src_table

            for ref in refs:
                col = ref.get("column", "")
                target = ref.get("target_table", "")
                ref_type = ref.get("ref_type", "")
                if not col:
                    continue
                scanned_tables.add((src_table, col))

                if not target:
                    need_data_resolve.append((src_table, col, ref_type))
                    continue

                try:
                    orphan_count = session.execute(
                        sqlt(
                            f"SELECT COUNT(*) FROM {src_table} src "
                            f"WHERE src.{col} IS NOT NULL "
                            f"AND NOT EXISTS (SELECT 1 FROM {target} t WHERE t._idrref = src.{col})"
                        )
                    ).scalar() or 0
                    if orphan_count > 0:
                        samples = session.execute(
                            sqlt(
                                f"SELECT src.{col} FROM {src_table} src "
                                f"WHERE src.{col} IS NOT NULL "
                                f"AND NOT EXISTS (SELECT 1 FROM {target} t WHERE t._idrref = src.{col}) "
                                f"LIMIT 5"
                            )
                        ).all()
                        results.append({
                            "source_table": src_table,
                            "source_name": src_name,
                            "column": col,
                            "ref_type": ref_type,
                            "target_table": target,
                            "orphan_count": orphan_count,
                            "sample_ids": [str(r[0])[:24] for r in samples],
                        })
                except Exception:
                    continue

        # 2) Discover additional ref columns from information_schema
        import re as _re
        ref_columns_direct: list = []
        try:
            ref_sql = (
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND data_type='bytea' "
                "AND column_name ~* '_.*(rref|rtref|owner|parent|recorder|folder)$'"
                " AND column_name != '_idrref'"
            )
            if table_filter:
                ref_sql += f" AND table_name='{table_filter}'"
            ref_columns_direct = list(session.execute(sqlt(ref_sql)).fetchall())
        except Exception:
            pass

        for src_table, col in ref_columns_direct:
            if (src_table, col) in scanned_tables:
                continue
            if table_filter and src_table != table_filter:
                continue

            # Skip PK-like columns
            if _re.match(r"^_.*_idrref$|^_idrref$", col, _re.I):
                continue

            # Infer ref_type from column name
            if _re.search(r"rtref", col, _re.I):
                ref_type = "RTRef"
            elif _re.search(r"owner", col, _re.I):
                ref_type = "Owner"
            elif _re.search(r"parent", col, _re.I):
                ref_type = "Parent"
            else:
                ref_type = "RRef"

            # Try to resolve target by table number guess
            target = ""
            m = _re.match(r"^_fld(\d+)", col, _re.I)
            if m:
                tbl_num = m.group(1)
                for prefix in ("_reference", "_document", "_inforg", "_const", "_enum"):
                    candidate = f"{prefix}{tbl_num}"
                    if candidate in reg.tables:
                        target = candidate
                        break

            if not target:
                need_data_resolve.append((src_table, col, ref_type))
            else:
                info = reg.get_object_by_table(src_table)
                src_name = info.tech_name if info and isinstance(info, ObjectInfo) else src_table
                try:
                    orphan_count = session.execute(
                        sqlt(
                            f"SELECT COUNT(*) FROM {src_table} src "
                            f"WHERE src.{col} IS NOT NULL "
                            f"AND NOT EXISTS (SELECT 1 FROM {target} t WHERE t._idrref = src.{col})"
                        )
                    ).scalar() or 0
                    if orphan_count > 0:
                        samples = session.execute(
                            sqlt(
                                f"SELECT DISTINCT src.{col} FROM {src_table} src "
                                f"WHERE src.{col} IS NOT NULL "
                                f"AND NOT EXISTS (SELECT 1 FROM {target} t WHERE t._idrref = src.{col}) "
                                f"LIMIT 5"
                            )
                        ).all()
                        results.append({
                            "source_table": src_table,
                            "source_name": src_name,
                            "column": col,
                            "ref_type": ref_type,
                            "target_table": target,
                            "orphan_count": orphan_count,
                            "sample_ids": [str(r[0])[:24] for r in samples],
                        })
                except Exception:
                    need_data_resolve.append((src_table, col, ref_type))

        # 3) Data-based resolution: sample a value and find target via data matching.
        #    Then verify orphan values exist in NO table (not just the guessed one).
        data_resolved: set[tuple[str, str]] = set()
        if need_data_resolve and not table_filter:
            tables_with_idrref: list[str] = []
            for t in reg.tables:
                obj = reg.get_object_by_table(t)
                if obj is None:
                    continue
                if any(c.name == "_idrref" for c in obj.columns):
                    tables_with_idrref.append(t)

            zero_uuid = bytes(16)

            for src_table, col, ref_type in need_data_resolve:
                try:
                    row = session.execute(
                        sqlt(
                            f"SELECT {col} FROM {src_table} "
                            f"WHERE {col} IS NOT NULL AND {col} != :zero LIMIT 1"
                        ),
                        {"zero": zero_uuid},
                    ).first()
                    if not row:
                        continue
                    sample = row[0]

                    found_target = None
                    for candidate_tbl in tables_with_idrref:
                        if candidate_tbl == src_table:
                            continue
                        try:
                            hit = session.execute(
                                sqlt(f"SELECT 1 FROM {candidate_tbl} WHERE _idrref = :v LIMIT 1"),
                                {"v": sample},
                            ).first()
                            if hit:
                                found_target = candidate_tbl
                                break
                        except Exception:
                            continue

                    if not found_target:
                        continue

                    data_resolved.add((src_table, col))

                    # Find candidate orphans against the guessed target
                    orphan_candidates = session.execute(
                        sqlt(
                            f"SELECT DISTINCT src.{col} FROM {src_table} src "
                            f"WHERE src.{col} IS NOT NULL AND src.{col} != :zero "
                            f"AND NOT EXISTS (SELECT 1 FROM {found_target} t WHERE t._idrref = src.{col})"
                        ),
                        {"zero": zero_uuid},
                    ).all()

                    if not orphan_candidates:
                        continue

                    # Verify each orphan value against ALL tables
                    orphan_values = [r[0] for r in orphan_candidates]
                    true_orphans = []

                    for val in orphan_values:
                        found_anywhere = False
                        for candidate_tbl in tables_with_idrref:
                            try:
                                hit = session.execute(
                                    sqlt(f"SELECT 1 FROM {candidate_tbl} WHERE _idrref = :v LIMIT 1"),
                                    {"v": val},
                                ).first()
                                if hit:
                                    found_anywhere = True
                                    break
                            except Exception:
                                continue
                        if not found_anywhere:
                            true_orphans.append(val)

                    if true_orphans:
                        info = reg.get_object_by_table(src_table)
                        src_name = info.tech_name if info and isinstance(info, ObjectInfo) else src_table
                        results.append({
                            "source_table": src_table,
                            "source_name": src_name,
                            "column": col,
                            "ref_type": ref_type,
                            "target_table": found_target,
                            "orphan_count": len(true_orphans),
                            "sample_ids": [str(v)[:24] for v in true_orphans[:5]],
                        })
                except Exception:
                    continue

            # Remaining unresolved ones that couldn't even be target-resolved
            for src_table, col, _rt in need_data_resolve:
                if (src_table, col) not in data_resolved:
                    unresolved.append(f"  {src_table}.{col} — не удалось определить таблицу-цель")
        else:
            for src_table, col, _rt in need_data_resolve:
                unresolved.append(f"  {src_table}.{col} — не удалось определить таблицу-цель")

        # ── Build output ──────────────────────────────────────────────────
        text_parts: list[str] = []
        reporting: list[str] = []
        details: list[str] = []

        if results:
            reporting.append(f"Найдено {len(results)} типов битых ссылок:")
            for r in results:
                reporting.append(
                    f"  {r['source_table']} ({r['source_name']}).{r['column']} "
                    f"→ {r['target_table']}: {r['orphan_count']} сирот"
                )
                if r["sample_ids"]:
                    reporting.append(f"    примеры: {', '.join(r['sample_ids'][:3])}")

        if not results:
            reporting.append("Битых ссылок не найдено.")

        total_rel_refs = sum(len(v) for v in reg.relationships.values()) if reg.relationships else 0
        if total_rel_refs:
            details.append(
                f"Проверено {total_rel_refs} ссылочных колонок "
                f"в {len(reg.relationships)} таблицах (relationships модуль)."
            )
        else:
            details.append(
                "Стандартных ссылочных колонок не обнаружено — "
                "используются нестандартные имена (_fldXXXrref, _owneridrref, ...)."
            )
        if ref_columns_direct:
            extra_count = len(ref_columns_direct) - sum(1 for _, c in ref_columns_direct if (_, c) in scanned_tables)
            if extra_count > 0:
                details.append(
                    f"Через прямой обход схемы найдено дополнительно {extra_count} колонок-кандидатов."
                )
        if data_resolved:
            details.append(
                f"Из них {len(data_resolved)} разрешены через сопоставление данных, "
                f"{len(unresolved)} остались неразрешёнными."
            )
        if unresolved:
            details.append(f"Не удалось определить таблицу-цель для {len(unresolved)} колонок:")
            details.extend(unresolved)

        text_parts.extend(reporting)
        text_parts.append("")
        text_parts.extend(details)

        return [TextContent(type="text", text="\n".join(text_parts))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        session.close()


# ── Run ─────────────────────────────────────────────────────────────────


def run(schema_loader: SchemaLoader | None = None) -> None:
    """Start the MCP server.

    Args:
        schema_loader: Optional SchemaLoader with DI providers.
            If not provided, uses default (backward-compat) SchemaLoader.
    """
    import asyncio

    from mcp.server.stdio import stdio_server

    global _loader
    if schema_loader is not None:
        _loader = schema_loader

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    run()
