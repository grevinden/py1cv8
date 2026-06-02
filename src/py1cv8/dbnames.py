"""DBNames parsing and table name generation.

Responsibilities:
  - Parse DBNames blob text into DBNamesEntry records
  - Generate database table names from DBNames entries
  - Classify entries as main/sub/service/companion

Satisfies: contracts.dbnames.DBNamesProvider
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from py1cv8.config import (
    COMPANION_TABLE_PARENT,
    COMPANION_TABLE_TYPES,
    MAIN_TABLE_TYPES,
    SERVICE_TABLE_TYPES,
    SUB_TABLE_PARENT,
    SUB_TABLE_TYPES,
)


@dataclass
class DBNamesEntry:
    uuid: str
    type_name: str
    number: int

    @property
    def category(self) -> str:
        """Classify this entry as 'main', 'sub', 'companion', or 'service'."""
        if self.type_name in SUB_TABLE_TYPES:
            return "sub"
        if self.type_name in COMPANION_TABLE_TYPES:
            return "companion"
        if (
            self.type_name in SERVICE_TABLE_TYPES
            or self.uuid == "00000000-0000-0000-0000-000000000000"
        ):
            return "service"
        return "main"


def parse_dbnames_text(text: str) -> list[DBNamesEntry]:
    """Parse decompressed DBNames text into entries."""
    entries: list[DBNamesEntry] = []
    for m in re.finditer(
        r"\{([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}),"
        r'"([^"]+)",(\d+)\}',
        text,
    ):
        entries.append(DBNamesEntry(
            uuid=m.group(1).lower(),
            type_name=m.group(2),
            number=int(m.group(3)),
        ))
    return entries


def generate_db_name(entry: DBNamesEntry, parent_db_name: str | None = None) -> str | None:
    """Generate the expected database table name from a DBNames entry."""
    tname = entry.type_name
    num = entry.number

    if tname in MAIN_TABLE_TYPES:
        return f"_{tname.lower()}{num}"

    if tname in SUB_TABLE_TYPES:
        if parent_db_name:
            return f"{parent_db_name}_{tname.lower()}{num}"
        return None

    if tname in COMPANION_TABLE_TYPES:
        return f"_{tname.lower()}{num}"

    if tname in SERVICE_TABLE_TYPES:
        return f"_{tname.lower()}"

    return None


def get_parent_type(tname: str, category: str) -> str | None:
    """Resolve parent DBNames type_name for sub/companion tables."""
    if tname in SUB_TABLE_PARENT:
        return SUB_TABLE_PARENT[tname]
    if tname in COMPANION_TABLE_PARENT:
        return COMPANION_TABLE_PARENT[tname]
    return None


# ── Class implementation (satisfies DBNamesProvider contract) ─────────────


class DBNamesProviderImpl:
    """Parses _DBNames__ system table and generates SQL table names.

    Satisfies: contracts.dbnames.DBNamesProvider
    """

    @staticmethod
    def parse_dbnames_text(text: str) -> list[dict]:
        """Parse raw _DBNames__ table content into structured entries.

        Returns list of dicts with keys: uuid, type_name, number, category, db_name.
        """
        entries = parse_dbnames_text(text)
        return [
            {
                "uuid": e.uuid,
                "type_name": e.type_name,
                "number": e.number,
                "category": e.category,
                "db_name": generate_db_name(e) or "",
            }
            for e in entries
        ]

    @staticmethod
    def generate_db_name(
        entry: dict,
        parent_db_name: str | None = None,
    ) -> str | None:
        """Generate SQL table name for a DBNames entry dict."""
        tname = entry.get("type_name", "")
        num = entry.get("number", 0)
        return generate_db_name(DBNamesEntry(
            uuid=entry.get("uuid", ""),
            type_name=tname,
            number=num,
        ), parent_db_name)
