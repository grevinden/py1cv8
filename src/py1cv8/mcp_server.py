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
    import re

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
        if isinstance(info, ObjectInfo):
            if name in info.tech_name.lower() or name in info.display_ru.lower() or name in info.uuid.lower():
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
