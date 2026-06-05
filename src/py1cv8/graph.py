"""Relationship graph for 1C metadata objects.

Builds a graph showing how objects reference each other via
_RTRef, _RRef, type discriminators, and known FK patterns.
"""

from __future__ import annotations

import re
import struct
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.context import build_llm_context


def _is_postgres(db_url: str) -> bool:
    return "postgresql" in db_url or "postgres" in db_url


def _get_table_schema(db_url: str, table_name: str) -> list[dict]:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            sql = text(
                """
                SELECT column_name, data_type
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


def _resolve_table_from_suffix(suffix: int, ctx: dict) -> dict | None:
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
                }
    return None


def _sample_rtref_targets(
    db_url: str,
    table_name: str,
    ctx: dict,
    sample_limit: int = 5,
) -> list[dict]:
    """Scan _rtref columns in a table to discover referenced targets."""
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            rtref_cols: list[dict] = []
            for col in _get_table_schema(db_url, table_name):
                if col["column_name"].endswith("_rtref"):
                    rtref_cols.append(col)
            if not rtref_cols:
                return []

            col_names = [c["column_name"] for c in rtref_cols]
            cols_sql = ", ".join(
                f"encode({c}, 'hex') AS {c}" if _is_postgres(db_url) else c
                for c in col_names
            )
            raw = conn.execute(
                text(f"SELECT {cols_sql} FROM {table_name} LIMIT :lim"),
                {"lim": sample_limit},
            )
            refs: dict[int, int] = {}
            for row in raw.fetchall():
                for _cn, val in zip(col_names, row, strict=False):
                    if val is None:
                        continue
                    try:
                        raw_bytes = bytes.fromhex(val) if isinstance(val, str) else val
                        if len(raw_bytes) >= 4:
                            suffix = struct.unpack(">I", raw_bytes[:4])[0]
                            if suffix != 0:
                                refs[suffix] = refs.get(suffix, 0) + 1
                    except (ValueError, struct.error):
                        continue

            results: list[dict] = []
            for suffix, count in sorted(refs.items(), key=lambda x: -x[1]):
                target = _resolve_table_from_suffix(suffix, ctx)
                if target:
                    results.append(
                        {
                            "type": "_rtref",
                            "table_suffix": suffix,
                            "sample_count": count,
                            **target,
                        }
                    )
            return results
    finally:
        engine.dispose()


def _sample_rref_values(
    db_url: str,
    table_name: str,
    ctx: dict,
    sample_limit: int = 5,
) -> list[dict]:
    """Scan _rref / _rrref columns and sample their UUIDs."""
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            rref_cols: list[str] = []
            for col in _get_table_schema(db_url, table_name):
                name = col["column_name"]
                if name.endswith("_rref") and not name.endswith("_rtref"):
                    rref_cols.append(name)

            if not rref_cols:
                return []

            results: list[dict] = []
            for col_name in rref_cols[:5]:
                col_sql = f"encode({col_name}, 'hex')" if _is_postgres(db_url) else col_name
                raw = conn.execute(
                    text(
                        f"SELECT DISTINCT {col_sql} AS h"
                        f" FROM {table_name}"
                        f" WHERE {col_name} IS NOT NULL LIMIT :lim"
                    ),
                    {"lim": sample_limit},
                )
                sample_uuids: list[str] = []
                for row in raw.fetchall():
                    if row[0] and isinstance(row[0], str):
                        h = row[0]
                        sample_uuids.append(f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}")

                results.append(
                    {
                        "column": col_name,
                        "type": "_rref",
                        "sample_uuids": sample_uuids,
                        "count": len(sample_uuids),
                        "table_name": None,
                        "tech_name": None,
                        "uuid": None,
                    }
                )
            return results
    finally:
        engine.dispose()


def build_graph(db_url: str, uuid_str: str) -> dict:
    """Build relationship graph for the metadata object identified by *uuid_str*.

    Returns a dict describing:
    - The object itself (metadata info)
    - Tables it references (_rtref suffixes resolved)
    - Tables that reference it (reverse _rtref)
    - Known FK columns
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
        return {
            "uuid": uuid_str,
            "error": f"UUID '{uuid_str}' not found in metadata",
        }

    result: dict[str, Any] = {
        "uuid": obj["uuid"],
        "tech_name": obj.get("tech_name"),
        "display_names": obj.get("display_names", {}),
        "category": obj.get("category"),
        "type_num": obj.get("type_num"),
        "table_name": obj.get("table_name"),
    }

    # Forward refs: what this object's table points to
    if obj.get("table_name"):
        result["references"] = _sample_rtref_targets(
            db_url, obj["table_name"], ctx,
        )
        result["rref_references"] = _sample_rref_values(
            db_url, obj["table_name"], ctx,
        )

    return result
