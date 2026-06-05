"""Combine context + schema + blob + sample data for a single UUID."""

from __future__ import annotations

import re
import struct
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.blob_fetch import fetch_blob
from py1cv8.config import TYPE_DISCRIMINATOR_MAP
from py1cv8.context import build_llm_context

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
    """Return True if db_url points to a PostgreSQL database."""
    return "postgresql" in db_url or "postgres" in db_url


def _get_column_descriptions(
    schema: list[dict],
    rtref_targets: dict[str, dict] | None = None,
) -> dict[str, str]:
    """Build {column_name: description} map from known columns + _rtref targets."""
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
    """Get column info from information_schema."""
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
    """Get sample rows from *table_name*.

    Probes for an orderable column (``_idrref`` → ``_period`` → ``_recordkey``
    → ``_key`` → ``_number`` → first column) to get deterministic rows.
    """
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            order_probes = [
                "_idrref", "_period", "_recordkey", "_datakey",
                "_key", "_number", "_lineno",
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
                    f"SELECT * FROM {table_name} ORDER BY {order_col} LIMIT :lim"
                )
            else:
                sql = text(f"SELECT * FROM {table_name} LIMIT :lim")

            result = conn.execute(sql, {"lim": limit})
            columns = list(result.keys())
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        engine.dispose()


def _decode_rtref_values(
    sample_rows: list[dict],
    context: dict,
) -> dict[str, dict]:
    """Scan sample rows for _rtref columns, decode first non-zero value.

    Only processes columns ending with ``_rtref`` (typed references).
    Returns {column_name: {table_suffix, table_name, tech_name, category}}.
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
) -> str:
    """Short printable summary of a cell value.

    For _rtref columns, decode and show the target table.
    For _type columns, show the type discriminator meaning.
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
            import uuid
            try:
                return str(uuid.UUID(bytes=raw))
            except Exception:
                pass
        return f"<{len(raw)} bytes>"
    s = str(val)
    if len(s) > 80:
        return s[:77] + "..."
    return s


def describe_object(
    db_url: str,
    uuid_str: str,
    sample_limit: int = 3,
) -> dict:
    """Build a full description dict for *uuid_str*.

    Returns dict with keys: uuid, tech_name, table_name, schema,
    column_descriptions, sample_data, blob.
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
        result["column_descriptions"] = _get_column_descriptions(
            schema, rtref_targets=rtref_targets,
        )

        # Format sample data
        formatted: list[dict[str, str]] = []
        for row in sample_rows:
            formatted.append(
                {
                    k: _summarise_value(v, col_name=k, rtref_targets=rtref_targets)
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
                            name = TYPE_DISCRIMINATOR_MAP.get(
                                byte_val, f"0x{byte_val:02X}"
                            )
                            type_info[col["column_name"]] = name
                            break
        if type_info:
            result["type_discriminators"] = type_info

    # Fetch blob
    try:
        blobs = fetch_blob(
            db_url, table="config", uuid=obj["uuid"], limit=1,
        )
        if blobs and blobs[0].get("content"):
            result["blob"] = blobs[0]["content"]
    except Exception:
        pass

    return result


def describe_text(
    db_url: str,
    uuid_str: str,
    sample_limit: int = 3,
) -> str:
    """Human-readable text description of a 1C metadata object."""
    info = describe_object(db_url, uuid_str, sample_limit=sample_limit)

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

    schema = info.get("schema")
    if schema:
        lines.append("")
        lines.append(f"--- Table schema ({table}) ---")
        col_desc = info.get("column_descriptions") or {}
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
            lines.append(f"  Row {i+1}:")
            for k, v in row.items():
                if k in ("_idrref",):
                    continue
                if v == "NULL":
                    continue
                lines.append(f"    {k:25s} = {v}")

    try:
        blobs = fetch_blob(
            db_url, table="config", uuid=info["uuid"], limit=1,
        )
        if blobs and blobs[0].get("content"):
            lines.append("")
            lines.append("--- Blob content (raw metadata) ---")
            content = blobs[0]["content"]
            lines.append(content[:6000])
    except Exception:
        pass

    return "\n".join(lines)
