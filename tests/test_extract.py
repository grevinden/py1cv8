"""Tests for py1cv8 core modules (decompress, decode, metadata, bsl, resolve)."""

from __future__ import annotations

import zlib

from py1cv8.blob.decompress import decode_blob_chunk, try_decompress
from py1cv8.bsl import extract_name_from_code, has_bsl_keywords
from py1cv8.metadata_binary import (
    extract_type_from_configcas_blob,
    parse_metadata_blob,
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


# ── has_bsl_keywords ──────────────────────────────────────────────────────


def test_has_bsl_keywords_found():
    assert has_bsl_keywords("Процедура Тест()") is True
    assert has_bsl_keywords("Функция Вернуть()") is True
    assert has_bsl_keywords("// comment") is True


def test_has_bsl_keywords_not_found():
    assert has_bsl_keywords("Just some text without keywords") is False
    assert has_bsl_keywords("Привет мир") is False


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


# ── parse_metadata_blob ─────────────────────────────────────────────────────


def test_parse_metadata_blob_dataprocessor():
    txt = """{1,
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
{1,1},""}"""
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 4
    assert result["tech_name"] == "ирИсполняемыйЗапрос"
    assert result["display_names"].get("ru") == "Исполняемый запрос (ИР)"
    assert result["display_names"].get("en") == "Executable query"


def test_parse_metadata_blob_commontemplate():
    """CommonTemplate (type=12) with OPI name ending in digits."""
    txt = """{1,
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
{1,1},""}"""
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 12
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
    txt = """{1,
{2,4,
{3,
{1,0,uuid-test-0000-0000-0000-000000000000},"ОбщийМодуль1",
{3,"ru","Общий модуль 1"},"",0,0,""}
},"",0,0,00000000-0000-0000-0000-000000000000,0},""}"""
    result = parse_metadata_blob(txt)
    assert result is None


def test_parse_metadata_blob_type57():
    txt = """{1,
{57,
{3,
{1,0,cd070a4a-6274-4576-8cc1-f17696a76834},"ирАлгоритмы",
{3,"ru","Алгоритмы (ИР)"},"",0,0,00000000-0000-0000-0000-000000000000,0},1,1,""}"""
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


def test_extract_name_from_code_skip_keyword():
    """Quoted name containing a skip keyword should be rejected."""
    code = 'Сообщить("Object not found");'
    name, _ = extract_name_from_code(code)
    assert name is None


def test_extract_name_from_code_quoted_match():
    """Quoted name NOT in skip keywords should be returned."""
    code = 'Сообщить("Получатели");'
    name, _ = extract_name_from_code(code)
    assert name == "Получатели"


# ── extract_type_from_configcas_blob ────────────────────────────────────────


def test_extract_type_moxcel():
    dec = b"MOXCEL\x00\x08\x00\x01\x00\x0c\x00"
    dec += b'{12,1,"test"}'
    result = extract_type_from_configcas_blob(dec)
    assert result == 12


def test_extract_type_moxcel_type8():
    dec = b"MOXCEL\x00\x08\x00\x01\x00\x08\x00"
    dec += b'{8,1,"test"}'
    result = extract_type_from_configcas_blob(dec)
    assert result == 8


def test_extract_type_braces_pattern():
    dec = b'{1,\n{4,\n{3,\n{1,0,uuid},"TestName"'
    result = extract_type_from_configcas_blob(dec)
    assert result == 4


def test_extract_type_returns_none():
    assert extract_type_from_configcas_blob(b"garbage data here") is None
    assert extract_type_from_configcas_blob(b"") is None


# ── UUID format helpers (resolve_uuid) ───────────────────────────────────


def test_uuid_to_1c_idrref_hex() -> None:
    from py1cv8.resolve_uuid import _normalise_uuid, _uuid_to_1c_idrref_hex

    uuid_str = "9c270050-b666-dffa-11f1-46fd81c23ada"
    hex_val = _normalise_uuid(uuid_str)
    assert hex_val == "9c270050b666dffa11f146fd81c23ada"

    idrref = _uuid_to_1c_idrref_hex(hex_val)
    # time_low 0x9c270050 -> LE: 50 00 9c 27       -> 50009c27? no...
    # Let's trace: hex chars: 9c 27 00 50
    # LE byte order: byte3 byte2 byte1 byte0
    # byte3 = 0x50, byte2 = 0x00, byte1 = 0x27, byte0 = 0x9c
    # hex[6:8] + hex[4:6] + hex[2:4] + hex[0:2] = 50 + 00 + 27 + 9c = 5000279c
    assert idrref == "5000279c66b6fadf11f146fd81c23ada"


def test_uuid_to_1c_idrref_roundtrip() -> None:
    """Verify that the 1C _IDRRef hex correctly encodes a standard UUID."""
    from py1cv8.resolve_uuid import _normalise_uuid, _uuid_to_1c_idrref_hex

    # Known mapping from actual DB: _reference53._IDRRef raw hex
    db_raw_hex = "9c280050b666dffa11f14e880e761abe"
    db_raw_hex_2 = "9c270050b666dffa11f144090b2c44a7"

    # 1C mixed-endian decoding produces the standard UUID:
    #   raw bytes: 9c 28 00 50 | b6 66 | df fa | 11 f1 4e 88 0e 76 1a be
    #   time_low LE = 0x5000289c
    #   time_mid LE = 0x66b6
    #   time_hi  LE = 0xfadf
    # std uuid = 5000289c-66b6-fadf-11f1-4e880e761abe
    std_hex = _normalise_uuid("5000289c-66b6-fadf-11f1-4e880e761abe")
    idrref = _uuid_to_1c_idrref_hex(std_hex)
    assert idrref == db_raw_hex, f"Expected {db_raw_hex}, got {idrref}"

    # Second DB sample
    #   raw bytes: 9c 27 00 50 | b6 66 | df fa | 11 f1 44 09 0b 2c 44 a7
    #   time_low LE = 0x5000279c
    #   time_mid LE = 0x66b6
    #   time_hi  LE = 0xfadf
    # std uuid = 5000279c-66b6-fadf-11f1-44090b2c44a7
    std_hex_2 = _normalise_uuid("5000279c-66b6-fadf-11f1-44090b2c44a7")
    idrref_2 = _uuid_to_1c_idrref_hex(std_hex_2)
    assert idrref_2 == db_raw_hex_2


def test_uuid_to_1c_normalise_uuid() -> None:
    from py1cv8.resolve_uuid import _normalise_uuid

    assert _normalise_uuid("550e8400-e29b-41d4-a716-446655440000") == (
        "550e8400e29b41d4a716446655440000"
    )
    assert _normalise_uuid("550E8400E29B41D4A716446655440000") == (
        "550e8400e29b41d4a716446655440000"
    )
    assert _normalise_uuid("  550E8400-E29B-41D4-A716-446655440000  ") == (
        "550e8400e29b41d4a716446655440000"
    )
