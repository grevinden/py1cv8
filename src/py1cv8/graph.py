"""Relationship graph for 1C metadata objects.

Shows how objects reference each other using metadata-level names
instead of raw SQL column names.
"""

from __future__ import annotations

import re
import struct
from contextlib import suppress
from typing import Any

from sqlalchemy import create_engine, text

from py1cv8.blob_fetch import fetch_blob
from py1cv8.config import TYPE_DISCRIMINATOR_MAP
from py1cv8.context import build_llm_context
from py1cv8.db import is_postgres_url, quote_ident
from py1cv8.describe_object import _get_table_schema  # reuse schema discovery
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex


def _resolve_from_table_suffix(suffix: int, ctx: dict) -> dict | None:
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
    """Extract ordered field names from a metadata blob.

    Skips the first ``{1,0,OBJ_UUID},"Name"`` (the object itself).
    Returns subsequent field names in order.

    Tolerates optional whitespace between brace, comma and quotes.
    """
    matches = re.findall(
        r'\{1,0\s*,\s*[^}]+\}\s*,\s*"([^"]+)"',
        blob_content,
    )
    return matches[1:] if len(matches) > 1 else []


def _build_reference_columns(
    db_url: str,
    table_name: str,
    obj_uuid: str,
    field_names: list[str] | None = None,
) -> list[dict]:
    """Build list of reference columns with metadata field names.

    Maps ``_rref`` / ``_rtref`` columns to blob field names by
    positional order among reference columns.

    Parameters
    ----------
    field_names
        Pre-extracted field names from the blob (avoids double-fetch).
        If None, fetches and extracts from the blob.
    """
    schema_columns = _get_table_schema(db_url, table_name)

    if field_names is None:
        field_names = []
        try:
            blobs = fetch_blob(db_url, uuid=obj_uuid, limit=1)
            if blobs and blobs[0].get("content"):
                field_names = _extract_field_names(blobs[0]["content"])
        except Exception:
            pass

    rref_re = re.compile(r"_fld\d+rref$", re.IGNORECASE)
    rtref_re_col = re.compile(r"_fld\d+rtref$", re.IGNORECASE)

    ref_cols: list[dict] = []
    ref_index = 0
    for col in schema_columns:
        name = col["column_name"]
        if name.lower() == "_idrref":
            continue

        is_rref = bool(rref_re.match(name)) and not bool(rtref_re_col.match(name))
        is_rtref = bool(rtref_re_col.match(name))

        if not (is_rref or is_rtref):
            continue

        field_name = name
        if is_rref or is_rtref:
            field_name = (
                field_names[ref_index]
                if ref_index < len(field_names)
                else name
            )
            ref_index += 1

        ref_cols.append({
            "column": name,
            "field_name": field_name,
            "type": "rref" if is_rref else "rtref",
        })

    return ref_cols


def _has_owneridrref(db_url: str, table_name: str) -> bool:
    """Check if table has _owneridrref column."""
    schema = _get_table_schema(db_url, table_name)
    return any(c["column_name"].lower() == "_owneridrref" for c in schema)


def _has_parentidrref(db_url: str, table_name: str) -> bool:
    """Check if table has _parentidrref column."""
    schema = _get_table_schema(db_url, table_name)
    return any(c["column_name"].lower() == "_parentidrref" for c in schema)


def _find_type_columns(db_url: str, table_name: str) -> list[dict]:
    """Find _type columns and sample their values."""
    schema = _get_table_schema(db_url, table_name)
    type_cols = [
        c for c in schema
        if c["column_name"].endswith("_type")
    ]
    if not type_cols:
        return []

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            results: list[dict] = []
            for tc in type_cols:
                cn = tc["column_name"]
                qcn = quote_ident(cn, db_url)
                is_pg = is_postgres_url(db_url)
                if is_pg:
                    sql_snippet = f"encode({qcn}, 'hex')"
                else:
                    sql_snippet = f"LOWER(CONVERT(VARCHAR(MAX), {qcn}, 2))"
                raw = conn.execute(
                    text(
                        f"SELECT DISTINCT {sql_snippet} AS h"
                        f" FROM {quote_ident(table_name, db_url)}"
                        f" WHERE {qcn} IS NOT NULL AND length({qcn}) > 0"
                        f" LIMIT 5"
                    ),
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
                        decoded.append({
                            "hex": f"0x{v}",
                            "meaning": TYPE_DISCRIMINATOR_MAP.get(
                                b, f"Unknown type 0x{b:02X}"
                            ),
                        })
                    except ValueError:
                        decoded.append({"hex": v, "meaning": "unknown"})
                results.append({
                    "column": cn,
                    "values": decoded,
                })
            return results
    finally:
        engine.dispose()


def _resolve_uuid_against_tables(
    db_url: str,
    uuid_hex_std: str,
    ctx: dict,
) -> dict | None:
    """Try to find *uuid_hex_std* in _IDRRef of any known table.

    *uuid_hex_std* is a 32-char lowercase hex (standard format).
    _IDRRef in 1C stores standard UUID (NOT mixed-endian), so we
    search with both the standard hex and the mixed-endian variant
    as a fallback.
    """
    candidates = {uuid_hex_std}
    with suppress(Exception):
        candidates.add(_uuid_to_1c_idrref_hex(uuid_hex_std))
    is_pg = is_postgres_url(db_url)

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            for obj in ctx["objects"]:
                tn = obj.get("table_name")
                if not tn:
                    continue
                try:
                    qtn = quote_ident(tn, db_url)
                    qidr = quote_ident("_IDRRef", db_url)
                    if is_pg:
                        arg = ",".join(f"'{h}'" for h in candidates)
                        sql = text(
                            f"SELECT 1 FROM {qtn}"
                            f" WHERE encode({qidr}, 'hex') IN ({arg})"
                            f" LIMIT 1"
                        )
                    else:
                        arg = ",".join(f"'{h}'" for h in candidates)
                        sql = text(
                            f"SELECT 1 FROM {qtn}"
                            f" WHERE LOWER(CONVERT(VARCHAR(32), {qidr}, 2))"
                            f" IN ({arg}) LIMIT 1"
                        )
                    row = conn.execute(sql).fetchone()
                    if row:
                        return {
                            "table_name": tn,
                            "tech_name": obj.get("tech_name"),
                            "category": obj.get("category"),
                            "uuid": obj.get("uuid"),
                            "display_names": obj.get("display_names"),
                        }
                except Exception:
                    continue
    finally:
        engine.dispose()
    return None


def _find_reverse_rtref(
    db_url: str,
    table_suffix: int,
    ctx: dict,
) -> list[dict]:
    """Find objects that have _rtref columns pointing to *table_suffix*."""
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            is_pg = is_postgres_url(db_url)
            suffix_bytes = struct.pack(">I", table_suffix)
            suffix_hex = suffix_bytes.hex()

            results: list[dict] = []
            for obj in ctx["objects"]:
                tn = obj.get("table_name")
                if not tn:
                    continue
                try:
                    schema = _get_table_schema(db_url, tn)
                    rtref_cols = [
                        c["column_name"]
                        for c in schema
                        if re.match(r"_fld\d+rtref$", c["column_name"], re.IGNORECASE)
                    ]
                    if not rtref_cols:
                        continue

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
                        row = conn.execute(text(sql_text)).fetchone()
                        if row:
                            results.append({
                                "table_name": tn,
                                "tech_name": obj.get("tech_name"),
                                "uuid": obj.get("uuid"),
                                "category": obj.get("category"),
                                "column": rc,
                            })
                            break
                except Exception:
                    continue
    finally:
        engine.dispose()
    return results


def _sample_rref_uuids(
    db_url: str,
    table_name: str,
    field_names: list[str],
) -> list[dict]:
    """Scan _rref columns, sample IDs, try to resolve target tables."""
    schema_columns = _get_table_schema(db_url, table_name)
    rref_re = re.compile(r"_fld\d+rref$", re.IGNORECASE)
    rtref_re = re.compile(r"_fld\d+rtref$", re.IGNORECASE)
    ref_index = 0

    rref_cols = [
        c["column_name"]
        for c in schema_columns
        if bool(rref_re.match(c["column_name"]))
        and not bool(rtref_re.match(c["column_name"]))
    ]
    if not rref_cols:
        return []

    ctx = build_llm_context(db_url)
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            results: list[dict] = []
            for col_name in rref_cols:
                # Assign field name by positional order
                fn = (
                    field_names[ref_index]
                    if ref_index < len(field_names)
                    else col_name
                )
                ref_index += 1

                is_pg = is_postgres_url(db_url)
                qcol = quote_ident(col_name, db_url)
                if is_pg:
                    sql_snippet = f"encode({qcol}, 'hex')"
                else:
                    sql_snippet = f"LOWER(CONVERT(VARCHAR(MAX), {qcol}, 2))"

                zero_check = (
                    f" AND encode({qcol}, 'hex') != '00000000000000000000000000000000'"
                    if is_pg
                    else ""
                )
                raw = conn.execute(
                    text(
                        f"SELECT DISTINCT {sql_snippet} AS h"
                        f" FROM {quote_ident(table_name, db_url)}"
                        f" WHERE {qcol} IS NOT NULL"
                        f" AND length({qcol}) = 16"
                        f"{zero_check}"
                        f" LIMIT 4"
                    ),
                ).fetchall()

                sample_uuids: list[str] = []
                for row in raw:
                    if row[0] and isinstance(row[0], str):
                        h = row[0].strip().lower()
                        if len(h) == 32:
                            sample_uuids.append(h)

                target = None
                for su in sample_uuids[:1]:
                    target = _resolve_uuid_against_tables(db_url, su, ctx)
                    if target:
                        break

                results.append({
                    "column": col_name,
                    "field_name": fn,
                    "sample_uuids": sample_uuids,
                    "target": target,
                })
            return results
    finally:
        engine.dispose()


def _sample_rtref_targets(
    db_url: str,
    table_name: str,
    ctx: dict,
    field_names: list[str],
    sample_limit: int = 5,
) -> list[dict]:
    """Scan _rtref columns and discover target tables from first 4 bytes."""
    schema_columns = _get_table_schema(db_url, table_name)
    rtref_re = re.compile(r"_fld\d+rtref$", re.IGNORECASE)

    rtref_col_names = [
        c["column_name"]
        for c in schema_columns
        if bool(rtref_re.match(c["column_name"]))
    ]
    if not rtref_col_names:
        return []

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            is_pg = is_postgres_url(db_url)
            cols_sql = ", ".join(
                f"encode({quote_ident(c, db_url)}, 'hex') AS {quote_ident(c, db_url)}"
                if is_pg else quote_ident(c, db_url)
                for c in rtref_col_names
            )
            raw = conn.execute(
                text(
                    f"SELECT {cols_sql}"
                    f" FROM {quote_ident(table_name, db_url)}"
                    f" LIMIT :lim"
                ),
                {"lim": sample_limit},
            )

            refs: dict[tuple[str, int], int] = {}
            for row in raw.fetchall():
                for col_name, val in zip(rtref_col_names, row, strict=False):
                    if val is None:
                        continue
                    try:
                        raw_bytes = (
                            bytes.fromhex(val) if isinstance(val, str) else val
                        )
                        if len(raw_bytes) >= 4:
                            suffix = struct.unpack(">I", raw_bytes[:4])[0]
                            if suffix != 0:
                                key = (col_name, suffix)
                                refs[key] = refs.get(key, 0) + 1
                    except (ValueError, struct.error):
                        continue

            results: list[dict] = []
            for (col_name, suffix), count in sorted(
                refs.items(), key=lambda x: -x[1]
            ):
                fn = (
                    field_names[list(rtref_col_names).index(col_name)]
                    if col_name in rtref_col_names
                    and list(rtref_col_names).index(col_name) < len(field_names)
                    else col_name
                )
                target = _resolve_from_table_suffix(suffix, ctx)
                results.append({
                    "column": col_name,
                    "field_name": fn,
                    "table_suffix": suffix,
                    "sample_count": count,
                    "target": target,
                })
            return results
    finally:
        engine.dispose()


def build_graph(db_url: str, uuid_str: str) -> dict:
    """Build relationship graph for the metadata object identified by *uuid_str*.

    Resolves owners, parents, reference targets, type discriminators,
    and reverse references.

    Returns a JSON-serialisable dict.
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

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        # 1. Extract blob field names
        field_names: list[str] = []
        try:
            blobs = fetch_blob(db_url, uuid=obj_uuid, limit=1)
            if blobs and blobs[0].get("content"):
                field_names = _extract_field_names(blobs[0]["content"])
        except Exception:
            pass
        result["field_names"] = field_names

        # 2. Reference columns with metadata names
        ref_cols = _build_reference_columns(
            db_url, table_name, obj_uuid, field_names,
        )
        result["references"] = ref_cols

        # 3. _owneridrref — resolve owner
        if _has_owneridrref(db_url, table_name):
            with engine.connect() as conn:
                is_pg = is_postgres_url(db_url)
                qtn = quote_ident(table_name, db_url)
                qown = quote_ident("_owneridrref", db_url) if is_pg else "_owneridrref"
                if is_pg:
                    owner_row = conn.execute(
                        text(
                            f"SELECT DISTINCT encode({qown}, 'hex')"
                            f" FROM {qtn}"
                            f" WHERE {qown} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    ).fetchone()
                else:
                    owner_row = conn.execute(
                        text(
                            f"SELECT DISTINCT"
                            f" LOWER(CONVERT(VARCHAR(32), {qown}, 2))"
                            f" FROM {qtn}"
                            f" WHERE {qown} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    ).fetchone()

                if owner_row and owner_row[0]:
                    owner_hex = owner_row[0].strip()
                    owner_candidates = {owner_hex}
                    owner_candidates.add(_uuid_to_1c_idrref_hex(owner_hex))

                    owner_target = None
                    for tobj in ctx["objects"]:
                        ttn = tobj.get("table_name")
                        if not ttn:
                            continue
                        try:
                            arg = ",".join(f"'{h}'" for h in owner_candidates)
                            trow = conn.execute(
                                text(
                                    f"SELECT 1 FROM {ttn}"
                                    f" WHERE encode(_IDRRef, 'hex') IN ({arg})"
                                    f" LIMIT 1"
                                ),
                            ).fetchone()
                            if trow:
                                owner_target = {
                                    "table_name": ttn,
                                    "tech_name": tobj.get("tech_name"),
                                    "category": tobj.get("category"),
                                    "uuid": tobj.get("uuid"),
                                    "display_names": tobj.get("display_names"),
                                }
                                break
                        except Exception:
                            continue
                    result["owner"] = owner_target
                else:
                    result["owner"] = None
        else:
            result["owner"] = None

        # 4. _parentidrref — resolve parent
        if _has_parentidrref(db_url, table_name):
            with engine.connect() as conn:
                is_pg = is_postgres_url(db_url)
                qtn = quote_ident(table_name, db_url)
                qpar = quote_ident("_parentidrref", db_url) if is_pg else "_parentidrref"
                if is_pg:
                    parent_row = conn.execute(
                        text(
                            f"SELECT DISTINCT encode({qpar}, 'hex')"
                            f" FROM {qtn}"
                            f" WHERE {qpar} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    ).fetchone()
                else:
                    parent_row = conn.execute(
                        text(
                            f"SELECT DISTINCT"
                            f" LOWER(CONVERT(VARCHAR(32), {qpar}, 2))"
                            f" FROM {qtn}"
                            f" WHERE {qpar} IS NOT NULL"
                            f" LIMIT 1"
                        ),
                    ).fetchone()

                if parent_row and parent_row[0]:
                    parent_hex = parent_row[0].strip()
                    parent_candidates = {parent_hex}
                    parent_candidates.add(_uuid_to_1c_idrref_hex(parent_hex))

                    parent_target = None
                    for tobj in ctx["objects"]:
                        ttn = tobj.get("table_name")
                        if not ttn:
                            continue
                        try:
                            arg = ",".join(f"'{h}'" for h in parent_candidates)
                            trow = conn.execute(
                                text(
                                    f"SELECT 1 FROM {ttn}"
                                    f" WHERE encode(_IDRRef, 'hex') IN ({arg})"
                                    f" LIMIT 1"
                                ),
                            ).fetchone()
                            if trow:
                                parent_target = {
                                    "table_name": ttn,
                                    "tech_name": tobj.get("tech_name"),
                                    "category": tobj.get("category"),
                                    "uuid": tobj.get("uuid"),
                                    "display_names": tobj.get("display_names"),
                                }
                                break
                        except Exception:
                            continue
                    result["parent"] = parent_target
                else:
                    result["parent"] = None
        else:
            result["parent"] = None

        # 5. RTRef targets (typed references) — forward
        rtref_results = _sample_rtref_targets(
            db_url, table_name, ctx, field_names,
        )
        if rtref_results:
            result["rtref_targets"] = rtref_results

        # 6. RRef UUID resolution
        rref_results = _sample_rref_uuids(db_url, table_name, field_names)
        if rref_results:
            result["rref_targets"] = rref_results

        # 7. Type discriminators
        type_info = _find_type_columns(db_url, table_name)
        if type_info:
            result["type_discriminators"] = type_info

        # 8. Reverse _rtref references
        table_suffix = None
        m = re.search(r"_(\d+)$", table_name)
        if m:
            table_suffix = int(m.group(1))
            reverse_refs = _find_reverse_rtref(db_url, table_suffix, ctx)
            if reverse_refs:
                result["reverse_rtref"] = reverse_refs

    finally:
        engine.dispose()

    return result


def graph_text(db_url: str, uuid_str: str) -> str:
    """Human-readable text representation of the relationship graph."""
    info = build_graph(db_url, uuid_str)

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
            lines.append(f"  «{fn}»  ({col})  [{rtype}]")

            # Show resolved rref target
            if rtype == "rref":
                for rr in rref_targets:
                    if rr["column"] == col:
                        tgt = rr.get("target")
                        if tgt:
                            lines.append(
                                f"         ↳ {tgt['tech_name']} ({tgt['table_name']})"
                            )
                        elif rr.get("sample_uuids"):
                            lines.append(
                                f"         ↳ UUID: {rr['sample_uuids'][0]} (таблица не определена)"
                            )
                        break

            # Show resolved rtref target
            if rtype == "rtref":
                for rr in rtref_targets:
                    if rr["column"] == col:
                        tgt = rr.get("target")
                        if tgt:
                            lines.append(
                                f"         ↳ {tgt['tech_name']} ({tgt['table_name']})"
                            )
                        else:
                            lines.append(
                                f"         ↳ table suffix #{rr.get('table_suffix', '?')}"
                            )
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
                meanings = ", ".join(
                    v["meaning"] or v["hex"] for v in vals
                )
                lines.append(f"  {col} → {meanings}")

    # Reverse references
    reverse = info.get("reverse_rtref")
    if reverse:
        lines.append("")
        lines.append("── Обратные ссылки (на этот объект) ──")
        for rv in reverse:
            lines.append(
                f"  {rv['tech_name']} → {rv['column']} ({rv['table_name']})"
            )

    return "\n".join(lines)
