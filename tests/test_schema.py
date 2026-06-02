"""Tests for schema discovery module."""

from __future__ import annotations

from py1cv8.schema import (
    ColumnInfo,
    DBNamesEntry,
    ObjectInfo,
    SchemaLoader,
    SchemaRegistry,
    ServiceTableInfo,
    generate_db_name,
    parse_dbnames_text,
)


def test_parse_dbnames() -> None:
    """Parse DBNames text format."""
    text = (
        '{257,\n'
        '{115,\n'
        '{00000000-0000-0000-0000-000000000000,"STTSettings",1},\n'
        '{cd070a4a-6274-4576-8cc1-f17696a76834,"Reference",53},\n'
        '{fe3fc224-60a5-4d1c-bc54-41ef18be8792,"VT",59},\n'
        '{fe3fc224-60a5-4d1c-bc54-41ef18be8792,"LineNo",60},\n'
        '{68a9ad1e-cba3-4c21-b565-03aa3efbf31d,"Const",155},\n'
        '{bd01340d-35fa-49f5-adda-9ea21b4fd05c,"Enum",160},\n'
        '{e70db5ca-460d-4fb5-bc6e-6460d67278cf,"Document",209},\n'
        '}\n'
        '}\n'
    )
    entries = parse_dbnames_text(text)
    assert len(entries) == 7

    assert entries[0].type_name == "STTSettings"
    assert entries[0].number == 1
    assert entries[0].uuid == "00000000-0000-0000-0000-000000000000"

    assert entries[1].type_name == "Reference"
    assert entries[1].number == 53
    assert entries[1].uuid == "cd070a4a-6274-4576-8cc1-f17696a76834"

    assert entries[2].type_name == "VT"
    assert entries[3].type_name == "LineNo"
    assert entries[2].uuid == entries[3].uuid == "fe3fc224-60a5-4d1c-bc54-41ef18be8792"


def test_generate_db_name_reference() -> None:
    """Generate DB name for Reference type."""
    entry = DBNamesEntry(
        uuid="cd070a4a-6274-4576-8cc1-f17696a76834",
        type_name="Reference",
        number=53,
    )
    assert generate_db_name(entry) == "_reference53"


def test_generate_db_name_document() -> None:
    entry = DBNamesEntry(
        uuid="e70db5ca-460d-4fb5-bc6e-6460d67278cf",
        type_name="Document",
        number=209,
    )
    assert generate_db_name(entry) == "_document209"


def test_generate_db_name_service() -> None:
    entry = DBNamesEntry(
        uuid="00000000-0000-0000-0000-000000000000",
        type_name="Bots",
        number=40,
    )
    assert generate_db_name(entry) == "_bots"


def test_generate_db_name_vt() -> None:
    """Generate sub-table name with parent context."""
    entry = DBNamesEntry(
        uuid="fe3fc224-60a5-4d1c-bc54-41ef18be8792",
        type_name="VT",
        number=59,
    )
    # Without parent context, sub-tables return None
    assert generate_db_name(entry) is None
    # With parent context
    assert generate_db_name(entry, "_reference53") == "_reference53_vt59"


def test_column_info() -> None:
    col = ColumnInfo(name="test", data_type="integer", nullable=True, is_pk=False, ordinal=1)
    assert col.name == "test"
    assert col.data_type == "integer"
    assert col.nullable is True
    assert col.is_pk is False


def test_object_info() -> None:
    obj = ObjectInfo(
        uuid="cd070a4a-6274-4576-8cc1-f17696a76834",
        tech_name="TestCatalog",
        display_ru="Тестовый каталог",
        type_num=57,
        category="Catalogs",
        main_table="_reference53",
        table_number=53,
    )
    assert obj.tech_name == "TestCatalog"
    assert obj.display_ru == "Тестовый каталог"
    assert obj.category == "Catalogs"
    assert obj.main_table == "_reference53"


def test_service_table_info() -> None:
    svc = ServiceTableInfo(
        db_name="_bots",
        description="System table: Bots",
    )
    assert svc.db_name == "_bots"
    assert svc.description == "System table: Bots"
    assert svc.columns == []


def test_schema_registry_lazy_load() -> None:
    """Test that SchemaRegistry lazy loads."""
    reg = SchemaRegistry("MessageCenter")
    assert reg._loaded is False
    reg.lazy_load()
    assert reg._loaded is True
    assert len(reg.dbnames_entries) > 0
    assert len(reg.tables) > 0


def test_schema_registry_contains() -> None:
    reg = SchemaRegistry("MessageCenter")
    reg.lazy_load()
    assert "_reference53" in reg
    assert "_document209" in reg
    assert "_inforg119" in reg
    assert "_nonexistent_table_xyz" not in reg


def test_schema_registry_get() -> None:
    reg = SchemaRegistry("MessageCenter")
    reg.lazy_load()
    obj = reg.get_object_by_table("_reference53")
    assert obj is not None
    assert isinstance(obj, ObjectInfo)
    assert obj.category == "Catalogs"
    assert len(obj.columns) > 0

    svc = reg.get_object_by_table("_bots")
    assert svc is not None
    assert isinstance(svc, ServiceTableInfo)


def test_schema_registry_search() -> None:
    reg = SchemaRegistry("MessageCenter")
    reg.lazy_load()
    results = reg.search("reference")
    assert len(results) > 0
    assert any("reference" in r.tech_name.lower() for r in results)


def test_schema_registry_summary() -> None:
    reg = SchemaRegistry("MessageCenter")
    reg.lazy_load()
    summary = reg.summary
    assert summary["database"] == "MessageCenter"
    assert summary["total_tables"] > 0
    assert "categories" in summary


def test_schema_loader() -> None:
    loader = SchemaLoader()
    reg = loader("MessageCenter")
    assert reg.dbname == "MessageCenter"
    assert len(reg.tables) > 0

    # Should return cached version
    reg2 = loader("MessageCenter")
    assert reg2 is reg

    loader.clear()
    assert loader._registries == {}
