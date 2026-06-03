"""Tests for DBNames parsing module."""

from __future__ import annotations

from py1cv8.dbnames import (
    DBNamesEntry,
    DBNamesProviderImpl,
    generate_db_name,
    get_parent_type,
)


def test_dbnames_entry_category_main() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="Reference",
        number=42,
    )
    assert entry.category == "main"


def test_dbnames_entry_category_service_by_type() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="STTSettings",
        number=0,
    )
    assert entry.category == "service"


def test_dbnames_entry_category_service_by_zero_uuid() -> None:
    entry = DBNamesEntry(
        uuid="00000000-0000-0000-0000-000000000000",
        type_name="Reference",
        number=1,
    )
    assert entry.category == "service"


def test_generate_db_name_main() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="Reference",
        number=42,
    )
    assert generate_db_name(entry) == "_reference42"


def test_generate_db_name_companion() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="ChrcSInf",
        number=7,
    )
    assert generate_db_name(entry) == "_chrcsinf7"


def test_generate_db_name_service() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="STTSettings",
        number=0,
    )
    assert generate_db_name(entry) == "_sttsettings"


def test_generate_db_name_unknown_type() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="BogusType",
        number=99,
    )
    assert generate_db_name(entry) is None


def test_generate_db_name_sub_with_parent() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="Fld",
        number=3,
    )
    assert generate_db_name(entry, "_reference53") == "_reference53_fld3"


def test_generate_db_name_sub_without_parent() -> None:
    entry = DBNamesEntry(
        uuid="11111111-1111-1111-1111-111111111111",
        type_name="Fld",
        number=3,
    )
    assert generate_db_name(entry) is None


def test_get_parent_type_sub() -> None:
    assert get_parent_type("Fld", "") == "Reference"


def test_get_parent_type_companion() -> None:
    assert get_parent_type("ChrcSInf", "") == "Chrc"


def test_get_parent_type_unknown() -> None:
    assert get_parent_type("BogusType", "") is None


def test_dbnames_provider_parse() -> None:
    provider = DBNamesProviderImpl()
    result = provider.parse_dbnames_text(
        "{11111111-1111-1111-1111-111111111111,\"Reference\",42}"
    )
    assert len(result) == 1
    assert result[0]["uuid"] == "11111111-1111-1111-1111-111111111111"
    assert result[0]["type_name"] == "Reference"
    assert result[0]["number"] == 42
    assert result[0]["category"] == "main"
    assert result[0]["db_name"] == "_reference42"


def test_dbnames_provider_generate_db_name() -> None:
    provider = DBNamesProviderImpl()
    entry: dict = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "type_name": "Document",
        "number": 99,
    }
    name = provider.generate_db_name(entry)
    assert name == "_document99"


def test_dbnames_provider_generate_db_name_with_parent() -> None:
    provider = DBNamesProviderImpl()
    entry: dict = {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "type_name": "Fld",
        "number": 5,
    }
    name = provider.generate_db_name(entry, "_document100")
    assert name == "_document100_fld5"
