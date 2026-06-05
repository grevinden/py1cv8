"""Распаковка и декодирование бинарных блобов 1С.

Содержит чистые функции (без I/O) для:
  - zlib-декомпрессии с разными размерами окна
  - Детекции кодировки и декодирования текста (chardet + fallback)
  - Разделения по BOM-маркерам
  - Извлечения и очистки блоков BSL-кода
"""

from __future__ import annotations

import re
import zlib

from charset_normalizer import from_bytes

# ── Decompression ──────────────────────────────────────────────────────────


def try_decompress(data: bytes) -> bytes | None:
    """Попробовать zlib-декомпрессию с распространёнными размерами окна.

    Args:
        data: Сжатые бинарные данные.

    Returns:
        Распакованные байты или None, если декомпрессия не удалась.
    """
    if not data or len(data) < 4:
        return None
    for w in (-15, 15):
        try:
            return zlib.decompress(data, w)
        except Exception:
            pass
    return None


# ── Encoding detection ─────────────────────────────────────────────────────

ENCODING_ORDER: tuple[str, ...] = (
    "utf-8",
    "utf-16-le",
    "utf-16-be",
    "cp1251",
    "koi8-r",
    "koi8-u",
    "windows-1251",
)


def decode_blob_chunk(chunk: bytes) -> str | None:
    """Декодировать бинарный чанк в текст через chardet + скоринг.

    Args:
        chunk: Бинарные данные (один блоб или BOM-раздел).

    Returns:
        Декодированный текст или None, если данные слишком короткие.
    """
    data = chunk.lstrip(b"\xef\xbb\xbf")
    if len(data) < 4:
        return None

    result = from_bytes(data[:10000]).best()
    hint_enc = result.encoding if result else None
    hint_conf = 1.0 if result else 0

    if hint_conf > 0.5 and hint_enc:
        enc_order = (hint_enc.lower(),) + ENCODING_ORDER
    else:
        enc_order = ENCODING_ORDER

    # Fast path: UTF-8
    try:
        txt = data.decode("utf-8")
        if "\ufffd" not in txt and any(c.isprintable() or c.isspace() for c in txt[:100]):
            return txt
    except UnicodeDecodeError:
        pass

    best_txt = None
    best_has_keywords = False

    from py1cv8.bsl import has_bsl_keywords

    for enc in enc_order:
        if enc == "utf-8":
            continue
        try:
            txt = data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue

        has_kw = has_bsl_keywords(txt)
        if has_kw and not best_has_keywords:
            best_txt = txt
            best_has_keywords = True
        elif not best_txt:
            printable_ratio = sum(1 for c in txt[:500] if c.isprintable() or c.isspace()) / max(
                len(txt[:500]), 1
            )
            if printable_ratio > 0.85:
                best_txt = txt

    return best_txt


# ── BSL code block extraction ──────────────────────────────────────────────


def extract_code_blocks(dec: bytes) -> list[str]:
    """Разделить распакованный блоб на блоки BSL-кода по BOM-маркерам.

    Args:
        dec: Распакованные бинарные данные блоба.

    Returns:
        Список строк с фрагментами BSL-кода.
    """
    bom_positions = [m.start() for m in re.finditer(b"\xef\xbb\xbf", dec)]
    utf16_bom_positions = [m.start() for m in re.finditer(b"\xff\xfe", dec)]

    chunks: list[bytes] = []
    if bom_positions:
        for i, pos in enumerate(bom_positions):
            end = bom_positions[i + 1] if i + 1 < len(bom_positions) else len(dec)
            chunks.append(dec[pos:end])
    elif utf16_bom_positions:
        for i, pos in enumerate(utf16_bom_positions):
            end = utf16_bom_positions[i + 1] if i + 1 < len(utf16_bom_positions) else len(dec)
            chunks.append(dec[pos:end])
    else:
        chunks = [dec]

    blocks: list[str] = []
    for chunk in chunks:
        block = decode_blob_chunk(chunk)
        if not block or len(block.strip()) < 20:
            continue

        has_code = any(
            kw in block
            for kw in (
                "Перем",
                "Процедура ",
                "Функция ",
                "КонецПроцедуры",
                "КонецФункции",
            )
        )
        if not has_code or len(block.strip()) < 20:
            continue

        code = re.sub(r"^\{3,\d+,\d+,\"[^\"]*\",\d+\}\s*", "", block)
        code = re.sub(r"\s*\{3,\d+,\d+,\"[^\"]*\",\d+\}$", "", code)

        for kw in ("КонецПроцедуры", "КонецФункции"):
            idx = code.rfind(kw)
            if idx >= 0:
                after = code[idx + len(kw) :].strip()
                if after and not after.startswith("\n"):
                    code = code[: idx + len(kw)]

        lines = []
        prev_blank = False
        for line in code.splitlines():
            stripped = line.strip()
            if stripped and re.match(r"^\d{8}\s+\d{8}\s+[0-9a-f]+", stripped):
                continue
            is_blank = len(stripped) == 0
            if is_blank and prev_blank:
                continue
            lines.append(line.rstrip())
            prev_blank = is_blank

        text = "\n".join(lines).strip()
        if len(text) >= 10:
            blocks.append(text)

    return blocks
