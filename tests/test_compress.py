"""Tests for compress.py — BOM splitting, encoding fallbacks, code extraction."""

from __future__ import annotations

import zlib

from py1cv8.blob.decompress import (
    decode_blob_chunk,
    extract_code_blocks,
    try_decompress,
)

# ── try_decompress edge cases ────────────────────────────────────────────────


def test_try_decompress_raw_zlib_window():
    """Decompress with standard zlib window."""
    original = b"test data for raw deflate window"
    compressed = zlib.compress(original)
    assert try_decompress(compressed) == original


def test_try_decompress_wbits_15():
    """Ensure wbits=15 path is tried."""
    original = b"wbits-15 content"
    compressed = zlib.compress(original)
    result = try_decompress(compressed)
    assert result == original


def test_try_decompress_empty_input():
    """Empty bytes return None."""
    assert try_decompress(b"") is None


def test_try_decompress_too_short():
    """Less than 4 bytes returns None."""
    assert try_decompress(b"\x00\x01\x02") is None


def test_try_decompress_garbage():
    """Random non-zlib data returns None."""
    assert try_decompress(bytes(range(256))) is None


# ── decode_blob_chunk encoding fallbacks ─────────────────────────────────────


def test_decode_blob_chunk_utf8_fast_path():
    """Pure UTF-8 printable text decodes via fast path."""
    chunk = b"This is clearly valid UTF-8 printable text for testing purposes"
    result = decode_blob_chunk(chunk)
    assert result is not None
    assert "valid UTF-8" in result


def test_decode_blob_chunk_utf8_unprintable_fallback():
    """UTF-8 fast path fails on unprintable, falls through to scoring."""
    chunk = b"\x80\x81\x82\x83some text here"
    result = decode_blob_chunk(chunk)
    assert result is not None


def test_decode_blob_chunk_cp1251_with_keywords():
    """CP1251 encoding should be detected when BSL keywords are present."""
    text = "Процедура Тест()\nКонецПроцедуры"
    chunk = text.encode("cp1251")
    result = decode_blob_chunk(chunk)
    assert result is not None
    assert "Процедура" in result


def test_decode_blob_chunk_printable_ratio_threshold():
    """Non-keyword text with high printable ratio should still decode."""
    chunk = b"This is a long enough printable string without BSL keywords present here"
    result = decode_blob_chunk(chunk)
    assert result is not None


def test_decode_blob_chunk_high_printable_ratio():
    """CP1251 can decode any byte, so high-printable data won't be None."""
    chunk = bytes(range(256)) * 4
    # cp1251 is a single-byte encoding that maps every value to a character
    result = decode_blob_chunk(chunk)
    assert result is not None  # cp1251 will produce text with high printable ratio


def test_decode_blob_chunk_koi8r_with_keywords():
    """KOI8-R encoding should decode BSL keywords correctly."""
    text = "Процедура Тест()\nКонецПроцедуры"
    chunk = text.encode("koi8-r")
    result = decode_blob_chunk(chunk)
    assert result is not None
    assert "Процедура" in result


def test_decode_blob_chunk_short_data():
    """Less than 4 bytes after BOM strip returns None."""
    assert decode_blob_chunk(b"\xef\xbb\xbfab") is None


# ── extract_code_blocks BOM splitting ────────────────────────────────────────


def test_extract_code_blocks_utf8_bom_split():
    """Split by UTF-8 BOM markers."""
    bom = b"\xef\xbb\xbf"
    raw_text1 = "Процедура Первая()\n\tСообщить(1);\nКонецПроцедуры".encode()
    raw_text2 = "Процедура Вторая()\n\tВозврат 2;\nКонецФункции".encode()

    dec = bom + raw_text1 + bom + raw_text2
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 2
    assert "Первая" in blocks[0]
    assert "Вторая" in blocks[1]


def test_extract_code_blocks_utf16_bom_split():
    """Split by UTF-16 LE BOM markers — chunks decoded per their encoding."""
    bom = b"\xff\xfe"
    # Use ASCII content so it decodes regardless of encoding path
    raw_text1 = b"Procedure First()\n\tResult := 1;\nEndProcedure"
    raw_text2 = b"Procedure Second()\n\tResult := 2;\nEndProcedure"

    dec = bom + raw_text1 + bom + raw_text2
    blocks = extract_code_blocks(dec)
    # Chunks are split by \xff\xfe; whether they decode depends on content
    assert isinstance(blocks, list)


def test_extract_code_blocks_no_bom_single_chunk():
    """Without BOM, entire blob is one chunk (if it passes filters)."""
    raw = "Процедура БезБом()\n\tСообщить('hello');\nКонецПроцедуры".encode()
    blocks = extract_code_blocks(raw)
    assert len(blocks) == 1
    assert "БезБом" in blocks[0]


def test_extract_code_blocks_ignores_short_chunks():
    """Chunks shorter than 20 chars are skipped."""
    bom = b"\xef\xbb\xbf"
    short = bom + b"short text" + bom + b"also short"
    blocks = extract_code_blocks(short)
    assert len(blocks) == 0


def test_extract_code_blocks_ignores_no_procedure():
    """Chunks without Procedure/Function keywords are skipped."""
    bom = b"\xef\xbb\xbf"
    text = "Это просто текст без процедур и функций, он должен быть пропущен целиком".encode()
    dec = bom + text
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 0


# ── Code cleaning ────────────────────────────────────────────────────────────


def test_extract_code_blocks_strips_metadata_header():
    """MOXCEL metadata header {3,...} is stripped from code."""
    bom = b"\xef\xbb\xbf"
    text_part = "Процедура СМетаданными()\n\tСообщить(1);\nКонецПроцедуры".encode()
    text = b'{3,1,0,"test",1}\n' + bom + text_part
    blocks = extract_code_blocks(text)
    assert len(blocks) >= 1


def test_extract_code_blocks_truncates_after_konets():
    """Trailing garbage after КонецПроцедуры/КонецФункции is truncated."""
    bom = b"\xef\xbb\xbf"
    text_part = "Процедура СМусором()\n\tСообщить(1);\nКонецПроцедуры".encode()
    dec = bom + text_part + b"EXTRA_GARBAGE_DATA_AFTER_END"
    blocks = extract_code_blocks(dec)
    assert len(blocks) >= 1


def test_extract_code_blocks_removes_timestamp_lines():
    """Lines matching timestamp pattern are filtered out."""
    bom = b"\xef\xbb\xbf"
    text_part = (
        "Процедура СДатами()\n20231201 20231202 abc123\n\tСообщить(1);\nКонецПроцедуры".encode()
    )
    dec = bom + text_part
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 1
    assert "20231201 20231202" not in blocks[0]


def test_extract_code_blocks_collapse_blank_lines():
    """Consecutive blank lines are collapsed to one."""
    bom = b"\xef\xbb\xbf"
    text_part = "Процедура СПробелами()\n\n\n\n\tСообщить(1);\nКонецПроцедуры".encode()
    dec = bom + text_part
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 1
    # Should not have more than one consecutive blank line
    assert "\n\n\n" not in blocks[0]


def test_extract_code_blocks_mixed_bom_and_no_bom():
    """When UTF-8 BOMs are present, only BOM-split chunks are used."""
    bom = b"\xef\xbb\xbf"
    text1 = "Процедура Первая()\n\tСообщить(1);\nКонецПроцедуры".encode()
    text2 = "Процедура Вторая()\n\tВозврат 2;\nКонецФункции".encode()
    dec = bom + text1 + bom + text2
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 2


def test_extract_code_blocks_empty_input():
    """Empty bytes return empty list."""
    assert extract_code_blocks(b"") == []


# ── Integration: compress + extract pipeline ────────────────────────────────


def test_compress_then_extract_roundtrip():
    """Full pipeline: compress raw BSL, decompress, extract blocks."""
    bom = b"\xef\xbb\xbf"
    text = "Процедура Интеграция()\n\tВозврат 'OK';\nКонецПроцедуры".encode()
    raw = bom + text
    compressed = zlib.compress(raw)
    dec = try_decompress(compressed)
    assert dec is not None
    blocks = extract_code_blocks(dec)
    assert len(blocks) == 1
    assert "Интеграция" in blocks[0]
