"""Tests for binary metadata parser."""

from __future__ import annotations

import struct

from py1cv8.metadata_binary import (
    extract_type_from_configcas_blob,
    parse_metadata_blob,
)


def test_parse_metadata_blob_standard() -> None:
    txt = (
        '{1,\n{93,0,{11111111-1111-1111-1111-111111111111},'
        '"TestObject",{"ru","ТестовыйОбъект"},1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["uuid"] == "11111111-1111-1111-1111-111111111111"
    assert result["tech_name"] == "TestObject"
    assert result["display_names"] == {"ru": "ТестовыйОбъект"}
    assert result["type_num"] == 93


def test_parse_metadata_blob_with_obj_uuid() -> None:
    txt = (
        '{1,0,{22222222-2222-2222-2222-222222222222},'
        '{"ru","Объект"},1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["uuid"] == "22222222-2222-2222-2222-222222222222"


def test_parse_metadata_blob_obj_uuid_preferred() -> None:
    """{1,0,UUID} is preferred over the first UUID in text."""
    txt = (
        '{99,0,{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa},'
        '{1,0,bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb}'
        ',"MyObject",1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["uuid"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_parse_metadata_blob_no_uuid_at_all() -> None:
    txt = "no UUID here at all"
    result = parse_metadata_blob(txt)
    assert result is None


def test_parse_metadata_blob_no_name_after_uuid() -> None:
    txt = "{11111111-1111-1111-1111-111111111111,12345}"
    result = parse_metadata_blob(txt)
    assert result is None


def test_parse_metadata_blob_generic_prefix_skipped() -> None:
    txt = (
        '{1,0,{33333333-3333-3333-3333-333333333333},'
        '"ОбщийМодуль142",1}'
    )
    result = parse_metadata_blob(txt)
    assert result is None


def test_parse_metadata_blob_rus_prefix_not_generic() -> None:
    txt = (
        '{1,0,{44444444-4444-4444-4444-444444444444},'
        '"Справочник.Клиенты",1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["tech_name"] == "Справочник.Клиенты"


def test_parse_metadata_blob_type_num_from_header() -> None:
    txt = (
        '{1,\n{55,\n{55555555-5555-5555-5555-555555555555},'
        '"SomeType",1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] == 55


def test_parse_metadata_blob_type_num_out_of_range() -> None:
    txt = (
        '{1,0,{66666666-6666-6666-6666-666666666666},'
        '"Large",{"ru","Большой"},100}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["type_num"] is None


def test_parse_metadata_blob_multiple_languages() -> None:
    txt = (
        '{1,0,{77777777-7777-7777-7777-777777777777},'
        '"Multi",{"ru","Русский","en","English","uk","Українська"},1}'
    )
    result = parse_metadata_blob(txt)
    assert result is not None
    assert result["display_names"] == {
        "ru": "Русский",
        "en": "English",
        "uk": "Українська",
    }


def test_extract_type_from_configcas_moxcel() -> None:
    """MOXCEL header with type_num in bytes 11-12."""
    import struct
    dec = b"MOXCEL" + b"\x00" * 5 + struct.pack("<H", 42) + b"\x00"
    result = extract_type_from_configcas_blob(dec)
    assert result == 42


def test_extract_type_from_configcas_moxcel_large_type() -> None:
    """Type > 99 from MOXCEL header returns None."""
    import struct
    dec = b"MOXCEL" + b"\x00" * 5 + struct.pack("<H", 200) + b"\x00"
    result = extract_type_from_configcas_blob(dec)
    assert result is None


def test_extract_type_from_configcas_no_moxcel() -> None:
    """Fallback: scan for {1,{N pattern."""
    dec = b'some stuff here {1,\n{42,\nmore data'
    result = extract_type_from_configcas_blob(dec)
    assert result == 42


def test_extract_type_from_configcas_no_match() -> None:
    dec = b"no type information here"
    result = extract_type_from_configcas_blob(dec)
    assert result is None


def test_extract_type_from_configcas_type_over_99() -> None:
    """Fallback with type > 99 returns None."""
    dec = b"prefix {1,{200,\nmore data"
    result = extract_type_from_configcas_blob(dec)
    assert result is None


def test_extract_type_from_configcas_moxcel_too_short() -> None:
    """MOXCEL header shorter than 13 bytes can't extract type."""
    dec = b"MOXCELabc"
    result = extract_type_from_configcas_blob(dec)
    assert result is None


def test_extract_type_from_configcas_moxcel_bad_magic() -> None:
    """Non-MOXCEL header skips to fallback regex."""
    dec = b"NOTMOX" + b"\x00" * 10
    result = extract_type_from_configcas_blob(dec)
    # No {1,{N match either
    assert result is None


# ── ConfigMetadataProvider class tests ───────────────────────────────────


def test_config_metadata_provider_init() -> None:
    """ConfigMetadataProvider stores db_provider."""
    from py1cv8.db import PgDatabaseProvider
    from py1cv8.metadata_binary import ConfigMetadataProvider

    dbp = PgDatabaseProvider("postgresql+psycopg2://u:p@h:5433")
    provider = ConfigMetadataProvider(dbp)
    assert provider._db is dbp


def test_config_metadata_provider_static_methods() -> None:
    """Static methods delegate to module-level functions."""
    from py1cv8.metadata_binary import ConfigMetadataProvider

    result = ConfigMetadataProvider.parse_metadata_blob(
        '{1,0,{11111111-1111-1111-1111-111111111111},"Test",1}'
    )
    assert result is not None
    assert result["tech_name"] == "Test"

    dec = b"MOXCEL" + b"\x00" * 5 + struct.pack("<H", 77) + b"\x00"
    tn = ConfigMetadataProvider.extract_type_from_configcas_blob(dec)
    assert tn == 77


def test_config_metadata_provider_build_map() -> None:
    """build_metadata_map reads Config table from real DB."""
    from py1cv8.db import PgDatabaseProvider
    from py1cv8.metadata_binary import ConfigMetadataProvider

    dbp = PgDatabaseProvider("postgresql+psycopg2://postgres:qwaseD12@localhost:5433")
    provider = ConfigMetadataProvider(dbp)
    result = provider.build_metadata_map("test")
    assert isinstance(result, dict)
    assert len(result) > 0
    for uuid_val, info in result.items():
        assert "uuid" in info
        assert "tech_name" in info
        assert info["uuid"] == uuid_val


def test_module_level_build_metadata_map() -> None:
    """Module-level build_metadata_map works with real DB."""
    from py1cv8.metadata_binary import build_metadata_map

    result = build_metadata_map("test")
    assert isinstance(result, dict)
    assert len(result) > 0
