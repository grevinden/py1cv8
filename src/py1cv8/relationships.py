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
            m = re.match(r"^(.+?)_(RRef|RTRef|Owner|Parent|Recorder|Folder)$", col.name)
            if m:
                prefix = m.group(1).lstrip("_")
                ref_type = m.group(2)
                target = _resolve_ref_target(
                    prefix, dbnames_entries, main_table_types, uuid_to_entry,
                )
                refs.append({
                    "column": col.name,
                    "ref_type": ref_type,
                    "target_table": target or f"_{prefix}*",
                })
        if refs:
            rels[db_name] = refs

    return rels


def _resolve_ref_target(
    prefix: str,
    dbnames_entries: list[DBNamesEntry],
    main_table_types: frozenset[str],
    uuid_to_entry: dict[str, DBNamesEntry],
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
