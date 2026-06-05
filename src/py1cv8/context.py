"""LLM context generator — produces structured metadata for AI consumption.

Usage:
    from py1cv8.context import build_llm_context
    ctx = build_llm_context("postgresql+psycopg2://user:pass@host:5433/dbname")
    print(json.dumps(ctx, indent=2, ensure_ascii=False))
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select

from py1cv8.compress import decode_blob_chunk, try_decompress
from py1cv8.config import TYPE_MAP
from py1cv8.db import get_session
from py1cv8.dbnames import generate_db_name, parse_dbnames_text
from py1cv8.metadata_binary import build_metadata_map
from py1cv8.models import Params

DBNAMES_RULES: str = """\
# 1C Table naming conventions

Object type → table name pattern:
- Catalogs (Справочники)   → _Reference{N}
- Documents (Документы)    → _Document{N}
- InformationRegisters     → _InfoRg{N}
- AccumulationRegisters    → _AccRg{N}
- AccountingRegisters      → _CalcRg{N}
- ChartsOfCharacteristicTypes → _Chrc{N}
- Constants                → _Const{N}
- Enums (Перечисления)     → _Enum{N}
- BusinessProcesses        → _BusinessProcess{N}
- ExchangePlans            → _ExchangePlan{N}
- Sequences                → _Sequence{N}

Sub-table suffixes appended to the base name:
- _Fld{N}   — tabular section fields
- _VT{N}    — tabular section rows
- _LineNo{N}— line number sequences

Key columns:
- _IDRRef — primary UUID key for most tables
- _Code   — string code (catalogs)
- _Description — display name (catalogs, documents)
- _Date_Time — document date
- _Number — document number
- _Posted — document posted flag
- _DeletionMark — soft delete flag
- _FldXXX_RRef — reference (FK) to another table
- _FldXXX_RTRef — typed reference (type_num + UUID)
- _FldXXX_Owner — owner link (subordinate objects)
- _FldXXX_Parent — parent link (hierarchical objects)
- _FldXXX_Type — type discriminator (enum/type)

Rules:
- {N} is a sequential number assigned by 1C, varies per database
- N starts at 1 for the first object of its type
- To find the right table: SELECT table_name FROM information_schema.tables
  WHERE table_name LIKE '_Reference%' ORDER BY table_name
"""

RELATIONSHIP_RULES: str = """\
# 1C Reference field conventions

1. _IDRRef is the primary UUID key for all reference tables
2. _Fld{N}_RRef contains a UUID linking to _IDRRef of another table
3. _Fld{N}_RTRef contains a 16-byte value: first 4 bytes = type_num (LE),
   next 12 bytes may be UUID padding, rest may be type discriminator
4. _Fld{N}_Owner and _Fld{N}_Parent are special _RRef fields
5. Enum fields store the enum value directly (integer), not a UUID
6. Type fields (_Fld{N}_Type) store type_num bitmasks or enum ordinals

To resolve RRef links:
  SELECT _IDRRef FROM _Reference{N} WHERE ...  -- look up by UUID
"""

TYPE_MAP_DESCRIPTION: str = """\
# type_num → 1C object category

type_num is extracted from the binary config blob header (MOXCEL format).
It identifies the 1C metadata object category for serialization.
"""


def build_llm_context(db_url: str) -> dict:
    """Build LLM context from a live 1C database.

    Steps:
      1. Parse db_url -> (base_url, dbname)
      2. Read binary config blobs -> metadata object map
      3. Read DBNames from params table -> UUID -> table_name
      4. Compute DBNames for each discovered object
      5. Package everything as structured dict
    """
    parsed = urlparse(db_url)
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Database URL must include a path (database name): {db_url}")
    dbname = path.rsplit("/", 1)[-1]

    meta_map = build_metadata_map(dbname)

    # Read DBNames entries from params table for UUID -> table_name mapping
    dbnames_index: dict[str, str] = _read_dbnames_index(dbname)

    objects: list[dict] = []
    for uuid_val, info in meta_map.items():
        type_num = info.get("type_num")
        tech_name = info.get("tech_name", "")
        # Skip garbage entries — malformed tech_name from parser artifacts
        if not tech_name or tech_name in (",0}", "{2,") or tech_name.startswith(",0"):
            continue
        category = TYPE_MAP.get(type_num, "Unknown") if type_num is not None else "Unknown"
        table_name = dbnames_index.get(uuid_val)
        obj: dict = {
            "uuid": uuid_val,
            "tech_name": tech_name or None,
            "display_names": info.get("display_names", {}),
            "type_num": type_num,
            "category": category,
        }
        if table_name:
            obj["table_name"] = table_name
        objects.append(obj)

    return {
        "version": 1,
        "db_database": dbname,
        "object_count": len(objects),
        "objects": objects,
        "type_map": {str(k): v for k, v in sorted(TYPE_MAP.items())},
        "dbnames_rules": DBNAMES_RULES,
        "relationship_rules": RELATIONSHIP_RULES,
    }


def _read_dbnames_index(dbname: str) -> dict[str, str]:
    """Parse params table and return {uuid: table_name} mapping."""
    session = get_session(dbname)
    try:
        q = select(Params)
        rows = session.scalars(q).all()
    finally:
        session.close()

    index: dict[str, str] = {}
    for row in rows:
        if not row.binarydata:
            continue
        raw = bytes(row.binarydata)
        dec = try_decompress(raw)
        if not dec:
            continue
        txt = decode_blob_chunk(dec) or dec.decode("utf-8", errors="replace")
        entries = parse_dbnames_text(txt)
        for entry in entries:
            table_name = generate_db_name(entry)
            if table_name:
                index[entry.uuid] = table_name
    return index
