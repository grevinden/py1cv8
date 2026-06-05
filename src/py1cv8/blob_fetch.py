"""Fetch and decompress a specific blob from config/configcas tables.

LLM uses this when it encounters an unknown type_num or wants to inspect
the raw binary metadata of a specific 1C object.
"""

from __future__ import annotations

import re
import struct
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from py1cv8.compress import decode_blob_chunk, try_decompress
from py1cv8.config import TYPE_MAP
from py1cv8.db import get_session
from py1cv8.metadata_binary import parse_metadata_blob
from py1cv8.models import Config, ConfigCas

BLOB_FORMAT_DESCRIPTION: str = """\
# 1C binary metadata blob format

Blobs in config/configcas store one or more serialized 1C metadata objects.
Format types:

## 1. Bracket format (most common)
  {1,{TYPE_NUM,{1,0,OBJECT_UUID},"TechName",{"ru","DisplayName",...},...}
  {1,0,OBJECT_UUID} — the object's own identity UUID
  "TechName" — technical name like "Справочник.Клиенты" or "Документ.Заказ"
  {"ru","DisplayName"} — localized display names (ru, en, uk)
  TYPE_NUM — integer 0-99 identifying the object category (see type_map)

## 2. MOXCEL format (alternative header)
  MOXCEL\\x00\\x08\\x00\\x01\\x00\\xNN\\x00 ...
  Bytes 11-12 contain TYPE_NUM as uint16 LE.
  The MOXCEL header may be followed by bracket format text.

## 3. BOM-split multi-blob
  The entire decompressed payload may contain multiple blobs
  separated by UTF-8 BOM markers (\\xef\\xbb\\xbf) or UTF-16 BOM markers
  (\\xff\\xfe). Each segment is a separate metadata object.
"""


def fetch_blob(
    db_url: str,
    table: str = "config",
    filename: str | None = None,
    partno: int | None = None,
    uuid: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search config/configcas for matching blobs, decompress, return as text.

    Parameters
    ----------
    db_url : str
        SQLAlchemy database URL.
    table : str
        ``"config"`` or ``"configcas"``.
    filename : str, optional
        SQL ``ILIKE`` pattern for the filename column.
    partno : int, optional
        Exact part number filter.
    uuid : str, optional
        UUID to search for in filename.
    limit : int
        Max rows to return.

    Returns
    -------
    list[dict]
        Each dict has keys: filename, partno, size, decompressed_size,
        content (raw text), parsed (structured fields or None),
        format_description (rules for interpreting the format).
    """
    parsed = urlparse(db_url)
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Database URL must include a path (database name): {db_url}")
    dbname = path.rsplit("/", 1)[-1]

    session = get_session(dbname)
    model_cls: Any
    if table == "config":
        model_cls = Config
    elif table == "configcas":
        model_cls = ConfigCas
    else:
        session.close()
        raise ValueError(f"Unknown table: {table!r}. Choose from: config, configcas")

    rows = _query(session, model_cls, uuid, filename, partno, limit)
    session.close()

    results: list[dict] = []
    for row in rows:
        raw = bytes(row["binarydata"]) if row.get("binarydata") else b""
        if not raw:
            results.append(
                {
                    "filename": row["filename"],
                    "partno": row["partno"],
                    "error": "empty blob",
                }
            )
            continue

        dec = try_decompress(raw)
        if not dec:
            results.append(
                {
                    "filename": row["filename"],
                    "partno": row["partno"],
                    "size": len(raw),
                    "error": "decompress failed",
                }
            )
            continue

        content = None
        type_num = None

        txt = decode_blob_chunk(dec) or dec.decode("utf-8", errors="replace").lstrip("\ufeff")
        m = re.search(r"\{1,\s*\r?\n?\{(\d+)", txt[:2000])
        if m:
            candidate = int(m.group(1))
            if 0 <= candidate <= 99:
                type_num = candidate
            content = txt[:10000]

        if dec[:6] == b"MOXCEL" and len(dec) >= 13:
            tn = struct.unpack("<H", dec[11:13])[0]
            if tn <= 99:
                type_num = tn
            after_header = dec[13:]
            txt2 = decode_blob_chunk(after_header) or after_header.decode(
                "utf-8", errors="replace"
            ).lstrip("\ufeff")
            if not content:
                content = txt2[:10000]

        if content is None:
            content = repr(dec[:500])

        # Parse structured fields from the bracket format
        parsed_info = parse_metadata_blob(content) if m else None
        category = TYPE_MAP.get(type_num, "Unknown") if type_num is not None else None

        results.append(
            {
                "filename": row["filename"],
                "partno": row["partno"],
                "size": len(raw),
                "decompressed_size": len(dec),
                "content": content if len(content) <= 10000 else content[:10000] + "...",
                "parsed": parsed_info,
                "category": category,
                "format_description": BLOB_FORMAT_DESCRIPTION,
            }
        )

    return results


def _query(
    session, model_cls, uuid, filename, partno, limit
):
    table_name = "config" if model_cls.__tablename__ == "config" else "configcas"

    conditions: list[str] = []
    params: dict = {}

    if uuid:
        conditions.append("CAST(filename AS text) ILIKE :pattern")
        params["pattern"] = f"%{uuid.lower()}%"
    elif filename:
        conditions.append("CAST(filename AS text) ILIKE :pattern")
        params["pattern"] = filename.replace("%", "%%")

    if partno is not None:
        conditions.append("partno = :partno")
        params["partno"] = partno

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    sql = text(
        f"SELECT * FROM {table_name} WHERE {where_clause} "
        f"ORDER BY filename, partno LIMIT {int(limit)}"
    )
    result = session.execute(sql, params)
    columns = list(result.keys())
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
