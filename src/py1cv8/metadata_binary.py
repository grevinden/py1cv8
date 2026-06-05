"""Binary metadata parser for 1C config/configcas blobs.

  - Parse {1,\n{type pattern from decompressed config blobs
  - Extract type_num from MOXCEL header
  - Build UUID -> metadata map from config table (via SQLAlchemy ORM)
"""

from __future__ import annotations

import re
import struct
from typing import Any

from sqlalchemy import select

from py1cv8.compress import decode_blob_chunk, try_decompress
from py1cv8.models import Config

# ── Metadata parser ────────────────────────────────────────────────────────


def parse_metadata_blob(txt: str) -> dict[str, Any] | None:
    """Extract type number and technical name from serialized config metadata.

    Expected pattern in text:
      {1, 0, UUID, "TechName", {...localized names}, ...}

    The UUID is the object's own UUID found in the {1,0,UUID} pattern,
    NOT the first UUID in the text (which is the type's UUID).

    Returns dict with 'type_num', 'tech_name', 'display_names', or None.
    """
    # Prefer UUID from {1,0,UUID} — the object's own identity
    obj_match = re.search(
        r"\{1,0,([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}",
        txt,
    )
    if obj_match:
        uuid_val = obj_match.group(1)
        after_uuid = txt[obj_match.end():]
    else:
        # Fallback: first UUID in text
        uuid_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            txt,
        )
        if not uuid_match:
            return None
        uuid_val = uuid_match.group(0)
        after_uuid = txt[uuid_match.end():]

    name_match = re.search(r'"([^"]{2,120})"', after_uuid)
    if not name_match:
        return None

    tech_name = name_match.group(1)

    generic_prefixes = (
        "ОбщийМодуль", "ОбщаяФорма", "ОбщийМакет", "ОбщаяКоманда",
        "Каталог", "Роль", "Подсистема", "Перечисление",
        "Константа", "Документ", "Отчет", "Обработка",
        "ВнешняяОбработка", "Справочник", "РегистрСведений",
        "РегистрНакопления", "РегистрБухгалтерии", "РегистрРасчета",
        "БизнесПроцесс", "Задача", "ПланОбмена", "ПланВидовХарактеристик",
        "ПланСчетов", "ПланВидовРасчета", "Последовательность",
        "КритерийОтбора", "Модуль", "Команда",
        "Расш1_",
    )
    if re.match(r"^(?:" + "|".join(generic_prefixes) + r")\d+$", tech_name):
        return None

    display_names: dict[str, str] = {}
    for dm in re.finditer(
        r'"(ru|en|uk)","([^"]{2,200})"', after_uuid,
    ):
        lang, val = dm.group(1), dm.group(2)
        if lang not in display_names:
            display_names[lang] = val

    type_num = None
    m = re.search(r"\{1,\s*\r?\n?\{(\d+)", txt)
    if m:
        candidate = int(m.group(1))
        if 0 <= candidate <= 99:
            type_num = candidate

    return {
        "uuid": uuid_val,
        "tech_name": tech_name,
        "display_names": display_names,
        "type_num": type_num,
    }


# ── Type from configcas blob header ────────────────────────────────────────


def extract_type_from_configcas_blob(dec: bytes) -> int | None:
    """Extract metadata type from configcas blob header."""
    if dec[:6] == b"MOXCEL" and len(dec) >= 13:
        tn = struct.unpack("<H", dec[11:13])[0]
        if tn <= 99:
            return tn

    m = re.search(rb"\{1,\s*\r?\n?\{(\d+)", dec[:2000])
    if m:
        tn = int(m.group(1))
        if tn <= 99:
            return tn

    return None


# ── Build metadata map from config table ───────────────────────────────────


def build_metadata_map(dbname: str) -> dict[str, dict]:
    """Read config table metadata blobs via ORM and build UUID -> info map.

    Calls get_session from db module directly (backward-compat).
    """
    from py1cv8.db import get_session
    session = get_session(dbname)
    try:
        q = select(Config).order_by(Config.partno)
        rows = session.scalars(q).all()
    finally:
        session.close()

    meta_map: dict[str, dict] = {}
    count = 0

    for row in rows:
        if not row.binarydata or row.partno is None:
            continue
        raw = bytes(row.binarydata)
        sz = len(raw)
        if sz < 20 or sz > 500_000:
            continue

        dec = try_decompress(raw)
        if not dec:
            continue

        if not re.search(rb"\{1,\s*\r?\n?\{(\d+)", dec[:2000]):
            continue

        txt = decode_blob_chunk(dec) or dec.decode("utf-8", errors="replace").lstrip("\ufeff")
        info = parse_metadata_blob(txt)
        if info and info.get("uuid"):
            uuid_val = info.get("uuid", "")
            assert isinstance(uuid_val, str)
            uuid_lower = uuid_val.lower()
            existing = meta_map.get(uuid_lower)
            if existing is None:
                meta_map[uuid_lower] = info
                count += 1
            elif existing.get("tech_name") == "" and info.get("tech_name"):
                meta_map[uuid_lower] = info

            fn_uuid_m = re.search(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                row.filename,
            )
            if fn_uuid_m:
                fn_uuid = fn_uuid_m.group(0).lower()
                if fn_uuid != uuid_lower:
                    existing_fn = meta_map.get(fn_uuid)
                    new_type_num = info.get("type_num")
                    if existing_fn is None:
                        meta_map[fn_uuid] = {
                            "uuid": fn_uuid,
                            "tech_name": "",
                            "display_names": {},
                            "type_num": new_type_num,
                        }
                    elif existing_fn.get("type_num") is None and new_type_num is not None:
                        existing_fn["type_num"] = new_type_num

    return meta_map



