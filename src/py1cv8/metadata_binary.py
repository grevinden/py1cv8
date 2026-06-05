"""Парсер бинарных метаданных 1С из блобов config/configcas.

Модуль отвечает за извлечение структурированной информации из бинарных
блобов конфигурации 1С:Enterprise. Поддерживает два формата — классический
паттерн ``{1,\n{type`` и MOXCEL-заголовок. Предоставляет функции для
синтаксического разбора отдельных блобов, извлечения type_num из заголовка
configcas, а также построения полной карты UUID -> метаданные на основе
таблицы config через SQLAlchemy ORM.
"""

from __future__ import annotations

import re
import struct
from typing import Any

from sqlalchemy import select

from py1cv8.blob.decompress import decode_blob_chunk, try_decompress
from py1cv8.sql.orm.models import Config, ConfigCas

# ── Type map: type_num → category (from 1C binary config blobs) ────────────
#
# WARNING: type_num (0-99) is NOT globally consistent across 1C configurations.
# The 1C platform assigns type_num per serialization format, which can vary
# between databases. This mapping is valid for the MessageCenter DB.
# For the test DB, see data/v8unpack_metadata_types.json (type_num_reference).
#
# These are BROAD categories for BSL extraction output folders, NOT 1C type IDs.

TYPE_MAP: dict[int, str] = {
    0: "CommonForms",
    1: "DataProcessors",
    2: "CommonModules",
    3: "Subsystems",
    4: "DataProcessors",
    5: "CommonAttributes",
    6: "Roles",
    7: "Roles",
    8: "Ext",
    9: "Reports",
    12: "CommonTemplates",
    13: "OtherTypes",
    14: "OtherTypes",
    16: "Constants",
    17: "DataProcessors",
    19: "DataProcessors",
    20: "Enums",
    22: "Documents",
    26: "DocumentJournals",
    30: "OtherTypes",
    33: "InformationRegisters",
    34: "ChartsOfCharacteristicTypes",
    37: "OtherTypes",
    40: "Documents",
    57: "Catalogs",
    68: "Ext",
}

# ── Metadata parser ────────────────────────────────────────────────────────


def parse_metadata_blob(txt: str) -> dict[str, Any] | None:
    """Извлечение type_num, технического имени и отображаемых имён из
    текстового представления сериализованного блоба метаданных 1С.

    Ожидаемый паттерн во входном тексте::

        {1, 0, UUID, "TechName", {...localized names}, ...}

    UUID извлекается в первую очередь из паттерна ``{1,0,UUID}``
    — это собственный UUID объекта метаданных. Если такой паттерн
    не найден, используется первый UUID в тексте (но это может
    быть UUID типа, а не объекта).

    Техническое имя (tech_name) — это строка в кавычках, следующая
    сразу за UUID. Имена, соответствующие шаблонам ``ОбщийМодуль123``,
    ``Справочник456`` и т.п., отбрасываются как сгенерированные
    автоматически.

    Отображаемые имена извлекаются для языков ``ru``, ``en``, ``uk``.

    Args:
        txt: Текстовое содержимое декомпрессированного блоба метаданных.

    Returns:
        Словарь с ключами ``uuid``, ``tech_name``, ``display_names``,
        ``type_num`` или None, если разбор не удался.
    """
    # Prefer UUID from {1,0,UUID} — the object's own identity
    obj_match = re.search(
        r"\{1,0,([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\}",
        txt,
    )
    if obj_match:
        uuid_val = obj_match.group(1)
        after_uuid = txt[obj_match.end() :]
    else:
        # Fallback: first UUID in text
        uuid_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            txt,
        )
        if not uuid_match:
            return None
        uuid_val = uuid_match.group(0)
        after_uuid = txt[uuid_match.end() :]

    name_match = re.search(r'"([^"]{2,120})"', after_uuid)
    if not name_match:
        return None

    tech_name = name_match.group(1)

    generic_prefixes = (
        "ОбщийМодуль",
        "ОбщаяФорма",
        "ОбщийМакет",
        "ОбщаяКоманда",
        "Каталог",
        "Роль",
        "Подсистема",
        "Перечисление",
        "Константа",
        "Документ",
        "Отчет",
        "Обработка",
        "ВнешняяОбработка",
        "Справочник",
        "РегистрСведений",
        "РегистрНакопления",
        "РегистрБухгалтерии",
        "РегистрРасчета",
        "БизнесПроцесс",
        "Задача",
        "ПланОбмена",
        "ПланВидовХарактеристик",
        "ПланСчетов",
        "ПланВидовРасчета",
        "Последовательность",
        "КритерийОтбора",
        "Модуль",
        "Команда",
        "Расш1_",
    )
    if re.match(r"^(?:" + "|".join(generic_prefixes) + r")\d+$", tech_name):
        return None

    display_names: dict[str, str] = {}
    for dm in re.finditer(
        r'"(ru|en|uk)","([^"]{2,200})"',
        after_uuid,
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
    """Извлечение type_num из бинарного заголовка configcas-блоба.

    Поддерживает два формата:
      1. MOXCEL-заголовок: байты ``MOXCEL\\x00\\x08\\x00\\x01\\x00\\xNN\\x00``,
         где uint16 LE на позиции 11-12 содержит type_num.
      2. Текстовый паттерн ``{1,\\n{N`` в первых 2000 байтах,
         где N — число 0-99.

    Args:
        dec: Декомпрессированные бинарные данные блоба.

    Returns:
        Числовой type_num (0-99) или None, если определить не удалось.
    """
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


def build_metadata_map(
    dbname: str,
    table: str = "config",
) -> dict[str, dict]:
    """Read config table metadata blobs via ORM and build UUID -> info map.

    Parameters
    ----------
    dbname : str
        Имя базы данных.
    table : str
        Таблица-источник: ``"config"`` (текущая), ``"configcas"`` (кэш),
        ``"configsave"`` (предыдущая версия).
    """
    from py1cv8.db import get_session

    _table_model: dict[str, type[Any]] = {
        "config": Config,
        "configcas": ConfigCas,
        "configsave": ConfigCas,  # та же структура
    }
    model_cls = _table_model.get(table)
    if model_cls is None:
        msg = f"Unknown table: {table!r}. Choose from: config, configcas, configsave"
        raise ValueError(msg)

    session = get_session(dbname)
    try:
        q = select(model_cls).order_by(model_cls.partno)
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
