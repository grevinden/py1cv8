"""DBNames parsing and table name generation.

Responsibilities:
  - Parse DBNames blob text into DBNamesEntry records
  - Generate database table names from DBNames entries
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from py1cv8.config import MAIN_TABLE_TYPES, SERVICE_TABLE_TYPES, SUB_TABLE_TYPES


@dataclass
class DBNamesEntry:
    uuid: str
    type_name: str
    number: int


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

    if tname in SERVICE_TABLE_TYPES:
        return f"_{tname.lower()}"

    return None
