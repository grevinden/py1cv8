"""Граф связей для объектов метаданных 1С.

Модуль строит ориентированный граф отношений между объектами
конфигурации 1С: кто кому принадлежит (owner), кто родитель (parent),
на какие таблицы ссылаются поля _Fld{N}RRef и _Fld{N}RTRef, какие
тип-дискриминаторы используются, а также обратные ссылки (какие
объекты ссылаются на данный).

Все результаты отображаются человекочитаемыми именами полей
(из бинарных блобов метаданных) вместо технических _fld{N}rref.

Основные функции:
    - build_graph: построить граф для одного UUID
    - graph_mermaid: сгенерировать Mermaid classDiagram для одного объекта
    - graph_text: человекочитаемое текстовое описание графа
    - build_global_graph: построить граф для ВСЕХ объектов
    - graph_all_mermaid / graph_all_text: глобальный граф в разных форматах

Вспомогательные функции:
    - _resolve_from_table_suffix: поиск объекта по номеру таблицы
    - _extract_field_names: извлечение имён полей из блоба
    - _compute_fld_positions: маппинг _fld{N} → позиция
    - _build_reference_columns: сбор референсных колонок
    - _has_owneridrref / _has_parentidrref: проверка наличия колонок
    - _find_type_columns: поиск и декодирование тип-дискриминаторов
    - _resolve_uuid_against_tables: поиск UUID во всех таблицах
    - _find_reverse_rtref: поиск обратных RTRef-ссылок
    - _sample_rref_uuids: сэмплирование RRef-ссылок
    - _sample_rtref_targets: определение целевых таблиц RTRef
"""

from __future__ import annotations

import asyncio
import re
import struct
from contextlib import suppress
from typing import Any

from sqlalchemy import text

from py1cv8.blob_fetch import extract_metadata_blobs
from py1cv8.context import build_llm_context
from py1cv8.db import is_postgres_url, quote_ident
from py1cv8.describe_object import _get_table_schema  # reuse schema discovery
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex
from py1cv8.sql.orm import async_session_scope
from py1cv8.sql.types import get_db_name
from py1cv8.type_enums import TYPE_DISCRIMINATOR_MAP


def _resolve_from_table_suffix(suffix: int, ctx: dict) -> dict | None:
    """Найти объект метаданных по числовому суффиксу таблицы.

    Извлекает числовой суффикс из имени таблицы (например, 53 из
    "_Reference53") и сравнивает с переданным значением. Если объект
    найден — возвращает словарь с информацией о нём.

    Args:
        suffix: Числовой суффикс таблицы (например, 53 для _Reference53).
        ctx: Контекст метаданных, полученный через build_llm_context().
            Ожидается наличие ключа "objects" со списком объектов.

    Returns:
        Словарь с ключами table_name, tech_name, category, uuid,
        display_names, type_num или None, если объект не найден.
    """
    for obj in ctx["objects"]:
        tn = obj.get("table_name")
        if tn:
            m = re.search(r"_(\d+)$", tn)
            if m and int(m.group(1)) == suffix:
                return {
                    "table_name": tn,
                    "tech_name": obj.get("tech_name"),
                    "category": obj.get("category"),
                    "uuid": obj.get("uuid"),
                    "display_names": obj.get("display_names"),
                    "type_num": obj.get("type_num"),
                }
    return None


def _extract_field_names(blob_content: str) -> list[str]:
    """Извлечь упорядоченный список имён полей из блоба метаданных.

    Парсит текстовое содержимое блоба, находя паттерн
    {1,0,UUID},"FieldName" и извлекая имена полей. Первый элемент
    пропускается — это заголовок самого объекта (его UUID и tech_name).

    Args:
        blob_content: Текстовое содержимое блоба метаданных
            (первые ~50000 символов после декомпрессии).

    Returns:
        Список имён полей в порядке их объявления в метаданных.
        Если полей нет — пустой список.

    Пример:
        >>> _extract_field_names('... {1,0,UUID},"Name" ... {1,0,UUID},"Code" ...')
        ['Code', 'Description']
    """
    matches = re.findall(
        r'\{1,0\s*,\s*[^}]+\}\s*,\s*"([^"]+)"',
        blob_content,
    )
    return matches[1:] if len(matches) > 1 else []


def _compute_fld_positions(schema_columns: list[dict]) -> dict[str, int]:
    """Построить маппинг имён колонок _fld{N} на индексы полей.

    Извлекает номер поля из имени каждой колонки. Колонки-варианты
    одного поля (_fld{N}RRef, _fld{N}RTRef, _fld{N}_TYPE и т.д.)
    группируются по номеру поля — все они получают один и тот же
    индекс, соответствующий первой встреченной колонке с этим номером.

    Args:
        schema_columns: Список словарей с описанием колонок таблицы,
            каждый должен содержать ключ "column_name".

    Returns:
        Словарь {имя_колонки: индекс_поля}. Индексы назначаются
        последовательно, начиная с 0, в порядке возрастания номеров
        полей в таблице.

    Пример:
        >>> _compute_fld_positions([
        ...     {"column_name": "_Fld1RRef"},
        ...     {"column_name": "_Fld1RTRef"},
        ...     {"column_name": "_Fld2"},
        ... ])
        {'_Fld1RRef': 0, '_Fld1RTRef': 0, '_Fld2': 1}
    """
    fld_re = re.compile(r"_fld(\d+)", re.IGNORECASE)
    positions: dict[str, int] = {}
    field_to_pos: dict[int, int] = {}
    next_pos = 0
    for col in schema_columns:
        name = col["column_name"]
        m = fld_re.match(name)
        if m:
            field_num = int(m.group(1))
            if field_num not in field_to_pos:
                field_to_pos[field_num] = next_pos
                next_pos += 1
            positions[name] = field_to_pos[field_num]
    return positions


async def _build_reference_columns(
    db_url: str,
    table_name: str,
    obj_uuid: str,
    field_names: list[str] | None = None,
) -> list[dict]:
    """Построить список референсных колонок с human-readable именами полей.

    Собирает все колонки таблицы, являющиеся ссылками (_RRef и _RTRef),
    и сопоставляет каждой из них человекочитаемое имя поля из блоба
    метаданных. Сопоставление происходит по позиции колонки среди
    всех референсных колонок.

    Пропускает системную колонку _IDRRef — она присутствует в каждой
    таблице и не является ссылочным полем объекта.

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы, для которой собираются референсные колонки.
        obj_uuid: UUID объекта метаданных (используется для извлечения
            блоба с именами полей, если field_names не передан).
        field_names: Предварительно извлечённый список имён полей.
            Если None, будет выполнен запрос к БД для получения блоба.

    Returns:
        Список словарей с ключами:
            - column: техническое имя колонки (_Fld{N}RRef/_Fld{N}RTRef)
            - field_name: человекочитаемое имя поля из метаданных
            - type: "rref" для жёстких ссылок или "rtref" для типизированных
    """
    schema_columns = _get_table_schema(db_url, table_name)

    if field_names is None:
        field_names = []
        try:
            blobs = await extract_metadata_blobs(db_url, uuid=obj_uuid, limit=1, raw=True)
            if blobs and blobs[0].get("content"):
                field_names = _extract_field_names(blobs[0]["content"])
        except Exception:
            pass

    rref_re = re.compile(r"_fld\d+rref$", re.IGNORECASE)
    rtref_re_col = re.compile(r"_fld\d+rtref$", re.IGNORECASE)
    fld_positions = _compute_fld_positions(schema_columns)

    ref_cols: list[dict] = []
    for col in schema_columns:
        name = col["column_name"]
        if name.lower() == "_idrref":
            continue

        is_rref = bool(rref_re.match(name)) and not bool(rtref_re_col.match(name))
        is_rtref = bool(rtref_re_col.match(name))

        if not (is_rref or is_rtref):
            continue

        pos = fld_positions.get(name, -1)
        field_name = field_names[pos] if pos >= 0 and pos < len(field_names) else name

        ref_cols.append(
            {
                "column": name,
                "field_name": field_name,
                "type": "rref" if is_rref else "rtref",
            }
        )

    return ref_cols


def _has_owneridrref(db_url: str, table_name: str) -> bool:
    """Проверить, есть ли в таблице колонка _OwnerIDRRef (владелец).

    Выполняет запрос схемы таблицы через _get_table_schema и проверяет
    наличие колонки с именем, чувствительным к регистру. Наличие этой
    колонки означает, что объект может принадлежать другому объекту
    (например, подчинённый справочник).

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы для проверки.

    Returns:
        True, если колонка _OwnerIDRRef присутствует в таблице.
    """
    schema = _get_table_schema(db_url, table_name)
    return any(c["column_name"].lower() == "_owneridrref" for c in schema)


def _has_parentidrref(db_url: str, table_name: str) -> bool:
    """Проверить, есть ли в таблице колонка _ParentIDRRef (родитель).

    Выполняет запрос схемы таблицы через _get_table_schema и проверяет
    наличие колонки с именем, чувствительным к регистру. Наличие этой
    колонки означает, что объект поддерживает иерархию
    (группы/элементы справочника).

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы для проверки.

    Returns:
        True, если колонка _ParentIDRRef присутствует в таблице.
    """
    schema = _get_table_schema(db_url, table_name)
    return any(c["column_name"].lower() == "_parentidrref" for c in schema)


async def _find_type_columns(db_url: str, table_name: str) -> list[dict]:
    """Найти _TYPE-колонки в таблице и сэмплировать их значения (асинхронно).

    Определяет все колонки, имена которых заканчиваются на "_type"
    (дискриминаторы типов для ссылочных полей), и извлекает уникальные
    значения из каждой такой колонки. Полученные hex-значения
    декодируются в человекочитаемый тип через TYPE_DISCRIMINATOR_MAP.

    Для каждого типа-дискриминатора выполняется отдельный SQL-запрос
    через asyncio.TaskGroup для параллелизации.

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы для анализа.

    Returns:
        Список словарей с ключами:
            - column: имя _TYPE колонки
            - values: список словарей {hex, meaning} с уникальными
              значениями типа-дискриминатора и их интерпретацией
        Если _TYPE колонок нет — пустой список.
    """
    schema = _get_table_schema(db_url, table_name)
    type_cols = [c for c in schema if c["column_name"].endswith("_type")]
    if not type_cols:
        return []

    dbname = get_db_name(db_url)
    is_pg = is_postgres_url(db_url)

    async def _sample_one(tc: dict) -> dict | None:
        cn = tc["column_name"]
        qcn = quote_ident(cn, db_url)
        if is_pg:
            sql_snippet = f"encode({qcn}, 'hex')"
        else:
            sql_snippet = f"LOWER(CONVERT(VARCHAR(MAX), {qcn}, 2))"
        async with async_session_scope(dbname) as session:
            raw = (
                await session.execute(
                    text(
                        f"SELECT DISTINCT {sql_snippet} AS h"
                        f" FROM {quote_ident(table_name, db_url)}"
                        f" WHERE {qcn} IS NOT NULL AND length({qcn}) > 0"
                        f" LIMIT 5"
                    ),
                )
            ).fetchall()
        values: list[str] = []
        for row in raw:
            if row[0]:
                val = row[0]
                if isinstance(val, str):
                    values.append(val)
        decoded = []
        for v in values:
            try:
                b = int(v, 16)
                decoded.append(
                    {
                        "hex": f"0x{v}",
                        "meaning": TYPE_DISCRIMINATOR_MAP.get(b, f"Unknown type 0x{b:02X}"),
                    }
                )
            except ValueError:
                decoded.append({"hex": v, "meaning": "unknown"})
        return {"column": cn, "values": decoded}

    results: list[dict] = []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_sample_one(tc)) for tc in type_cols]
    for t in tasks:
        r = t.result()
        if r:
            results.append(r)
    return results


async def _resolve_uuid_against_tables(
    db_url: str,
    uuid_hex_std: str,
    ctx: dict,
) -> dict | None:
    """Найти UUID в _IDRRef любой известной таблицы (асинхронно + TaskGroup).

    Пытается найти переданный UUID (и его 1С-вариацию через
    _uuid_to_1c_idrref_hex) в колонке _IDRRef всех таблиц, известных
    из контекста метаданных. Поиск выполняется параллельно через
    asyncio.TaskGroup.

    Args:
        db_url: Строка подключения к базе данных.
        uuid_hex_std: UUID в стандартном hex-формате (32 символа).
        ctx: Контекст метаданных со списком объектов и их таблиц.

    Returns:
        Словарь с информацией об объекте (table_name, tech_name,
        category, uuid, display_names), если UUID найден, иначе None.
    """
    candidates = {uuid_hex_std}
    with suppress(Exception):
        candidates.add(_uuid_to_1c_idrref_hex(uuid_hex_std))
    is_pg = is_postgres_url(db_url)
    dbname = get_db_name(db_url)
    arg = ",".join(f"'{h}'" for h in candidates)

    async def _check_one(obj: dict) -> dict | None:
        tn = obj.get("table_name")
        if not tn:
            return None
        try:
            qtn = quote_ident(tn, db_url)
            qidr = quote_ident("_idrref", db_url)
            if is_pg:
                sql = text(
                    f"SELECT 1 FROM {qtn} WHERE encode({qidr}::bytea, 'hex') IN ({arg}) LIMIT 1"
                )
            else:
                sql = text(
                    f"SELECT 1 FROM {qtn}"
                    f" WHERE LOWER(CONVERT(VARCHAR(32), {qidr}, 2))"
                    f" IN ({arg}) LIMIT 1"
                )
            async with async_session_scope(dbname) as session:
                row = (await session.execute(sql)).fetchone()
            if row:
                return {
                    "table_name": tn,
                    "tech_name": obj.get("tech_name"),
                    "category": obj.get("category"),
                    "uuid": obj.get("uuid"),
                    "display_names": obj.get("display_names"),
                }
        except Exception:
            pass
        return None

    objects_with_tables = [o for o in ctx["objects"] if o.get("table_name")]
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_check_one(o)) for o in objects_with_tables]
    for t in tasks:
        r = t.result()
        if r:
            return r
    return None


async def _find_reverse_rtref(
    db_url: str,
    table_suffix: int,
    ctx: dict,
) -> list[dict]:
    """Найти объекты, чьи _RTRef колонки ссылаются на указанную таблицу.

    Для каждого объекта метаданных, имеющего таблицу, проверяет все
    колонки _Fld{N}RTRef на наличие ссылок на переданный суффикс
    таблицы. Поиск выполняется параллельно через asyncio.TaskGroup.

    Сравнение происходит по первым 4 байтам RTRef-поля (которые
    содержат номер таблицы в формате uint32 BE).

    Args:
        db_url: Строка подключения к базе данных.
        table_suffix: Числовой суффикс целевой таблицы (например 53
            для _Reference53).
        ctx: Контекст метаданных со списком объектов.

    Returns:
        Список словарей, каждый с ключами:
            - table_name: имя таблицы, в которой найдена ссылка
            - tech_name: техническое имя объекта
            - uuid: UUID объекта
            - category: категория объекта
            - column: имя RTRef-колонки, содержащей ссылку
        Если обратных ссылок нет — пустой список.
    """
    is_pg = is_postgres_url(db_url)
    dbname = get_db_name(db_url)
    suffix_bytes = struct.pack(">I", table_suffix)
    suffix_hex = suffix_bytes.hex()

    async def _check_one(obj: dict) -> dict | None:
        tn = obj.get("table_name")
        if not tn:
            return None
        try:
            schema = _get_table_schema(db_url, tn)
            rtref_cols = [
                c["column_name"]
                for c in schema
                if re.match(r"_fld\d+rtref$", c["column_name"], re.IGNORECASE)
            ]
            if not rtref_cols:
                return None

            for rc in rtref_cols:
                qtn = quote_ident(tn, db_url)
                qrc = quote_ident(rc, db_url)
                if is_pg:
                    sql_text = (
                        f"SELECT 1 FROM {qtn}"
                        f" WHERE encode({qrc}, 'hex') LIKE '{suffix_hex}%'"
                        f" LIMIT 1"
                    )
                else:
                    sql_text = (
                        f"SELECT TOP 1 1 FROM {qtn}"
                        f" WHERE LOWER(CONVERT(VARCHAR(32), {qrc}, 2))"
                        f" LIKE '{suffix_hex}%'"
                    )
                async with async_session_scope(dbname) as session:
                    row = (await session.execute(text(sql_text))).fetchone()
                if row:
                    return {
                        "table_name": tn,
                        "tech_name": obj.get("tech_name"),
                        "uuid": obj.get("uuid"),
                        "category": obj.get("category"),
                        "column": rc,
                    }
        except Exception:
            pass
        return None

    objects_with_tables = [o for o in ctx["objects"] if o.get("table_name")]
    results: list[dict] = []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_check_one(o)) for o in objects_with_tables]
    for t in tasks:
        r = t.result()
        if r:
            results.append(r)
    return results


async def _sample_rref_uuids(
    db_url: str,
    table_name: str,
    field_names: list[str],
) -> list[dict]:
    """Сэмплировать UUID из _RRef колонок и определить целевые таблицы.

    Для каждой колонки _Fld{N}RRef (кроме _Fld{N}RTRef) извлекает
    несколько уникальных значений UUID, затем пытается найти каждый
    UUID в любой известной таблице. Если хотя бы один UUID разрешился
    в объект метаданных — возвращает информацию о целевой таблице.

    Все запросы выполняются параллельно через asyncio.TaskGroup.

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы для анализа.
        field_names: Список имён полей из блоба метаданных для
            человекочитаемого отображения.

    Returns:
        Список словарей с ключами:
            - column: имя RRef-колонки
            - field_name: человекочитаемое имя поля
            - sample_uuids: найденные уникальные UUID (до 4 штук)
            - target: словарь с информацией о целевой таблице (или None)
        Если RRef-колонок нет — пустой список.
    """
    schema_columns = _get_table_schema(db_url, table_name)
    rref_re = re.compile(r"_fld\d+rref$", re.IGNORECASE)
    rtref_re = re.compile(r"_fld\d+rtref$", re.IGNORECASE)

    rref_cols = [
        c["column_name"]
        for c in schema_columns
        if bool(rref_re.match(c["column_name"])) and not bool(rtref_re.match(c["column_name"]))
    ]
    if not rref_cols:
        return []

    ctx = build_llm_context(db_url)
    is_pg = is_postgres_url(db_url)
    dbname = get_db_name(db_url)
    fld_positions = _compute_fld_positions(schema_columns)

    async def _sample_one(col_name: str) -> dict:
        pos = fld_positions.get(col_name, -1)
        fn = field_names[pos] if pos >= 0 and pos < len(field_names) else col_name

        qcol = quote_ident(col_name, db_url)
        if is_pg:
            sql_snippet = f"encode({qcol}, 'hex')"
        else:
            sql_snippet = f"LOWER(CONVERT(VARCHAR(MAX), {qcol}, 2))"

        zero_check = (
            f" AND encode({qcol}, 'hex') != '00000000000000000000000000000000'" if is_pg else ""
        )
        async with async_session_scope(dbname) as session:
            raw = (
                await session.execute(
                    text(
                        f"SELECT DISTINCT {sql_snippet} AS h"
                        f" FROM {quote_ident(table_name, db_url)}"
                        f" WHERE {qcol} IS NOT NULL"
                        f" AND length({qcol}) = 16"
                        f"{zero_check}"
                        f" LIMIT 4"
                    ),
                )
            ).fetchall()

        sample_uuids: list[str] = []
        for row in raw:
            if row[0] and isinstance(row[0], str):
                h = row[0].strip().lower()
                if len(h) == 32:
                    sample_uuids.append(h)

        target = None
        for su in sample_uuids[:1]:
            target = await _resolve_uuid_against_tables(db_url, su, ctx)
            if target:
                break

        return {
            "column": col_name,
            "field_name": fn,
            "sample_uuids": sample_uuids,
            "target": target,
        }

    results: list[dict] = []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_sample_one(cn)) for cn in rref_cols]
    for t in tasks:
        results.append(t.result())
    return results


async def _sample_rtref_targets(
    db_url: str,
    table_name: str,
    ctx: dict,
    field_names: list[str],
    sample_limit: int = 5,
) -> list[dict]:
    """Сэмплировать _RTRef колонки и определить целевые таблицы по первым 4 байтам.

    _RTRef (Typed Reference) содержит в первых 4 байтах номер
    таблицы (uint32 BE), а в оставшихся 12 — UUID записи. Функция
    извлекает первые байты из нескольких строк, группирует по номерам
    таблиц и определяет, на какой объект метаданных указывает ссылка.

    Args:
        db_url: Строка подключения к базе данных.
        table_name: Имя таблицы для анализа.
        ctx: Контекст метаданных для резолвинга суффиксов таблиц.
        field_names: Список имён полей из блоба метаданных.
        sample_limit: Максимальное количество строк для сэмплирования
            (по умолчанию 5).

    Returns:
        Список словарей с ключами:
            - column: имя RTRef-колонки
            - field_name: человекочитаемое имя поля
            - table_suffix: числовой суффикс целевой таблицы
            - sample_count: количество найденных ссылок на эту таблицу
            - target: информация о целевом объекте (или None, если
              суффикс не соответствует ни одному известному объекту)
        Если RTRef-колонок нет — пустой список.
    """
    schema_columns = _get_table_schema(db_url, table_name)
    rtref_re = re.compile(r"_fld\d+rtref$", re.IGNORECASE)

    rtref_col_names = [
        c["column_name"] for c in schema_columns if bool(rtref_re.match(c["column_name"]))
    ]
    if not rtref_col_names:
        return []

    is_pg = is_postgres_url(db_url)
    dbname = get_db_name(db_url)
    cols_sql = ", ".join(
        f"encode({quote_ident(c, db_url)}, 'hex') AS {quote_ident(c, db_url)}"
        if is_pg
        else quote_ident(c, db_url)
        for c in rtref_col_names
    )
    async with async_session_scope(dbname) as session:
        raw = await session.execute(
            text(f"SELECT {cols_sql} FROM {quote_ident(table_name, db_url)} LIMIT :lim"),
            {"lim": sample_limit},
        )
        rows = raw.fetchall()

    refs: dict[tuple[str, int], int] = {}
    for row in rows:
        for col_name, val in zip(rtref_col_names, row, strict=False):
            if val is None:
                continue
            try:
                raw_bytes = bytes.fromhex(val) if isinstance(val, str) else val
                if len(raw_bytes) >= 4:
                    suffix = struct.unpack(">I", raw_bytes[:4])[0]
                    if suffix != 0:
                        key = (col_name, suffix)
                        refs[key] = refs.get(key, 0) + 1
            except (ValueError, struct.error):
                continue

    fld_positions = _compute_fld_positions(schema_columns)
    results: list[dict] = []
    for (col_name, suffix), count in sorted(refs.items(), key=lambda x: -x[1]):
        pos = fld_positions.get(col_name, -1)
        fn = field_names[pos] if pos >= 0 and pos < len(field_names) else col_name
        target = _resolve_from_table_suffix(suffix, ctx)
        results.append(
            {
                "column": col_name,
                "field_name": fn,
                "table_suffix": suffix,
                "sample_count": count,
                "target": target,
            }
        )
    return results


async def build_graph(db_url: str, uuid_str: str) -> dict:
    """Построить граф связей для объекта метаданных по его UUID.

    Центральная функция модуля. Для указанного UUID выполняет полный
    анализ графа отношений:
      1. Извлекает имена полей из блоба метаданных
      2. Собирает референсные колонки (_RRef, _RTRef) с human-readable именами
      3. Определяет владельца (Owner) через колонку _OwnerIDRRef
      4. Определяет родителя (Parent) через колонку _ParentIDRRef
      5. Резолвит _RTRef-ссылки: определяет, на какие таблицы они указывают
      6. Резолвит _RRef-ссылки: находит UUID-цели во всех таблицах
      7. Декодирует тип-дискриминаторы (_TYPE колонки)
      8. Находит обратные _RTRef-ссылки (какие объекты ссылаются на данный)

    Возвращает JSON-сериализуемый словарь, готовый для вывода
    в CLI, Mermaid-диаграмму или текстовое представление.

    Args:
        db_url: Строка подключения к базе данных.
        uuid_str: UUID объекта метаданных в любом стандартном формате
            (с дефисами, без, с постфиксом).

    Returns:
        Словарь со следующими ключами:
            - uuid: UUID объекта
            - tech_name: техническое имя объекта
            - display_names: словарь синонимов по языкам
            - category: категория объекта (Справочник, Документ и т.д.)
            - type_num: числовой код категории
            - table_name: имя таблицы в БД
            - references: список референсных колонок с именами полей
            - owner: информация об объекте-владельце (или None)
            - parent: информация об объекте-родителе (или None)
            - rtref_targets: результаты резолвинга _RTRef
            - rref_targets: результаты резолвинга _RRef
            - type_discriminators: значения тип-дискриминаторов
            - reverse_rtref: обратные _RTRef-ссылки

        Если UUID не найден в метаданных — возвращает словарь
        с ключом "error" и текстом ошибки.
    """
    ctx = build_llm_context(db_url)
    hex_raw = uuid_str.replace("-", "").lower()

    obj = None
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
        return {"uuid": uuid_str, "error": f"UUID '{uuid_str}' not found in metadata"}

    table_name = obj.get("table_name")
    obj_uuid = obj["uuid"]

    result: dict[str, Any] = {
        "uuid": obj_uuid,
        "tech_name": obj.get("tech_name"),
        "display_names": obj.get("display_names", {}),
        "category": obj.get("category"),
        "type_num": obj.get("type_num"),
        "table_name": table_name,
    }

    if not table_name:
        return result

    dbname = get_db_name(db_url)
    is_pg = is_postgres_url(db_url)

    # 1. Extract blob field names
    field_names: list[str] = []
    try:
        blobs = await extract_metadata_blobs(db_url, uuid=obj_uuid, limit=1, raw=True)
        if blobs and blobs[0].get("content"):
            field_names = _extract_field_names(blobs[0]["content"])
    except Exception:
        pass

    # 2. Reference columns with metadata names
    ref_cols = await _build_reference_columns(
        db_url,
        table_name,
        obj_uuid,
        field_names,
    )
    result["references"] = ref_cols

    # 3. _owneridrref — resolve owner (async + TaskGroup)
    result["owner"] = None
    if _has_owneridrref(db_url, table_name):
        async with async_session_scope(dbname) as session:
            qtn = quote_ident(table_name, db_url)
            qown = quote_ident("_owneridrref", db_url) if is_pg else "_owneridrref"
            if is_pg:
                owner_row = (
                    await session.execute(
                        text(
                            f"SELECT DISTINCT encode({qown}, 'hex')"
                            f" FROM {qtn}"
                            f" WHERE {qown} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    )
                ).fetchone()
            else:
                owner_row = (
                    await session.execute(
                        text(
                            f"SELECT DISTINCT LOWER(CONVERT(VARCHAR(32), {qown}, 2))"
                            f" FROM {qtn}"
                            f" WHERE {qown} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    )
                ).fetchone()

        if owner_row and owner_row[0]:
            owner_hex = owner_row[0].strip()
            owner_candidates = {owner_hex}
            with suppress(Exception):
                owner_candidates.add(_uuid_to_1c_idrref_hex(owner_hex))
            arg = ",".join(f"'{h}'" for h in owner_candidates)

            async def _find_owner(obj: dict) -> dict | None:
                tn = obj.get("table_name")
                if not tn:
                    return None
                try:
                    async with async_session_scope(dbname) as s:
                        row = (
                            await s.execute(
                                text(
                                    f"SELECT 1 FROM {quote_ident(tn, db_url)}"
                                    f" WHERE encode({quote_ident('_idrref', db_url)}::bytea, 'hex')"
                                    f" IN ({arg}) LIMIT 1"
                                ),
                            )
                        ).fetchone()
                    if row:
                        return {
                            "table_name": tn,
                            "tech_name": obj.get("tech_name"),
                            "category": obj.get("category"),
                            "uuid": obj.get("uuid"),
                            "display_names": obj.get("display_names"),
                        }
                except Exception:
                    pass
                return None

            owner_target = None
            objects_with_tables = [o for o in ctx["objects"] if o.get("table_name")]
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(_find_owner(o)) for o in objects_with_tables]
            for t in tasks:
                r = t.result()
                if r:
                    owner_target = r
                    break
            result["owner"] = owner_target

    # 4. _parentidrref — resolve parent (async + TaskGroup)
    result["parent"] = None
    if _has_parentidrref(db_url, table_name):
        async with async_session_scope(dbname) as session:
            qtn = quote_ident(table_name, db_url)
            qpar = quote_ident("_parentidrref", db_url) if is_pg else "_parentidrref"
            if is_pg:
                parent_row = (
                    await session.execute(
                        text(
                            f"SELECT DISTINCT encode({qpar}, 'hex')"
                            f" FROM {qtn}"
                            f" WHERE {qpar} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    )
                ).fetchone()
            else:
                parent_row = (
                    await session.execute(
                        text(
                            f"SELECT DISTINCT LOWER(CONVERT(VARCHAR(32), {qpar}, 2))"
                            f" FROM {qtn}"
                            f" WHERE {qpar} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    )
                ).fetchone()

        if parent_row and parent_row[0]:
            parent_hex = parent_row[0].strip()
            parent_candidates = {parent_hex}
            with suppress(Exception):
                parent_candidates.add(_uuid_to_1c_idrref_hex(parent_hex))
            arg = ",".join(f"'{h}'" for h in parent_candidates)

            async def _find_parent(obj: dict) -> dict | None:
                tn = obj.get("table_name")
                if not tn:
                    return None
                try:
                    async with async_session_scope(dbname) as s:
                        row = (
                            await s.execute(
                                text(
                                    f"SELECT 1 FROM {quote_ident(tn, db_url)}"
                                    f" WHERE encode({quote_ident('_idrref', db_url)}::bytea, 'hex')"
                                    f" IN ({arg}) LIMIT 1"
                                ),
                            )
                        ).fetchone()
                    if row:
                        return {
                            "table_name": tn,
                            "tech_name": obj.get("tech_name"),
                            "category": obj.get("category"),
                            "uuid": obj.get("uuid"),
                            "display_names": obj.get("display_names"),
                        }
                except Exception:
                    pass
                return None

            parent_target = None
            objects_with_tables = [o for o in ctx["objects"] if o.get("table_name")]
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(_find_parent(o)) for o in objects_with_tables]
            for t in tasks:
                r = t.result()
                if r:
                    parent_target = r
                    break
            result["parent"] = parent_target

    # 5. RTRef targets (typed references) — forward
    rtref_results = await _sample_rtref_targets(
        db_url,
        table_name,
        ctx,
        field_names,
    )
    if rtref_results:
        result["rtref_targets"] = rtref_results

    # 6. RRef UUID resolution
    rref_results = await _sample_rref_uuids(db_url, table_name, field_names)
    if rref_results:
        result["rref_targets"] = rref_results

    # 7. Type discriminators
    type_info = await _find_type_columns(db_url, table_name)
    if type_info:
        result["type_discriminators"] = type_info

    # 8. Reverse _rtref references
    table_suffix = None
    m = re.search(r"_(\d+)$", table_name)
    if m:
        table_suffix = int(m.group(1))
        reverse_refs = await _find_reverse_rtref(db_url, table_suffix, ctx)
        if reverse_refs:
            result["reverse_rtref"] = reverse_refs

    return result


async def graph_mermaid(db_url: str, uuid_str: str) -> str:
    """Сгенерировать Mermaid classDiagram для графа связей объекта.

    Строит визуальную диаграмму классов Mermaid, где каждый связанный
    объект (владелец, родитель, цель ссылки) представлен отдельным
    классом. Связи между классами подписаны человекочитаемыми именами
    полей, а не техническими _fld{N}rref.

    Типы связей в диаграмме:
      - Наследование ("<|") — для владельца и родителя
      - Композиция/зависимость ("<..") — для ссылочных полей
      - Пунктирная стрелка ("..>") — для обратных ссылок

    Args:
        db_url: Строка подключения к базе данных.
        uuid_str: UUID объекта метаданных.

    Returns:
        Строка с Mermaid-диаграммой в markdown-блоке ```mermaid...```.
        Если объект не найден — возвращает "ERROR: {текст ошибки}".
    """
    info = await build_graph(db_url, uuid_str)
    if "error" in info:
        return f"ERROR: {info['error']}"

    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("classDiagram")

    added: set[str] = set()
    tech = info.get("tech_name") or "Unknown"

    def _ensure_class(name: str, table: str | None, category: str | None) -> None:
        """Добавить блок класса в Mermaid-диаграмму, если ещё не добавлен.

        Внутренняя функция-замыкание, работающая со списком lines
        и множеством added из внешней области видимости. Предотвращает
        дублирование классов в диаграмме.

        Args:
            name: Имя класса (tech_name объекта).
            table: Имя таблицы в БД (отображается внутри блока).
            category: Категория объекта (отображается внутри блока).
        """
        if name and name not in added:
            added.add(name)
            lines.append("")
            lines.append(f"    class {name} {{")
            if table:
                lines.append(f"        {table}")
            if category:
                lines.append(f"        {category}")
            lines.append("    }")

    # Main object class
    _ensure_class(tech, info.get("table_name"), info.get("category"))
    for fn in info.get("field_names") or []:
        if fn and fn != tech.strip("()"):
            lines.append(f"        + {fn}")

    # Owner
    owner = info.get("owner")
    if owner:
        otn = owner.get("tech_name") or "Unknown"
        _ensure_class(otn, owner.get("table_name"), owner.get("category"))
        lines.append(f"    {otn} <|-- {tech} : владелец")

    # Parent
    parent = info.get("parent")
    if parent:
        ptn = parent.get("tech_name") or "Unknown"
        _ensure_class(ptn, parent.get("table_name"), parent.get("category"))
        lines.append(f"    {ptn} <|-- {tech} : родитель")

    # References
    refs = info.get("references") or []
    rref_targets = info.get("rref_targets") or []
    rtref_targets = info.get("rtref_targets") or []

    for ref in refs:
        col = ref["column"]
        fn = ref["field_name"]
        rtype = ref["type"]
        label = fn if fn and fn != col else col

        target = None
        if rtype == "rref":
            for rr in rref_targets:
                if rr["column"] == col:
                    target = rr.get("target")
                    break
        elif rtype == "rtref":
            for rr in rtref_targets:
                if rr["column"] == col:
                    target = rr.get("target")
                    break

        if target:
            ttn = target.get("tech_name") or "Unknown"
            _ensure_class(ttn, target.get("table_name"), target.get("category"))
            lines.append(f"    {ttn} <.. {tech} : {label}")
        elif rtype == "rtref":
            suffix = None
            for rr in rtref_targets:
                if rr["column"] == col:
                    suffix = rr.get("table_suffix")
                    break
            tag = f"#{suffix}" if suffix else col
            lines.append(f"    class {col} {{")
            lines.append(f"        {rtype} → {tag}")
            lines.append("    }")
            lines.append(f"    {col} <.. {tech} : {label}")

    # Reverse references (show as dotted lines from other objects to this one)
    reverse = info.get("reverse_rtref")
    if reverse:
        for rv in reverse:
            rtn = rv.get("tech_name") or "Unknown"
            _ensure_class(rtn, rv.get("table_name"), rv.get("category"))
            lines.append(f"    {rtn} ..> {tech} : {rv.get('column', '')}")

    lines.append("```")
    return "\n".join(lines)


async def graph_text(db_url: str, uuid_str: str) -> str:
    """Сформировать человекочитаемое текстовое описание графа связей.

    Строит многострочный текст в стиле структурированного отчёта,
    где последовательно отображаются:
      - Основная информация: UUID, имена (RU/EN), категория, таблица
      - Владелец (Owner), если есть
      - Родитель (Parent), если есть
      - Поля-ссылки с указанием типа и целевого объекта
      - Тип-дискриминаторы с расшифровкой hex → человекочитаемый тип
      - Обратные ссылки на данный объект

    Args:
        db_url: Строка подключения к базе данных.
        uuid_str: UUID объекта метаданных.

    Returns:
        Многострочный текст с графом связей, готовый для вывода
        в терминал или сохранения в файл. Если объект не найден —
        возвращает "ERROR: {текст ошибки}".
    """
    info = await build_graph(db_url, uuid_str)

    if "error" in info:
        return f"ERROR: {info['error']}"

    lines: list[str] = []
    tech = info.get("tech_name") or "(unnamed)"
    cat = info.get("category") or "Unknown"

    lines.append(f"=== Граф связей: {tech} ===")
    lines.append(f"UUID  : {info['uuid']}")
    dn = info.get("display_names") or {}
    for lang, name in sorted(dn.items()):
        lines.append(f"  [{lang}] : {name}")
    lines.append(f"Категория : {cat} (type_num={info.get('type_num')})")
    tn = info.get("table_name")
    if tn:
        lines.append(f"Таблица   : {tn}")
    else:
        lines.append("Таблица   : (нет записи в DBNames)")

    # Owner
    owner = info.get("owner")
    if owner:
        otn = owner.get("tech_name") or "(unnamed)"
        ocat = owner.get("category") or "?"
        ottn = owner.get("table_name") or "?"
        lines.append("")
        lines.append("── Владелец (Owner) ──")
        lines.append(f"  {otn} [{ocat}] → {ottn}")

    # Parent
    parent = info.get("parent")
    if parent:
        ptn = parent.get("tech_name") or "(unnamed)"
        pcat = parent.get("category") or "?"
        pttn = parent.get("table_name") or "?"
        lines.append("")
        lines.append("── Родитель (Parent) ──")
        lines.append(f"  {ptn} [{pcat}] → {pttn}")

    # References
    refs = info.get("references") or []
    rref_targets = info.get("rref_targets") or []
    rtref_targets = info.get("rtref_targets") or []

    if refs:
        lines.append("")
        lines.append("── Поля-ссылки ──")
        for ref in refs:
            col = ref["column"]
            fn = ref["field_name"]
            rtype = ref["type"]

            # Show human-readable field name; hide technical _fld{N} column
            if fn and fn != col:
                lines.append(f"  {fn}  [{rtype}]")
            else:
                lines.append(f"  {col}  [{rtype}]")

            # Show resolved rref target
            if rtype == "rref":
                for rr in rref_targets:
                    if rr["column"] == col:
                        tgt = rr.get("target")
                        if tgt:
                            lines.append(f"         → {tgt['tech_name']} ({tgt['table_name']})")
                        elif rr.get("sample_uuids"):
                            lines.append(f"         → UUID: {rr['sample_uuids'][0]}")
                        break

            # Show resolved rtref target
            if rtype == "rtref":
                for rr in rtref_targets:
                    if rr["column"] == col:
                        tgt = rr.get("target")
                        if tgt:
                            lines.append(f"         → {tgt['tech_name']} ({tgt['table_name']})")
                        else:
                            lines.append(f"         → table suffix #{rr.get('table_suffix', '?')}")
                        break

    # Type discriminators
    type_info = info.get("type_discriminators")
    if type_info:
        lines.append("")
        lines.append("── Тип-дискриминаторы ──")
        for td in type_info:
            col = td["column"]
            vals = td.get("values", [])
            if vals:
                meanings = ", ".join(v["meaning"] or v["hex"] for v in vals)
                lines.append(f"  {col} → {meanings}")

    # Reverse references
    reverse = info.get("reverse_rtref")
    if reverse:
        lines.append("")
        lines.append("── Обратные ссылки (на этот объект) ──")
        for rv in reverse:
            lines.append(f"  {rv['tech_name']} → {rv['column']} ({rv['table_name']})")

    return "\n".join(lines)


async def build_global_graph(db_url: str) -> list[dict]:
    """Построить граф связей для ВСЕХ объектов метаданных, имеющих таблицы.

    Собирает все объекты из контекста, у которых есть table_name,
    и параллельно запускает build_graph для каждого через
    asyncio.TaskGroup. Ошибки отдельных объектов подавляются —
    в результат попадают только успешно построенные графы.

    Args:
        db_url: Строка подключения к базе данных.

    Returns:
        Список словарей-графов (по одному на каждый объект с таблицей).
        Каждый словарь имеет структуру, идентичную возвращаемой
        build_graph. Если ни один объект не удалось обработать —
        возвращается пустой список.

    Примечание:
        Для больших конфигураций (сотни объектов) эта функция
        может выполняться долго из-за множества SQL-запросов.
    """
    ctx = build_llm_context(db_url)

    objects_with_tables = [o for o in ctx["objects"] if o.get("table_name")]

    async def _build_one(uuid: str) -> dict | None:
        """Построить граф для одного UUID с обработкой ошибок.

        Внутренняя вспомогательная функция для build_global_graph.
        Вызывает build_graph и возвращает результат только если
        нет ошибки. Любые исключения подавляются.

        Args:
            uuid: UUID объекта метаданных.

        Returns:
            Словарь-граф или None при ошибке.
        """
        try:
            g = await build_graph(db_url, uuid)
            if "error" not in g:
                return g
        except Exception:
            pass
        return None

    results: list[dict] = []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_build_one(o["uuid"])) for o in objects_with_tables]
    for t in tasks:
        r = t.result()
        if r:
            results.append(r)

    return results


async def graph_all_text(db_url: str) -> str:
    """Сформировать человекочитаемый текст полного графа связей всех объектов.

    Строит многострочный отчёт по всем объектам метаданных, имеющим
    таблицы. Для каждого объекта выводится:
      - Техническое имя, таблица и категория
      - Владелец (если есть)
      - Родитель (если есть)
      - Ссылочные поля с человекочитаемыми именами

    Args:
        db_url: Строка подключения к базе данных.

    Returns:
        Многострочный текст. Если нет объектов с таблицами —
        возвращает "(объекты с таблицами не найдены)".
    """
    graphs = await build_global_graph(db_url)
    if not graphs:
        return "(объекты с таблицами не найдены)"

    lines: list[str] = []
    lines.append(f"=== Полный граф связей ({len(graphs)} объектов) ===")
    lines.append("")

    for g in graphs:
        tech = g.get("tech_name") or "(unnamed)"
        tn = g.get("table_name") or "?"
        cat = g.get("category") or "?"
        lines.append(f"── {tech} [{tn}, {cat}] ──")

        owner = g.get("owner")
        if owner:
            otn = owner.get("tech_name") or "?"
            lines.append(f"  Владелец: {otn}")

        parent = g.get("parent")
        if parent:
            ptn = parent.get("tech_name") or "?"
            lines.append(f"  Родитель: {ptn}")

        for ref in g.get("references") or []:
            fn = ref.get("field_name", "")
            rtype = ref.get("type", "")
            if fn and fn != ref.get("column", ""):
                lines.append(f"  → {fn} [{rtype}]")

        lines.append("")

    return "\n".join(lines)


async def graph_all_mermaid(db_url: str) -> str:
    """Сгенерировать Mermaid classDiagram для всех объектов и их связей.

    Строит полную Mermaid-диаграмму классов, включающую все объекты
    метаданных, имеющие таблицы. Диаграмма проходит в два прохода:
      1. Добавление всех классов (объектов)
      2. Добавление связей: владелец, родитель, ссылки, обратные ссылки

    Args:
        db_url: Строка подключения к базе данных.

    Returns:
        Строка с Mermaid-диаграммой в markdown-блоке. Если объектов
        нет — возвращает заглушку с классом Error.

    Примечание:
        Для больших конфигураций диаграмма может получиться
        очень большой — рекомендуется использовать для небольших
        наборов объектов или фильтровать по подсистемам.
    """
    graphs = await build_global_graph(db_url)
    if not graphs:
        return "```mermaid\nclassDiagram\n    class Error {\n        no objects\n    }\n```"

    lines: list[str] = []
    lines.append("```mermaid")
    lines.append("classDiagram")

    added: set[str] = set()

    def _ensure_class(name: str, table: str | None, category: str | None) -> None:
        """Добавить блок класса в глобальную Mermaid-диаграмму.

        Внутренняя функция-замыкание для graph_all_mermaid. Работает
        со списком lines и множеством added из внешней области.
        Предотвращает дублирование классов.

        Args:
            name: Имя класса (tech_name объекта).
            table: Имя таблицы в БД.
            category: Категория объекта.
        """
        if name and name not in added:
            added.add(name)
            lines.append("")
            lines.append(f"    class {name} {{")
            if table:
                lines.append(f"        {table}")
            if category:
                lines.append(f"        {category}")
            lines.append("    }")

    # First pass: add all classes
    for g in graphs:
        tech = g.get("tech_name") or "Unknown"
        _ensure_class(tech, g.get("table_name"), g.get("category"))

    # Second pass: relationships
    for g in graphs:
        tech = g.get("tech_name") or "Unknown"

        owner = g.get("owner")
        if owner:
            otn = owner.get("tech_name") or "Unknown"
            _ensure_class(otn, owner.get("table_name"), owner.get("category"))
            lines.append(f"    {otn} <|-- {tech} : владелец")

        parent = g.get("parent")
        if parent:
            ptn = parent.get("tech_name") or "Unknown"
            _ensure_class(ptn, parent.get("table_name"), parent.get("category"))
            lines.append(f"    {ptn} <|-- {tech} : родитель")

        rref_targets = g.get("rref_targets") or []
        rtref_targets = g.get("rtref_targets") or []

        for ref in g.get("references") or []:
            col = ref["column"]
            fn = ref["field_name"]
            rtype = ref["type"]
            label = fn if fn and fn != col else col

            target = None
            if rtype == "rref":
                for rr in rref_targets:
                    if rr["column"] == col:
                        target = rr.get("target")
                        break
            elif rtype == "rtref":
                for rr in rtref_targets:
                    if rr["column"] == col:
                        target = rr.get("target")
                        break

            if target:
                ttn = target.get("tech_name") or "Unknown"
                _ensure_class(ttn, target.get("table_name"), target.get("category"))
                lines.append(f"    {ttn} <.. {tech} : {label}")

        # Reverse references
        reverse = g.get("reverse_rtref")
        if reverse:
            for rv in reverse:
                rtn = rv.get("tech_name") or "Unknown"
                _ensure_class(rtn, rv.get("table_name"), rv.get("category"))
                lines.append(f"    {rtn} ..> {tech} : {rv.get('column', '')}")

    lines.append("```")
    return "\n".join(lines)
