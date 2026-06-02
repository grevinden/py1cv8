"""Tests for py1cv8 extract module."""
from __future__ import annotations

import os
import zlib

from py1cv8.extract import (
    _has_bsl_keywords,
    decode_blob_chunk,
    extract_code_blocks,
    extract_name_from_code,
    extract_type_from_configcas_blob,
    load_checkpoint,
    parse_metadata_blob,
    sanitize,
    save_checkpoint,
    try_decompress,
)

# ── try_decompress ──────────────────────────────────────────────────────────

def test_try_decompress_zlib_returns_data():
    original = b"Hello 1C World!"
    compressed = zlib.compress(original)
    result = try_decompress(compressed)
    assert result == original


def test_try_decompress_none_returns_none():
    assert try_decompress(b"") is None
    assert try_decompress(b"not compressed at all") is None


def test_try_decompress_short_data():
    assert try_decompress(b"ab") is None


# ── sanitize ────────────────────────────────────────────────────────────────

def test_sanitize_removes_windows_illegal():
    assert sanitize('file:name<test>|bad"') == "filenametestbad"


def test_sanitize_allows_cyrillic():
    assert sanitize("ирТест") == "ирТест"


def test_sanitize_truncates_long():
    long_name = "a" * 300
    assert len(sanitize(long_name)) <= 200


def test_sanitize_slashes():
    assert sanitize("a/b\\c") == "abc"


# ── _has_bsl_keywords ──────────────────────────────────────────────────────

def test_has_bsl_keywords_found():
    assert _has_bsl_keywords("Процедура Тест()") is True
    assert _has_bsl_keywords("Функция Вернуть()") is True
    assert _has_bsl_keywords("// comment") is True


def test_has_bsl_keywords_not_found():
    assert _has_bsl_keywords("Just some text without keywords") is False
    assert _has_bsl_keywords("Привет мир") is False


# ── decode_blob_chunk ───────────────────────────────────────────────────────

def test_decode_blob_chunk_utf8():
    chunk = "Процедура Тест()".encode()
    result = decode_blob_chunk(chunk)
    assert result is not None
    assert "Процедура" in result


def test_decode_blob_chunk_with_bom():
    chunk = "\ufeffПроцедура Выполнить()".encode("utf-8")
    result = decode_blob_chunk(chunk)
    assert result is not None
    assert "Процедура" in result


def test_decode_blob_chunk_too_short():
    assert decode_blob_chunk(b"ab") is None


# ── extract_code_blocks ─────────────────────────────────────────────────────

def test_extract_code_blocks_empty():
    result = extract_code_blocks(b"")
    assert result == []


def test_extract_code_blocks_single_block():
    code = "\ufeffПроцедура Тест()\n\tКонецПроцедуры".encode("utf-8")
    result = extract_code_blocks(code)
    assert len(result) >= 1
    assert "Процедура" in result[0]


def test_extract_code_blocks_multiple():
    code1 = "\ufeffПроцедура Первая()\nКонецПроцедуры".encode("utf-8")
    code2 = "\ufeffПроцедура Вторая()\nКонецПроцедуры".encode("utf-8")
    combined = code1 + code2
    result = extract_code_blocks(combined)
    assert len(result) >= 2


def test_extract_code_blocks_blocks_cleaned():
    """BSL block marker {3,...} should be stripped."""
    raw = "\ufeff{3,1,0,\"\",0}\nПроцедура Тест()\nКонецПроцедуры".encode("utf-8")
    result = extract_code_blocks(raw)
    assert len(result) >= 1
    assert "{3,1,0" not in result[0]


# ── parse_metadata_blob ─────────────────────────────────────────────────────

def test_parse_metadata_blob_dataprocessor():
    txt = '''{1,
{4,
{3,
{1,0,022c01a4-650e-44a0-a921-b5455e802e4c},"ирИсполняемыйЗапрос",
{3,"ru","Исполняемый запрос (ИР)","en","Executable query","uk","Виконуваний запит"}
},"",0,0,00000000-0000-0000-0000-000000000000,0},1,1,1,0,
{0},
{0},
{0},
{0},
{0,0},
{0,0},
{0,0},
{0,0},
{0,0},0,0,5,0,0,5,0,
{1,1},""}'''
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 4
    assert result["tech_name"] == "ирИсполняемыйЗапрос"
    assert result["display_names"].get("ru") == "Исполняемый запрос (ИР)"
    assert result["display_names"].get("en") == "Executable query"


def test_parse_metadata_blob_commontemplate():
    """CommonTemplate (type=12) with OPI name ending in digits."""
    txt = '''{1,
{12,
{3,
{1,0,496e68cd-c70d-4c15-aa9e-c2aad28abf8a},"OPI_Bitrix24",
{1,"ru","Bitrix24 (ОПИ)"},"",0,0,00000000-0000-0000-0000-000000000000,0},1,1,1,0,
{0},
{0},
{0},
{0},
{0,0},
{0,0},
{0,0},
{0,0},
{0,0},0,0,5,0,0,5,0,
{1,1},""}'''
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 12
    # "OPI_Bitrix24" ends with digits but should NOT be filtered out
    assert result["tech_name"] == "OPI_Bitrix24"
    assert result["display_names"].get("ru") == "Bitrix24 (ОПИ)"


def test_parse_metadata_blob_role():
    txt = (
        "{1,\n"
        "{6,\n"
        "{3,\n"
        '{1,0,0db37ea7-8c90-4575-876c-026b425b5c09},"ирПользователь",\n'
        '{3,"ru","Пользователь (ИР)","en","User (IR)"},'
        '"",0,0,00000000-0000-0000-0000-000000000000,0},1,1,""}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 6
    assert result["tech_name"] == "ирПользователь"


def test_parse_metadata_blob_generic_name_filtered():
    """Generic names like ОбщийМодуль1 should be filtered out."""
    txt = '''{1,
{2,4,
{3,
{1,0,uuid-test-0000-0000-0000-000000000000},"ОбщийМодуль1",
{3,"ru","Общий модуль 1"},"",0,0,""}
},"",0,0,00000000-0000-0000-0000-000000000000,0},""}'''
    result = parse_metadata_blob(txt)
    assert result is None  # filtered


def test_parse_metadata_blob_type57():
    """Type 57 (>25) should still be recognized."""
    txt = '''{1,
{57,
{3,
{1,0,cd070a4a-6274-4576-8cc1-f17696a76834},"ирАлгоритмы",
{3,"ru","Алгоритмы (ИР)"},"",0,0,00000000-0000-0000-0000-000000000000,0},1,1,""}'''
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 57
    assert result["tech_name"] == "ирАлгоритмы"


# ── extract_name_from_code ──────────────────────────────────────────────────

def test_extract_name_from_code_func_name():
    code = "Процедура МояФункция(Параметр) Экспорт\n\t// code\nКонецПроцедуры"
    name, _ = extract_name_from_code(code)
    assert name == "МояФункция"


def test_extract_name_from_code_onescript_ref():
    code = "// OneScript: ./path/Modules/МойМодуль.os\nПроцедура Тест()\nКонецПроцедуры"
    name, _ = extract_name_from_code(code)
    assert name == "МойМодуль"


def test_extract_name_from_code_no_match():
    code = "Just some plain text without any recognizable name patterns"
    name, _ = extract_name_from_code(code)
    assert name is None


# ── extract_type_from_configcas_blob ────────────────────────────────────────

def test_extract_type_moxcel():
    """MOXCEL header with type=12 at bytes 11-12 (LE)."""
    dec = b"MOXCEL\x00\x08\x00\x01\x00\x0c\x00"  # 0x0C = 12
    dec += b"{12,1,\"test\"}"
    result = extract_type_from_configcas_blob(dec)
    assert result == 12


def test_extract_type_moxcel_type8():
    """MOXCEL header with type=8."""
    dec = b"MOXCEL\x00\x08\x00\x01\x00\x08\x00"  # 0x08 = 8
    dec += b"{8,1,\"test\"}"
    result = extract_type_from_configcas_blob(dec)
    assert result == 8


def test_extract_type_braces_pattern():
    """{1,\n{type pattern."""
    dec = b"{1,\n{4,\n{3,\n{1,0,uuid},\"TestName\""
    result = extract_type_from_configcas_blob(dec)
    assert result == 4


def test_extract_type_returns_none():
    assert extract_type_from_configcas_blob(b"garbage data here") is None
    assert extract_type_from_configcas_blob(b"") is None


# ── load_checkpoint / save_checkpoint ───────────────────────────────────────

def test_checkpoint_no_file():
    """load_checkpoint returns empty set when no file exists."""
    path = r"B:\py1cv8\.extraction_checkpoint.json"
    if os.path.exists(path):
        os.remove(path)
    result = load_checkpoint()
    assert result == set()


def test_checkpoint_roundtrip():
    data = {"uuid-a1b2", "uuid-c3d4"}
    save_checkpoint(data)
    try:
        loaded = load_checkpoint()
        assert loaded == data
    finally:
        path = r"B:\py1cv8\.extraction_checkpoint.json"
        if os.path.exists(path):
            os.remove(path)
