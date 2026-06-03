"""Relationship graph builder for 1C database tables.

Analyzes columns for RRef/RTRef/Owner/Parent/Recorder references
and builds a table-level relationship graph.

Satisfies: contracts.relationships.RelationshipBuilder
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py1cv8.dbnames import DBNamesEntry
    from py1cv8.schema import ObjectInfo, ServiceTableInfo

# Regex: standard pattern with _ separator (case-insensitive)
_STANDARD_REF_RE = re.compile(
    r"^(.+?)_(rref|rtref|rrref|owner|parent|recorder|folder)$",
    re.I,
)

# Map matched suffix to standard ref_type
_REF_TYPE_MAP: dict[str, str] = {
    "rref": "RRef",
    "rtref": "RTRef",
    "rrref": "RRef",
    "owner": "Owner",
    "parent": "Parent",
    "recorder": "Recorder",
    "folder": "Folder",
}

# Regex: _fldXXXrref (no underscore before rref)
_FLD_REF_RE = re.compile(r"^_fld(\d+)rref$", re.I)

# Regex: _fldXXX_rrref or _fldXXX_rtref (underscore before suffix)
_FLD_SUFFIX_RE = re.compile(r"^_fld(\d+)_(rrref|rtref)$", re.I)

# Regex: _owneridrref (Owner reference, lowercase — column name itself)
_OWNER_IDRREF_RE = re.compile(r"^_owneridrref$", re.I)

# Regex: _parentidrref, _folderidrref (column name itself)
_PARENT_FOLDER_IDRREF_RE = re.compile(r"^_(parent|folder)idrref$", re.I)


def build_relationships(
    tables: dict[str, ObjectInfo | ServiceTableInfo],
    dbnames_entries: list[DBNamesEntry],
    main_table_types: frozenset[str],
) -> dict[str, list[dict]]:
    """Analyze columns for inter-table references."""
    rels: dict[str, list[dict]] = {}

    uuid_to_entry: dict[str, DBNamesEntry] = {}
    for e in dbnames_entries:
        uuid_to_entry[e.uuid] = e

    for db_name, info in tables.items():
        refs: list[dict] = []
        for col in info.columns:
            ref_info = _match_reference_column(col.name)
            if ref_info is None:
                continue

            prefix, ref_type = ref_info
            target = _resolve_ref_target(
                prefix, dbnames_entries, main_table_types, uuid_to_entry,
            )
            refs.append({
                "column": col.name,
                "ref_type": ref_type,
                "target_table": target if target else "",
            })
        if refs:
            rels[db_name] = refs

    return rels


def _match_reference_column(col_name: str) -> tuple[str, str] | None:
    """Try all known reference column naming patterns.

    Returns (prefix, ref_type) or None if no pattern matches.
    """
    # 1) Standard pattern: XXX_RRef, XXX_Owner, etc. (case-insensitive)
    m = _STANDARD_REF_RE.match(col_name)
    if m:
        suffix = m.group(2).lower()
        return m.group(1).lstrip("_"), _REF_TYPE_MAP.get(suffix, suffix.capitalize())

    # 2) _fldXXXrref (field reference, no underscore before rref)
    m = _FLD_REF_RE.match(col_name)
    if m:
        return f"fld{m.group(1)}", "RRef"

    # 3) _fldXXX_rrref or _fldXXX_rtref
    m = _FLD_SUFFIX_RE.match(col_name)
    if m:
        suffix = m.group(2)
        ref_type = "RTRef" if suffix.lower() == "rtref" else "RRef"
        return f"fld{m.group(1)}", ref_type

    # 4) _owneridrref (exact match — column name IS the reference marker)
    m = _OWNER_IDRREF_RE.match(col_name)
    if m:
        return "owner", "Owner"

    # 5) _parentidrref, _folderidrref (exact match)
    m = _PARENT_FOLDER_IDRREF_RE.match(col_name)
    if m:
        return m.group(1).lower(), m.group(1).capitalize()

    return None


def _resolve_ref_target(
    prefix: str,
    dbnames_entries: list[DBNamesEntry],
    main_table_types: frozenset[str],
    uuid_to_entry: dict[str, DBNamesEntry],
) -> str | None:
    """Resolve a column name prefix to a target table."""
    if prefix in ("ID", "id"):
        return "_IDRRef (self)"

    # Special prefixes that can't be resolved from column name alone
    if prefix in ("owner", "parent", "folder"):
        return None

    # Try prefix as a reference number (RefN, refN, fldN)
    m = re.match(r"(?:ref|fld)(\d+)", prefix, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        entry = next((
            e for e in dbnames_entries
            if e.number == num and e.type_name in main_table_types
        ), None)
        if entry:
            from py1cv8.dbnames import generate_db_name
            return generate_db_name(entry)

    if len(prefix) == 36 and "-" in prefix:
        entry = uuid_to_entry.get(prefix)
        if entry and entry.type_name in main_table_types:
            from py1cv8.dbnames import generate_db_name
            return generate_db_name(entry)

    return None


# ── Class implementation (satisfies RelationshipBuilder contract) ─────────


class RelationshipBuilderImpl:
    """Builds inter-table reference graph for 1C databases.

    Satisfies: contracts.relationships.RelationshipBuilder
    """

    def build_relationships(
        self,
        tables: Mapping[str, object],
        entries: list[dict],
        main_types: frozenset[str],
    ) -> dict[str, list[dict]]:
        """Build {table_name: [relationship_dict, ...]}."""
        from py1cv8.dbnames import DBNamesEntry
        from py1cv8.schema import ObjectInfo, ServiceTableInfo

        typed_tables: dict[str, ObjectInfo | ServiceTableInfo] = {}
        for k, v in tables.items():
            if isinstance(v, (ObjectInfo, ServiceTableInfo)):
                typed_tables[k] = v

        parsed_entries: list[DBNamesEntry] = []
        for e in entries:
            if isinstance(e, DBNamesEntry):
                parsed_entries.append(e)
            elif isinstance(e, dict):
                parsed_entries.append(DBNamesEntry(
                    uuid=e.get("uuid", ""),
                    type_name=e.get("type_name", ""),
                    number=e.get("number", 0),
                ))

        return build_relationships(typed_tables, parsed_entries, main_types)
