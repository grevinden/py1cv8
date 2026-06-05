"""Извлечение и распаковка блобов из таблиц config/configcas базы данных 1С.

Таблицы **config** и **configcas** — это системные таблицы PostgreSQL, в которых
1С:Предприятие хранит бинарные блобы метаданных конфигурации. Каждая строка содержит:

- ``filename`` — идентификатор записи (часто содержит UUID объекта)
- ``partno`` — номер части (один объект может занимать несколько частей)
- ``binarydata`` — zlib-сжатый двоичный блоб с сериализованными метаданными

**config** — основная таблица конфигурации. Используется по умолчанию.
**configcas** — дополнительная таблица (configuration case-sensitive). Содержит
дубли/варианты для case-sensitive режимов. Обычно нужна только когда объект не
найден в config.

ORM-слой вынесен в ``py1cv8.sql.orm``. Этот модуль занимается **только**
декомпрессией и парсингом блобов.
"""

from __future__ import annotations

import re
import struct

from py1cv8.blob.decompress import decode_blob_chunk, try_decompress
from py1cv8.metadata_binary import TYPE_MAP, parse_metadata_blob
from py1cv8.sql.orm import ConfigTable, select_config_rows

BLOB_FORMAT_DESCRIPTION: str = """\
# 1C binary metadata blob format

Each row of the PostgreSQL tables **config** / **configcas** contains a zlib-compressed
blob with one or more serialized 1C metadata objects. Table ``config`` is the primary
storage; ``configcas`` holds case-sensitive variants.
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


async def extract_metadata_blobs(
    db_url: str,
    *,
    table: ConfigTable = "config",
    filename: str | None = None,
    partno: int | None = None,
    uuid: str | None = None,
    limit: int = 20,
    raw: bool = False,
) -> list[dict]:
    """Извлечь блобы из config/configcas, декомпрессировать и вернуть текстом.

    Ищет совпадающие строки по UUID / имени файла / номеру части,
    распаковывает zlib-данные и парсит метаданные 1С.

    Параметры
    ----------
    db_url : str
        URL подключения к БД (SQLAlchemy).
    table : str
        Таблица PostgreSQL для поиска:

        - ``"config"`` — основная таблица метаданных 1С (используется по умолчанию).
          Здесь хранится подавляющее большинство объектов.
        - ``"configcas"`` — дополнительная таблица для case-sensitive режимов.
          Проверяйте её, если объект не найден в ``config``.
    filename : str, optional
        Паттерн SQL ``ILIKE`` для фильтрации по имени файла.
    partno : int, optional
        Точный номер части (partno).
    uuid : str, optional
        UUID для поиска в имени файла.
    limit : int
        Максимальное количество возвращаемых строк.
    raw : bool
        Включить распакованное содержимое в результат. По умолчанию ``False``.
        Ставьте ``True``, когда нужен полный текст блоба (describe/graph).

    Возвращает
    -------
    list[dict]
        Словарь с ключами: filename, partno, size, decompressed_size,
        parsed (структурированные поля или None), category (название из TYPE_MAP).
        При ``raw=True`` дополнительно возвращается ``content``.
    """

    # ORM-слой: выборка сырых строк из БД
    rows = await select_config_rows(
        db_url=db_url,
        table=table,
        uuid=uuid,
        filename=filename,
        partno=partno,
        limit=limit,
    )

    # Парсинг/декомпрессия: обработка каждого блоба в памяти
    results: list[dict] = []
    for row in rows:
        blob_data = row["binarydata"]
        if not blob_data:
            results.append(
                {
                    "filename": row["filename"],
                    "partno": row["partno"],
                    "error": "empty blob",
                }
            )
            continue

        dec = try_decompress(blob_data)
        if not dec:
            results.append(
                {
                    "filename": row["filename"],
                    "partno": row["partno"],
                    "size": len(blob_data),
                    "error": "decompress failed",
                }
            )
            continue

        type_num = None
        parsed_info = None
        content_text: str | None = None

        txt = decode_blob_chunk(dec) or dec.decode("utf-8", errors="replace").lstrip("\ufeff")
        m = re.search(r"\{1,\s*\r?\n?\{(\d+)", txt[:5000])
        if m:
            candidate = int(m.group(1))
            if 0 <= candidate <= 99:
                type_num = candidate

        # Parse structured fields (always — cheap)
        if m:
            parsed_info = parse_metadata_blob(txt[:50000])

        # MOXCEL header detection (only need for type_num if bracket not found)
        if dec[:6] == b"MOXCEL" and len(dec) >= 13:
            tn = struct.unpack("<H", dec[11:13])[0]
            if tn <= 99:
                type_num = tn

        # Build result without content by default
        item: dict = {
            "filename": row["filename"],
            "partno": row["partno"],
            "size": len(blob_data),
            "decompressed_size": len(dec),
            "parsed": parsed_info,
            "category": (TYPE_MAP.get(type_num, "Unknown") if type_num is not None else None),
        }

        # Include raw content only when requested
        if raw:
            if m and parsed_info is not None:
                content_text = txt[:50000]
            elif dec[:6] == b"MOXCEL":
                after_header = dec[13:]
                content_text = (
                    decode_blob_chunk(after_header)
                    or after_header.decode("utf-8", errors="replace").lstrip("\ufeff")
                )[:50000]
            else:
                content_text = repr(dec[:500])
            item["content"] = (
                content_text if len(content_text) <= 50000 else content_text[:50000] + "..."
            )

        results.append(item)

    return results


# — асинхронный алиас —
fetch_blob = extract_metadata_blobs
