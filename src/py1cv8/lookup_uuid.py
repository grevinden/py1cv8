"""Глубокий поиск UUID по всем таблицам базы данных 1С, содержащим колонку _idrref.

В отличие от resolve_uuid, который ищет только в таблицах, перечисленных
в DBNames (params), lookup_uuid сканирует ВСЕ таблицы схемы public/dbo,
у которых есть колонка _idrref.

Использует только SQLAlchemy ORM — без text() и сырых SQL.
"""

from __future__ import annotations

import uuid as uuid_pkg
from typing import Any

from sqlalchemy import (
    Column,
    LargeBinary,
    MetaData,
    String,
    Table,
    cast,
    func,
    select,
)
from sqlalchemy.orm import Session

from py1cv8.sql.orm.engine import is_mssql_url, session_scope
from py1cv8.sql.orm.models import InformationSchemaColumn


def _find_tables_with_idrref(session: Session, db_url: str) -> list[str]:
    """Получить список таблиц, содержащих колонку _idrref, через ORM.

    Для PostgreSQL — schema='public', для MSSQL — schema='dbo'.
    """
    schema = "dbo" if is_mssql_url(db_url) else "public"
    stmt = (
        select(InformationSchemaColumn.table_name)
        .distinct()
        .where(
            InformationSchemaColumn.column_name == "_idrref",
            InformationSchemaColumn.table_schema == schema,
        )
        .order_by(InformationSchemaColumn.table_name)
    )
    rows = session.execute(stmt).scalars().all()
    return list(rows)


def _build_where_clause(
    db_url: str,
    table: Table,
    hex_val: str,
    idrref_hex: str,
) -> Any:
    """Построить WHERE-условие для поиска _idrref по UUID.

    PostgreSQL: encode(_idrref::bytea, 'hex') IN (...).
    MSSQL:      LOWER(CONVERT(VARCHAR(32), _idrref, 2)) IN (...).
    """
    idrref_col = table.c._idrref

    if is_mssql_url(db_url):
        # CONVERT(VARCHAR(32), _idrref, 2) → hex-строка без 0x
        col_expr = func.lower(func.convert(String(32), idrref_col, 2))
    else:
        # encode(_idrref::bytea, 'hex') → hex-строка
        col_expr = func.encode(cast(idrref_col, LargeBinary), "hex")

    return col_expr.in_([hex_val, idrref_hex])


def _format_uuid(hex_str: str) -> str:
    """Hex-строка → UUID с дефисами."""
    h = hex_str.strip().lower().replace("-", "")
    if len(h) != 32:
        return hex_str
    try:
        return str(uuid_pkg.UUID(h))
    except ValueError:
        return hex_str


def lookup_uuid(
    db_url: str,
    uuid_str: str,
    limit: int = 50,
) -> list[dict]:
    """Поиск UUID во всех таблицах базы данных, содержащих колонку _idrref.

    Args:
        db_url: SQLAlchemy URL базы данных 1С (postgresql:// или mssql://).
        uuid_str: UUID для поиска (с дефисами или без).
        limit: Максимум результатов (по умолчанию 50).

    Returns:
        Список словарей с ключами: table, uuid, description, code, source.
    """
    hex_val = uuid_str.replace("-", "").strip().lower()
    # 1C хранит _idrref в перевёрнутом little-endian формате
    # для UUID: первые 4 байта, потом 2, потом 2, потом 8 — байты развёрнуты
    idrref_hex = _uuid_to_1c_idrref_hex(hex_val)

    with session_scope(db_url) as session:
        tables = _find_tables_with_idrref(session, db_url)
        results: list[dict] = []

        table_meta = MetaData()

        for tbl in tables:
            if len(results) >= limit:
                break
            try:
                # Создаём лёгкую ORM-модель для таблицы
                # Нам нужны только колонки: _idrref, _description, _code
                dynamic_table = Table(
                    tbl,
                    table_meta,
                    Column("_idrref", LargeBinary),
                    Column("_description", LargeBinary, extend_existing=True),
                    Column("_code", LargeBinary, extend_existing=True),
                    extend_existing=True,
                )

                # Строим WHERE через ORM-выражение
                where_clause = _build_where_clause(
                    db_url,
                    dynamic_table,
                    hex_val,
                    idrref_hex,
                )

                stmt = select(dynamic_table).where(where_clause).limit(1)

                row = session.execute(stmt).mappings().first()
                if row:
                    rd = {k.lower(): v for k, v in row.items()}
                    desc = rd.get("_description")
                    code = rd.get("_code")
                    results.append(
                        {
                            "table": tbl,
                            "uuid": _format_uuid(hex_val),
                            "description": _decode_bytes(desc),
                            "code": _decode_bytes(code),
                            "source": "data",
                        }
                    )
            except Exception:
                continue

        return results


def _decode_bytes(val: object) -> str | None:
    """Расшифровать bytes/bytearray/None в строку."""
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode("utf-8", errors="replace").strip()
        except Exception:
            return val.hex()
    return str(val)


def _uuid_to_1c_idrref_hex(hex_str: str) -> str:
    """1C хранит UUID колонки _idrref в little-endian формате.

    Берёт hex-строку и переворачивает байты особым образом:
    - первые 4 байта → обратный порядок
    - следующие 2 байта → обратный порядок
    - следующие 2 байта → обратный порядок
    - следующие 2 байта (из 8) → обратный порядок
    - последние 6 байт → обратный порядок
    """
    h = hex_str.strip().lower().replace("-", "")
    if len(h) != 32:
        return hex_str
    # Разбиваем как в 1С: 4-2-2-2-6
    parts = [h[0:8], h[8:12], h[12:16], h[16:20], h[20:32]]
    # Переворачиваем байты внутри каждой части
    reversed_parts = []
    for p in parts:
        # Разбиваем на байты (по 2 hex-символа) и переворачиваем
        bytes_list = [p[i : i + 2] for i in range(0, len(p), 2)]
        reversed_parts.append("".join(reversed(bytes_list)))
    return "".join(reversed_parts)
