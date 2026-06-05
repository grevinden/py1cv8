"""Разрешение UUID в человекочитаемое описание через метаданные и таблицы данных.

Модуль отвечает за поиск UUID в двух источниках:

1. **Метаданные 1С** — объекты конфигурации (справочники, документы и т.д.)
   с их техническими именами, отображаемыми названиями и type_num.
2. **Таблицы данных БД** — записи в физических таблицах 1С (_ReferenceNNN,
   _DocumentNNN, _InfoRgNNN и др.) с _Description, _Code и прочими полями.

После обнаружения модуль также предоставляет декодирование _RTRef
(typed reference) — компактного формата ссылок 1С, где первые 4 байта
хранят номер таблицы (uint32 big-endian), а остальные 12 байт — UUID записи.

Пример использования:
    >>> from py1cv8.resolve_uuid import resolve_uuid, decode_rtref
    >>> result = resolve_uuid("postgresql://...", "9c270050-b666-dffa-...")
    >>> for r in result:
    ...     print(r["tech_name"], r["description"])
    ...
    Справочник.Контрагенты  ООО Ромашка

    >>> ref = decode_rtref(bytes.fromhex("00000075"), context=ctx)
    >>> ref["table_name"]
    '_Reference117'
"""

from __future__ import annotations

import struct
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.context import build_llm_context
from py1cv8.db import is_postgres_url, quote_ident


def _normalise_uuid(raw: str) -> str:
    """Нормализовать строку UUID: удалить дефисы, пробелы, привести к нижнему регистру.

    Args:
        raw: Сырая строка UUID в любом формате (с дефисами, без, с пробелами).

    Returns:
        Нормализованная 32-символьная hex-строка в нижнем регистре.
    """
    return raw.replace("-", "").strip().lower()


def _format_uuid(hex_str: str) -> str:
    """Отформатировать 32-символьную hex-строку в стандартный UUID формата 8-4-4-4-12.

    Args:
        hex_str: 32-символьная hex-строка (с дефисами или без, в любом регистре).

    Returns:
        Отформатированный UUID в виде 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'.
        Если на входе не 32 символа, возвращает исходную строку без изменений.

    Example:
        >>> _format_uuid("9c270050b666dffa11f146fd81c23ada")
        '9c270050-b666-dffa-11f1-46fd81c23ada'
    """
    h = hex_str.strip().lower().replace("-", "")
    if len(h) != 32:
        return hex_str
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _uuid_to_1c_idrref_hex(uuid_hex: str) -> str:
    """Конвертировать стандартный UUID hex в 1C mixed-endian формат для _IDRRef.

    1С хранит time_low (байты 0-3), time_mid (4-5), time_hi (6-7)
    в little-endian внутри _IDRRef. Остальное — big-endian.

    Покомпонентное преобразование:
      - time_low (4 байта) — реверс байтов
      - time_mid (2 байта) — реверс байтов
      - time_hi (2 байта) — реверс байтов
      - clock_seq + node (8 байт) — без изменений

    Args:
        uuid_hex: 32-символьная hex-строка (без дефисов, нижний регистр).

    Returns:
        32-символьная hex-строка в 1C mixed-endian формате для поиска
        по колонке _IDRRef.

    Example:
        >>> _uuid_to_1c_idrref_hex("9c270050b666dffa11f146fd81c23ada")
        '5000279c66b6fadf11f146fd81c23ada'
    """
    return (
        uuid_hex[6:8]
        + uuid_hex[4:6]
        + uuid_hex[2:4]
        + uuid_hex[0:2]
        + uuid_hex[10:12]
        + uuid_hex[8:10]
        + uuid_hex[14:16]
        + uuid_hex[12:14]
        + uuid_hex[16:]
    )


def _find_row_by_uuid(
    conn,
    table: str,
    uuid_hex: str,
    db_url: str,
) -> dict[str, Any] | None:
    """Найти строку в таблице по UUID с учётом обоих порядков байтов.

    Выполняет SELECT * для поиска строки, где _IDRRef совпадает с указанным
    UUID в стандартном или 1C mixed-endian формате. Адаптирует SQL-запрос
    под PostgreSQL (encode/decode) или MSSQL (CONVERT).

    Args:
        conn: Активное соединение SQLAlchemy.
        table: Имя таблицы для поиска (например, '_Reference117').
        uuid_hex: 32-символьная hex-строка UUID (без дефисов).
        db_url: URL подключения к БД для определения диалекта.

    Returns:
        Словарь {имя_колонки: значение} или None, если строка не найдена
        или произошла ошибка запроса.
    """
    idrref_hex = _uuid_to_1c_idrref_hex(uuid_hex)
    tbl = quote_ident(table, db_url)
    idr = quote_ident("_idrref", db_url)

    if is_postgres_url(db_url):
        sql = text(
            f"SELECT * FROM {tbl}"
            f" WHERE encode({idr}::bytea, 'hex') IN ('{uuid_hex}', '{idrref_hex}')"
            f" LIMIT 1"
        )
    else:
        sql = text(
            f"SELECT TOP 1 * FROM {tbl}"
            f" WHERE LOWER(CONVERT(VARCHAR(32), {idr}, 2))"
            f" IN ('{uuid_hex}', '{idrref_hex}')"
        )

    try:
        result = conn.execute(sql)
        row = result.fetchone()
        if row:
            keys = list(result.keys())
            return dict(zip(keys, row, strict=True))
    except Exception:
        pass
    return None


def resolve_uuid(
    db_url: str,
    uuid_str: str,
    table_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Найти UUID в метаданных 1С и/или таблицах данных, вернуть человекочитаемый результат.

    Двухфазный поиск:
    1. **Метаданные** — проверка среди известных объектов конфигурации
       (через build_llm_context). Если UUID найден, возвращается tech_name,
       category, display_names, type_num и table_name из DBNames.
    2. **Таблицы данных** — последовательный перебор таблиц (из DBNames
       или явно указанной) с поиском по _IDRRef в обоих порядках байтов.
       При нахождении возвращается _Description и _Code записи.

    Args:
        db_url: URL подключения к БД (SQLAlchemy-совместимый).
        uuid_str: UUID в любом формате (с дефисами или без).
                  Если короче 32 hex-символов, выполняется поиск по суффиксу
                  среди всех известных UUID метаданных.
        table_name: Конкретная таблица данных для поиска. Если None,
                    автоматически перебираются все таблицы из DBNames.
        limit: Максимальное количество таблиц для перебора (по умолчанию 20).

    Returns:
        Список словарей с ключами:
          - table — имя таблицы (или None для метаданных)
          - uuid — отформатированный UUID
          - description — _Description из таблицы данных (или None)
          - code — _Code из таблицы данных (или None)
          - tech_name — техническое имя объекта метаданных
          - category — категория объекта (Справочник, Документ и т.д.)
          - display_names — отображаемые имена по языкам (только метаданные)
          - type_num — числовой код типа (только метаданные)
          - source — источник: 'metadata' или 'data'
    """
    hex_val = _normalise_uuid(uuid_str)
    results: list[dict[str, Any]] = []
    ctx = build_llm_context(db_url)

    # Phase 1: check if UUID is a known metadata object
    meta_obj = None
    for obj in ctx["objects"]:
        obj_uuid = _normalise_uuid(obj.get("uuid", ""))
        if obj_uuid == hex_val or (len(hex_val) < 32 and obj_uuid.endswith(hex_val)):
            meta_obj = obj
            if obj_uuid == hex_val:
                break

    if meta_obj:
        results.append(
            {
                "table": meta_obj.get("table_name"),
                "uuid": _format_uuid(hex_val),
                "description": None,
                "code": None,
                "tech_name": meta_obj.get("tech_name"),
                "category": meta_obj.get("category"),
                "display_names": meta_obj.get("display_names"),
                "type_num": meta_obj.get("type_num"),
                "source": "metadata",
            }
        )

    # Phase 2: search data tables (if table_name given or from DBNames)
    tables: list[str] = []
    if table_name:
        tables = [table_name]
    else:
        seen: set[str] = set()
        for obj in ctx["objects"]:
            tn = obj.get("table_name")
            if tn and tn not in seen:
                seen.add(tn)
                tables.append(tn)
            if len(tables) >= limit:
                break

    if tables:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            execution_options={"isolation_level": "AUTOCOMMIT"},
        )
        try:
            with engine.connect() as conn:
                for tbl in tables:
                    row_dict = _find_row_by_uuid(conn, tbl, hex_val, db_url)
                    if row_dict:
                        # PG folds unquoted identifiers to lowercase
                        rd = {k.lower(): v for k, v in row_dict.items()}
                        results.append(
                            {
                                "table": tbl,
                                "uuid": _format_uuid(hex_val),
                                "description": rd.get("_description"),
                                "code": rd.get("_code"),
                                "tech_name": None,
                                "category": None,
                                "source": "data",
                            }
                        )
                        break
        finally:
            engine.dispose()

    return results


# ── _RTRef (typed reference) decoding ─────────────────────────────────────


def decode_rtref(
    raw: bytes | memoryview | str,
    context: dict | None = None,
) -> dict:
    """Декодировать _RTRef — типизированную ссылку 1С.

    Формат _RTRef (16 байт):
      - байты 0-3: номер таблицы (uint32 big-endian)
      - байты 4-15: UUID записи или нулевое заполнение

    Если передан context (из build_llm_context), выполняется дополнительное
    разрешение номера таблицы в человекочитаемое имя, техническое имя
    и категорию объекта.

    Args:
        raw: _RTRef значение в виде bytes, memoryview или hex-строки.
        context: Опциональный контекст LLM (результат build_llm_context).
                 Ускоряет разрешение таблицы по номеру суффикса.

    Returns:
        Словарь с ключами:
          - table_suffix — номер таблицы (int) или None
          - table_name — полное имя таблицы (str) или None
          - tech_name — техническое имя объекта (str) или None
          - category — категория объекта (str) или None

    Example:
        >>> ref = decode_rtref(bytes.fromhex("00000075"), context=ctx)
        >>> ref["table_suffix"]
        117
        >>> ref["table_name"]
        '_Reference117'
    """
    if isinstance(raw, memoryview):
        raw = bytes(raw)
    if isinstance(raw, str):
        try:
            raw = bytes.fromhex(raw.replace("-", ""))
        except ValueError:
            return _empty_rtref()

    if not raw or len(raw) < 4:
        return _empty_rtref()

    suffix = struct.unpack(">I", raw[:4])[0]
    if suffix == 0:
        return _empty_rtref()

    result: dict[str, Any] = {
        "table_suffix": suffix,
        "table_name": None,
        "tech_name": None,
        "category": None,
    }

    if context and suffix:
        for obj in context["objects"]:
            tn = obj.get("table_name")
            if tn:
                import re

                m = re.search(r"_(\d+)$", tn)
                if m and int(m.group(1)) == suffix:
                    result["table_name"] = tn
                    result["tech_name"] = obj.get("tech_name")
                    result["category"] = obj.get("category")
                    break

    return result


def _empty_rtref() -> dict:
    """Вернуть пустой словарь-заглушку для невалидного _RTRef.

    Все поля возвращаются как None. Используется как fallback
    при невозможности декодировать входные данные.

    Returns:
        Словарь {'table_suffix': None, 'table_name': None,
                  'tech_name': None, 'category': None}.
    """
    return {
        "table_suffix": None,
        "table_name": None,
        "tech_name": None,
        "category": None,
    }
