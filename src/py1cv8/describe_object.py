"""Полное описание объекта 1С: метаданные + схема + blob + семплы данных.

Модуль-оркестратор, который для заданного UUID собирает все доступные
сведения об объекте конфигурации 1С:

1. **Метаданные** — техническое имя, отображаемые названия, type_num,
   категория, таблица из DBNames (через build_llm_context).
2. **Схема таблицы** — колонки, типы данных, nullable (через
   information_schema.columns).
3. **Описания колонок** — человекочитаемые подписи для стандартных
   и пользовательских полей с декодированием _RTRef-ссылок.
4. **Семплы данных** — до N строк из таблицы с форматированием
   и разрешением ссылок.
5. **Блоб метаданных** — сырое бинарное содержимое из config/configcas.

Также предоставляет функцию describe_text для форматирования
результата в читаемый текст.

Ответственность (SRP): оркестрация сбора и форматирования данных.
Декомпозиция вынесена во вспомогательные функции модуля.

Пример использования:
    >>> import asyncio
    >>> from py1cv8.describe_object import describe_object, describe_text
    >>> info = await describe_object("postgresql://...",
    ...     "9c270050-b666-dffa-11f1-46fd81c23ada")
    >>> info["tech_name"]
    'Справочник.Контрагенты'
    >>> info["table_name"]
    '_Reference117'
"""

from __future__ import annotations

import re
import struct
import uuid as uuid_mod
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.blob_fetch import extract_metadata_blobs
from py1cv8.context import build_llm_context
from py1cv8.db import quote_ident
from py1cv8.resolve_uuid import resolve_uuid
from py1cv8.type_enums import TYPE_DISCRIMINATOR_MAP

STANDARD_COLUMNS: dict[str, str] = {
    "_idrref": "Primary UUID key",
    "_version": "Record version (concurrency control)",
    "_marked": "Soft delete flag (True = deleted)",
    "_deletionmark": "Soft delete flag (True = deleted)",
    "_predefinedid": "Predefined data UUID",
    "_description": "Display name / description",
    "_code": "String code / identifier",
    "_date_time": "Document date & time",
    "_number": "Document number",
    "_posted": "Document posted flag",
    "_folder": "Folder flag (catalogs)",
    "_parentidrref": "Parent reference (hierarchy)",
    "_owneridrref": "Owner reference (subordination)",
    "_isenum": "Enum value ordinal",
    "_enumorder": "Enum sort order",
    "_revision": "Revision counter",
    "_actuality": "Actuality flag (registers)",
    "_period": "Period (registers)",
    "_recordkey": "Record key (registers)",
    "_lineno": "Line number (tabular sections)",
    "_linenosto": "Line number sequence (tabular sections)",
    "_datakey": "Data key (constants)",
    "_fld12rref": "Chart of characteristic types reference",
    "_fld13rref": "Chart of characteristic types reference",
}


def _is_postgres(db_url: str) -> bool:
    """Определить, является ли БД PostgreSQL по URL подключения.

    Args:
        db_url: URL подключения к БД.

    Returns:
        True, если URL содержит 'postgresql' или 'postgres'.
    """
    return "postgresql" in db_url or "postgres" in db_url


def _get_column_descriptions(
    schema: list[dict],
    rtref_targets: dict[str, dict] | None = None,
) -> dict[str, str]:
    """Построить словарь {имя_колонки: описание} на основе известных шаблонов и _RTRef.

    Для каждой колонки из схемы определяется её семантика:
    - Стандартные колонки (_idrref, _description, _code и др.) получают
      описания из словаря STANDARD_COLUMNS.
    - Колонки _rtref получают пометку о типизированной ссылке и,
      если доступны rtref_targets, конкретную таблицу назначения.
    - Колонки _type отмечаются как дискриминаторы типа.
    - Пользовательские поля _fld{NN} нумеруются.

    Args:
        schema: Список словарей с информацией о колонках (из _get_table_schema).
        rtref_targets: Результат _decode_rtref_values — карта {колонка: {table_info}}.

    Returns:
        Словарь {column_name: human_readable_description}.
    """
    result: dict[str, str] = {}
    for col in schema:
        name = col["column_name"]
        if name in STANDARD_COLUMNS:
            result[name] = STANDARD_COLUMNS[name]
        elif name.endswith("_rtref"):
            desc = "Typed reference — first 4 bytes = table suffix (big-endian)"
            if rtref_targets and name in rtref_targets:
                tgt = rtref_targets[name]
                tn = tgt.get("table_name")
                tech = tgt.get("tech_name")
                if tn:
                    detail = f" → {tn}"
                    if tech:
                        detail += f" ({tech})"
                    desc += detail
            result[name] = desc
        elif "rref" in name.lower():
            result[name] = "Reference (FK) — UUID from _IDRRef of another table"
        elif name.endswith("_type"):
            result[name] = "Type discriminator (0x03=Date, 0x08=Reference)"
        elif name.endswith("_owner"):
            result[name] = "Owner reference (subordinate objects)"
        elif name.endswith("_parent"):
            result[name] = "Parent reference (hierarchical objects)"
        elif name.startswith("_fld"):
            num = re.sub(r"(?i)_(rref|rtref|type|ref|owner|parent)$", "", name.replace("_fld", ""))
            if num.isdigit():
                result[name] = f"Custom field #{num}"
            else:
                result[name] = "Custom field"
        else:
            result[name] = ""

    return result


def _get_table_schema(db_url: str, table_name: str) -> list[dict]:
    """Получить метаданные колонок таблицы через information_schema.

    Args:
        db_url: URL подключения к БД.
        table_name: Имя таблицы (регистронезависимое).

    Returns:
        Список словарей с колонками: column_name, data_type, is_nullable,
        character_maximum_length, ordinal_position.
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
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        engine.dispose()


def _get_sample_data(
    db_url: str,
    table_name: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Получить семплы строк из таблицы для наглядного просмотра данных.

    Для получения детерминированных строк пытается найти подходящую
    колонку для сортировки в следующем порядке приоритета:
    _idrref → _period → _recordkey → _datakey → _key → _number → _lineno.
    Если ни одна не найдена, использует первую колонку таблицы.
    Если колонок нет — без сортировки (просто LIMIT).

    Args:
        db_url: URL подключения к БД.
        table_name: Имя таблицы для выборки.
        limit: Максимальное количество строк (по умолчанию 3).

    Returns:
        Список словарей {column_name: value} с данными строк.
        Может быть пустым, если таблица пуста.
    """
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            order_probes = [
                "_idrref",
                "_period",
                "_recordkey",
                "_datakey",
                "_key",
                "_number",
                "_lineno",
            ]
            col_result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE LOWER(table_name) = LOWER(:tn) ORDER BY ordinal_position"
                ),
                {"tn": table_name},
            )
            cols = [r[0] for r in col_result.fetchall()]
            order_col = None
            for probe in order_probes:
                if probe in cols:
                    order_col = probe
                    break
            if not order_col and cols:
                order_col = cols[0]

            if order_col:
                sql = text(
                    f"SELECT * FROM {quote_ident(table_name, db_url)}"
                    f" ORDER BY {order_col} LIMIT :lim"
                )
            else:
                sql = text(f"SELECT * FROM {quote_ident(table_name, db_url)} LIMIT :lim")

            result = conn.execute(sql, {"lim": limit})
            columns = list(result.keys())
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        engine.dispose()


def _decode_rtref_values(
    sample_rows: list[dict],
    context: dict,
) -> dict[str, dict]:
    """Просмотреть семплы данных и декодировать первые ненулевые _RTRef-значения.

    Для каждой колонки, оканчивающейся на '_rtref', сканирует строки
    семплов в поиске первого ненулевого значения. Декодирует номер таблицы
    (первые 4 байта как uint32 BE) и, используя контекст метаданных,
    находит имя таблицы, техническое имя и категорию.

    Args:
        sample_rows: Семплы строк из _get_sample_data.
        context: Контекст LLM (build_llm_context) для разрешения
                 номера таблицы в человекочитаемые имена.

    Returns:
        Словарь {column_name: {table_suffix, table_name, tech_name, category}}.
        Пустой, если семплы пусты или _rtref-колонок нет.
    """
    targets: dict[str, dict] = {}
    if not sample_rows:
        return targets

    col_names = list(sample_rows[0].keys())
    for cn in col_names:
        if not cn.endswith("_rtref"):
            continue
        for row in sample_rows:
            val = row.get(cn)
            if val is None:
                continue
            raw = bytes(val) if isinstance(val, (bytes, memoryview)) else b""
            if len(raw) < 4:
                continue
            suffix = struct.unpack(">I", raw[:4])[0]
            if suffix == 0:
                continue
            decoded: dict[str, Any] = {"table_suffix": suffix}
            for obj in context["objects"]:
                tn = obj.get("table_name")
                if tn:
                    m = re.search(r"_(\d+)$", tn)
                    if m and int(m.group(1)) == suffix:
                        decoded["table_name"] = tn
                        decoded["tech_name"] = obj.get("tech_name")
                        decoded["category"] = obj.get("category")
                        break
            targets[cn] = decoded
            break

    return targets


def _summarise_value(
    val: Any,
    col_name: str = "",
    rtref_targets: dict | None = None,
    resolve_map: dict[str, dict] | None = None,
) -> str:
    """Сформировать краткое текстовое представление значения ячейки.

    Логика форматирования:
    - None → 'NULL'
    - _rtref-колонки → '→ Table #N (table_name)'
    - _type-колонки → '0xNN = Имя_типа' (через TYPE_DISCRIMINATOR_MAP)
    - 16-байтовые значения → UUID, с разрешением через resolve_map
    - bytes > 80 → '<N bytes>'
    - строки > 80 → обрезаются до 77 + '...'

    Args:
        val: Значение ячейки (любой тип).
        col_name: Имя колонки для контекстного форматирования.
        rtref_targets: Карта _RTRef-декодирований (из _decode_rtref_values).
        resolve_map: Карта {uuid: resolved_info} для разрешения ссылок.

    Returns:
        Краткая строка с человекочитаемым представлением значения.
    """
    if val is None:
        return "NULL"
    if isinstance(val, (bytes, memoryview)):
        raw = bytes(val)
        if col_name and rtref_targets and col_name in rtref_targets:
            tgt = rtref_targets[col_name]
            suffix = tgt.get("table_suffix")
            tn = tgt.get("table_name", "")
            if suffix:
                return f"→ Table #{suffix} ({tn})"
        # Decode _type fields with TYPE_DISCRIMINATOR_MAP
        if col_name.endswith("_type") and len(raw) == 1:
            byte_val = raw[0]
            name = TYPE_DISCRIMINATOR_MAP.get(byte_val, f"Type 0x{byte_val:02X}")
            return f"0x{byte_val:02X} = {name}"
        if len(raw) == 16:
            try:
                u = str(uuid_mod.UUID(bytes=raw))
                if resolve_map and u in resolve_map:
                    r = resolve_map[u]
                    tag = r.get("description") or r.get("code") or r.get("tech_name") or ""
                    if tag:
                        return f"{u} → {tag}"
                return u
            except Exception:
                pass
        return f"<{len(raw)} bytes>"
    s = str(val)
    if len(s) > 80:
        return s[:77] + "..."
    return s


def _build_resolve_map(
    db_url: str,
    sample_rows: list[dict],
    rtref_targets: dict[str, dict],
) -> dict[str, dict]:
    """Построить карту UUID → разрешённые данные для всех UUID в семплах.

    Обходит все колонки всех строк семплов, собирает уникальные
    16-байтовые значения (потенциальные UUID) и разрешает их через
    resolve_uuid. Для _rtref-колонок использует известную таблицу
    назначения для ускорения поиска.

    Args:
        db_url: URL подключения к БД.
        sample_rows: Семплы строк из _get_sample_data.
        rtref_targets: Карта _RTRef-декодирований (из _decode_rtref_values).

    Returns:
        Словарь {str(uuid): resolved_info_dict}.
        Пустой, если семплы пусты или UUID не найдены.
    """
    resolve_map: dict[str, dict] = {}
    if not sample_rows:
        return resolve_map

    col_names = list(sample_rows[0].keys())
    seen_uuids: set[str] = set()

    for cn in col_names:
        for row in sample_rows:
            val = row.get(cn)
            if val is None:
                continue
            raw = bytes(val) if isinstance(val, (bytes, memoryview)) else b""
            if len(raw) != 16:
                continue
            try:
                u = str(uuid_mod.UUID(bytes=raw))
            except Exception:
                continue
            if u in seen_uuids:
                continue
            seen_uuids.add(u)

            # If column is _rtref, use the known target table for faster lookup
            hint = None
            if cn in rtref_targets:
                hint = rtref_targets[cn].get("table_name")

            try:
                resolved = resolve_uuid(db_url, u, table_name=hint, limit=50)
                if resolved and resolved[0].get("source"):
                    resolve_map[u] = resolved[0]
            except Exception:
                pass

    return resolve_map


async def describe_object(
    db_url: str,
    uuid_str: str,
    sample_limit: int = 3,
    resolve_refs: bool = False,
    no_blob: bool = False,
) -> dict:
    """Собрать полное описание объекта 1С по UUID.

    Асинхронная функция-оркестратор, выполняющая последовательно:
    1. Поиск объекта в метаданных через build_llm_context.
    2. Если не найден — fallback через resolve_uuid по таблицам данных.
    3. Получение схемы таблицы (information_schema).
    4. Получение семплов данных (до sample_limit строк).
    5. Декодирование _RTRef-ссылок в семплах.
    6. Разрешение UUID-ссылок (если resolve_refs=True).
    7. Построение описаний колонок.
    8. Форматирование семплов с разрешением ссылок.
    9. Определение дискриминаторов типов (_type колонки).
    10. Извлечение блоба из config/configcas (если no_blob=False).

    Args:
        db_url: URL подключения к БД.
        uuid_str: UUID объекта в любом формате.
        sample_limit: Максимальное количество строк семплов (по умолчанию 3).
        resolve_refs: Разрешать UUID-ссылки в семплах (замедляет работу).
        no_blob: Не извлекать блоб метаданных (экономит время).

    Returns:
        Словарь с ключами:
          - uuid — отформатированный UUID.
          - tech_name — техническое имя объекта.
          - display_names — отображаемые имена по языкам.
          - type_num — числовой код типа.
          - category — категория объекта (Справочник, Документ...).
          - table_name — имя таблицы данных.
          - schema — список колонок (если таблица есть).
          - column_descriptions — описания колонок.
          - sample_data — отформатированные семплы строк.
          - type_discriminators — значения дискриминаторов типов (если есть).
          - blob — сырое содержимое блоба (если no_blob=False и blob найден).
          - error — сообщение об ошибке (если объект не найден).
    """
    ctx = build_llm_context(db_url)

    # Find metadata object
    obj = None
    hex_raw = uuid_str.replace("-", "").lower()
    for o in ctx["objects"]:
        if o.get("uuid", "").replace("-", "").lower() == hex_raw:
            obj = o
            break
    if not obj:
        for o in ctx["objects"]:
            if o.get("uuid", "").replace("-", "").lower().endswith(hex_raw):
                obj = o
                break

    if not obj:
        # Fallback: try data tables via resolve
        resolved = resolve_uuid(db_url, uuid_str, limit=5)
        if resolved:
            r = resolved[0]
            tbl = r.get("table")
            if tbl:
                obj = {
                    "uuid": r["uuid"],
                    "tech_name": r.get("description") or r.get("code") or f"Record in {tbl}",
                    "display_names": {},
                    "type_num": None,
                    "category": r.get("category"),
                    "table_name": tbl,
                }

    if not obj:
        return {
            "uuid": uuid_str,
            "error": f"UUID '{uuid_str}' not found in metadata",
        }

    table = obj.get("table_name")
    result: dict = {
        "uuid": obj["uuid"],
        "tech_name": obj.get("tech_name"),
        "display_names": obj.get("display_names", {}),
        "type_num": obj.get("type_num"),
        "category": obj.get("category"),
        "table_name": table,
    }

    if table:
        schema = _get_table_schema(db_url, table)
        result["schema"] = schema

        sample_rows = _get_sample_data(db_url, table, limit=sample_limit)
        rtref_targets = _decode_rtref_values(sample_rows, ctx)
        resolve_map = _build_resolve_map(db_url, sample_rows, rtref_targets) if resolve_refs else {}
        result["column_descriptions"] = _get_column_descriptions(
            schema,
            rtref_targets=rtref_targets,
        )

        # Format sample data
        formatted: list[dict[str, str]] = []
        for row in sample_rows:
            formatted.append(
                {
                    k: _summarise_value(
                        v,
                        col_name=k,
                        rtref_targets=rtref_targets,
                        resolve_map=resolve_map,
                    )
                    for k, v in row.items()
                }
            )
        result["sample_data"] = formatted

        # Check for type discriminator on all schema columns
        type_info: dict[str, str] = {}
        for col in schema:
            if col["column_name"].endswith("_type"):
                for row in sample_rows:
                    val = row.get(col["column_name"])
                    if val and isinstance(val, (bytes, memoryview)):
                        raw = bytes(val)
                        if len(raw) == 1:
                            byte_val = raw[0]
                            name = TYPE_DISCRIMINATOR_MAP.get(byte_val, f"0x{byte_val:02X}")
                            type_info[col["column_name"]] = name
                            break
        if type_info:
            result["type_discriminators"] = type_info

    # Fetch blob (skip if --no-blob)
    if not no_blob:
        try:
            blobs = await extract_metadata_blobs(
                db_url,
                table="config",
                uuid=obj["uuid"],
                limit=1,
                raw=True,
            )
            if blobs and blobs[0].get("content"):
                result["blob"] = blobs[0]["content"]
        except Exception:
            pass

    return result


async def describe_text(
    db_url: str,
    uuid_str: str,
    sample_limit: int = 3,
    resolve_refs: bool = False,
    no_blob: bool = False,
) -> str:
    """Сформировать человекочитаемое текстовое описание объекта 1С по UUID.

    Вызывает describe_object и форматирует результат в многострочный
    текст с секциями: заголовок UUID, техническое имя, отображаемые
    имена, категория, таблица, схема колонок с описаниями, значения
    дискриминаторов типов, семплы данных, содержимое блоба.

    Args:
        db_url: URL подключения к БД.
        uuid_str: UUID объекта.
        sample_limit: Максимальное количество строк семплов.
        resolve_refs: Разрешать UUID-ссылки.
        no_blob: Не включать блоб метаданных.

    Returns:
        Многострочная строка с форматированным описанием.
        При ошибке возвращает 'ERROR: {сообщение}'.
    """
    info = await describe_object(
        db_url,
        uuid_str,
        sample_limit=sample_limit,
        resolve_refs=resolve_refs,
        no_blob=no_blob,
    )

    lines: list[str] = []

    if "error" in info:
        lines.append(f"ERROR: {info['error']}")
        return "\n".join(lines)

    tech = info.get("tech_name") or "(unnamed)"
    cat = info.get("category") or "Unknown"
    tn = info.get("type_num")
    table = info.get("table_name")

    lines.append(f"=== {info['uuid']} ===")
    lines.append(f"Technical name : {tech}")
    dn = info.get("display_names") or {}
    for lang, name in sorted(dn.items()):
        lines.append(f"  [{lang}]       : {name}")
    lines.append(f"Category       : {cat} (type_num={tn})")
    if table:
        lines.append(f"Table          : {table}")
    else:
        lines.append("Table          : (none — no DBNames entry)")

    col_desc = info.get("column_descriptions") or {}
    schema = info.get("schema")
    if schema:
        lines.append("")
        lines.append(f"--- Table schema ({table}) ---")
        for col in schema:
            cn = col["column_name"]
            dt = col["data_type"]
            desc = col_desc.get(cn, "")
            suffix = f"  — {desc}" if desc else ""
            lines.append(f"  {cn:25s} {dt:25s}{suffix}")

    # Show type discriminator info
    type_info = info.get("type_discriminators")
    if type_info:
        lines.append("")
        lines.append("--- Type discriminator values ---")
        for cn, meaning in type_info.items():
            lines.append(f"  {cn:25s} → {meaning}")

    sample = info.get("sample_data")
    if sample:
        lines.append("")
        lines.append(f"--- Sample data (first {len(sample)} rows) ---")
        for i, row in enumerate(sample):
            lines.append(f"  Row {i + 1}:")
            for k, v in row.items():
                if k in ("_idrref",):
                    continue
                if v == "NULL":
                    continue
                label = col_desc.get(k, k)
                display = f"{label} [{k}]" if label and label != k else k
                lines.append(f"    {display:40s} = {v}")

    if info.get("blob"):
        lines.append("")
        lines.append("--- Blob content (raw metadata) ---")
        lines.append(info["blob"][:6000])

    return "\n".join(lines)
