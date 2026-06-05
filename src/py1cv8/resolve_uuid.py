"""Resolve UUID to human-readable description from metadata + data tables.

First checks if the UUID is a metadata object (from context), then
searches data tables derived from DBNames entries.

Also provides _RTRef (typed reference) decoding: first 4 bytes = table suffix.
"""

from __future__ import annotations

import struct
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.context import build_llm_context
from py1cv8.db import is_postgres_url, quote_ident


def _normalise_uuid(raw: str) -> str:
    return raw.replace("-", "").strip().lower()


def _uuid_to_1c_idrref_hex(uuid_hex: str) -> str:
    """Convert standard UUID hex to 1C mixed-endian format for _IDRRef.

    1C stores time_low (bytes 0-3), time_mid (4-5), time_hi (6-7)
    in little-endian within _IDRRef.  Everything else is big-endian.

    Example:
      standard: 9c270050-b666-dffa-11f1-46fd81c23ada
      1C _idrref hex: 5000279c66b6fadf11f146fd81c23ada

    Parameters
    ----------
    uuid_hex : str
        32-char hex string (lowercase, no dashes).

    Returns
    -------
    str
        1C mixed-endian hex string for _IDRRef comparison.
    """
    return (
        uuid_hex[6:8] + uuid_hex[4:6] + uuid_hex[2:4] + uuid_hex[0:2]
        + uuid_hex[10:12] + uuid_hex[8:10]
        + uuid_hex[14:16] + uuid_hex[12:14]
        + uuid_hex[16:]
    )


def _hex_where_clause(table: str, uuid_hex: str, db_url: str) -> str:
    """Build SELECT for _Description, _Code matching _IDRRef against hex UUID."""
    idrref_hex = _uuid_to_1c_idrref_hex(uuid_hex)
    tbl = quote_ident(table, db_url)
    desc = quote_ident("_Description", db_url)
    code = quote_ident("_Code", db_url)
    idr = quote_ident("_IDRRef", db_url)
    if is_postgres_url(db_url):
        return (
            f"SELECT {desc}, {code} FROM {tbl} "
            f"WHERE encode({idr}, 'hex') IN ('{uuid_hex}', '{idrref_hex}')"
        )
    return (
        f"SELECT {desc}, {code} FROM {tbl} "
        f"WHERE LOWER(CONVERT(VARCHAR(32), {idr}, 2)) IN ('{uuid_hex}', '{idrref_hex}')"
    )


def resolve_uuid(
    db_url: str,
    uuid_str: str,
    table_name: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Look up *uuid_str* in 1C metadata + data and return human-readable info.

    Parameters
    ----------
    db_url : str
        SQLAlchemy database URL.
    uuid_str : str
        UUID with or without dashes.  If shorter than 32 hex chars,
        tries to match by suffix across known metadata UUIDs (prefix-agnostic).
    table_name : str, optional
        Specific data table to search.  If omitted, auto-searches all
        known data tables from DBNames entries.
    limit : int
        Max tables to search.

    Returns
    -------
    list[dict]
        Each dict: table, uuid, description, code, tech_name, category.
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
                "uuid": uuid_str,
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
                    sql = text(_hex_where_clause(tbl, hex_val, db_url))
                    try:
                        result = conn.execute(sql)
                        for row in result.fetchall():
                            results.append(
                                {
                                    "table": tbl,
                                    "uuid": uuid_str,
                                    "description": row[0] if len(row) > 0 else None,
                                    "code": row[1] if len(row) > 1 else None,
                                    "tech_name": None,
                                    "category": None,
                                    "source": "data",
                                }
                            )
                    except Exception:
                        continue
                    if results:
                        break
        finally:
            engine.dispose()

    if not results:
        results.append(
            {
                "table": None,
                "uuid": uuid_str,
                "description": None,
                "code": None,
                "tech_name": None,
                "category": None,
                "source": None,
            }
        )

    return results


# ── _RTRef (typed reference) decoding ─────────────────────────────────────


def decode_rtref(
    raw: bytes | memoryview | str,
    context: dict | None = None,
) -> dict:
    """Decode a _RTRef typed reference value.

    _RTRef format (16 bytes):
      bytes 0-3 : table suffix number (uint32 BE)
      bytes 4-15: UUID or zero padding

    Parameters
    ----------
    raw : bytes | memoryview | str
        The _RTRef value as bytes, memoryview, or hex string.
    context : dict, optional
        LLM context dict (from ``build_llm_context``).  If provided,
        the output includes the resolved table name and category.

    Returns
    -------
    dict with keys:
      table_suffix  — extracted number (int or None)
      table_name    — resolved table name (str or None)
      tech_name     — resolved metadata tech_name (str or None)
      category      — resolved category (str or None)
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
    return {
        "table_suffix": None,
        "table_name": None,
        "tech_name": None,
        "category": None,
    }
