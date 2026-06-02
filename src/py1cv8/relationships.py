"""Relationship graph builder for 1C database tables.

Analyzes columns for RRef/RTRef/Owner/Parent/Recorder references
and builds a table-level relationship graph.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py1cv8.dbnames import DBNamesEntry
    from py1cv8.schema import ObjectInfo, ServiceTableInfo


def build_relationships(
    tables: dict[str, ObjectInfo | ServiceTableInfo],
    dbnames_entries: list[DBNamesEntry],
    main_table_types: frozenset[str],
) -> dict[str, list[dict]]:
    """Analyze columns for inter-table references."""
    rels: dict[str, list[dict]] = {}

    for db_name, info in tables.items():
        if not _is_object(info):
            continue
        refs: list[dict] = []
        for col in info.columns:
            m = re.match(r"^(.+?)_(RRef|RTRef|Owner|Parent|Recorder|Folder)$", col.name)
            if m:
                prefix = m.group(1).lstrip("_")
                ref_type = m.group(2)
                target = _resolve_ref_target(prefix, dbnames_entries, main_table_types)
                refs.append({
                    "column": col.name,
                    "ref_type": ref_type,
                    "target_table": target or f"_{prefix}*",
                })
        if refs:
            rels[db_name] = refs

    return rels


def _is_object(info: object) -> bool:
    from py1cv8.schema import ObjectInfo
    return isinstance(info, ObjectInfo)


def _resolve_ref_target(
    prefix: str,
    dbnames_entries: list[DBNamesEntry],
    main_table_types: frozenset[str],
) -> str | None:
    """Resolve a column name prefix to a target table."""
    if prefix == "ID":
        return "_IDRRef (self)"

    m = re.match(r"ref?(\d+)", prefix, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        entry = next((
            e for e in dbnames_entries
            if e.number == num and e.type_name in main_table_types
        ), None)
        if entry:
            from py1cv8.dbnames import generate_db_name
            return generate_db_name(entry)

    return None
