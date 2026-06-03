"""Tests for relationships.py — inter-table reference graph building."""

from __future__ import annotations

from py1cv8.dbnames import DBNamesEntry
from py1cv8.relationships import (
    RelationshipBuilderImpl,
    _resolve_ref_target,
    build_relationships,
)
from py1cv8.schema import ColumnInfo, ObjectInfo


def _make_col(name: str):
    """Create a minimal column info object."""
    return ColumnInfo(
        name=name,
        data_type="varchar",
        nullable=True,
        is_pk=False,
        ordinal=1,
    )


def _make_table_info(columns: list[str], uuid: str | None = None):
    """Create a minimal ObjectInfo."""
    return ObjectInfo(
        uuid=uuid or "00000000-0000-0000-0000-000000000001",
        tech_name="TestObj",
        display_ru="ТестОбъект",
        type_num=1,
        category="main",
        main_table="_Reference1",
        table_number=1,
        columns=[_make_col(n) for n in columns],
    )


def _make_dbnames_entries(entries: list[tuple[str, str, int]]) -> list[DBNamesEntry]:
    return [DBNamesEntry(uuid=u, type_name=t, number=n) for u, t, n in entries]


# ── build_relationships ──────────────────────────────────────────────────────


def test_build_relationships_basic_rref():
    """Table with RRef column resolves to target."""
    tables = {
        "_AccRg1_Recorder": _make_table_info([
            "Дата", "Период", "Document104_RRef", "СчетДт",
        ]),
    }
    entries = _make_dbnames_entries([
        ("aaaa-0000-0000-0000-000000000001", "Reference", 1),
        ("bbbb-0000-0000-0000-000000000002", "Document", 104),
    ])

    rels = build_relationships(
        tables, entries, frozenset({"Reference", "Document", "InfoRg", "AccRg"})
    )

    assert "_AccRg1_Recorder" in rels
    refs = rels["_AccRg1_Recorder"]
    rref_refs = [r for r in refs if r["column"] == "Document104_RRef"]
    assert len(rref_refs) == 1
    assert rref_refs[0]["ref_type"] == "RRef"


def test_build_relationships_rtref():
    """RTRef columns are detected."""
    tables = {
        "_AccRgT1": _make_table_info([
            "Регистратор", "PeriodType", "Account_RRef",
        ]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Reference"}))

    assert "_AccRgT1" in rels


def test_build_relationships_owner():
    """Owner columns resolve to parent table."""
    tables = {
        "_InfoRg1": _make_table_info([
            "Period", "Catalog42_Owner", "Значение",
        ]),
    }
    entries = _make_dbnames_entries([
        ("cccc-0000-0000-0000-000000000003", "Reference", 42),
    ])
    rels = build_relationships(tables, entries, frozenset({"Reference", "InfoRg"}))

    assert "_InfoRg1" in rels
    refs = rels["_InfoRg1"]
    owner_refs = [r for r in refs if r["column"] == "Catalog42_Owner"]
    assert len(owner_refs) == 1
    assert owner_refs[0]["ref_type"] == "Owner"


def test_build_relationships_folder():
    """Folder columns are detected for hierarchical references."""
    tables = {
        "_Reference1": _make_table_info([
            "Деятельность", "Наименование", "Parent_Folder",
        ]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Reference"}))

    assert "_Reference1" in rels
    refs = rels["_Reference1"]
    folder_refs = [r for r in refs if r["column"] == "Parent_Folder"]
    assert len(folder_refs) == 1


def test_build_relationships_parent():
    """Parent columns are detected."""
    tables = {
        "_Reference2": _make_table_info([
            "Наименование", "Группа_Parent",
        ]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Reference"}))

    assert "_Reference2" in rels


def test_build_relationships_recorder():
    """Recorder columns are detected."""
    tables = {
        "_Document104": _make_table_info([
            "Дата", "Сумма", "Journal1_Recorder",
        ]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Document"}))

    assert "_Document104" in rels


def test_build_relationships_no_refs():
    """Table without reference columns produces no entry."""
    tables = {
        "_Const1": _make_table_info(["Значение", "Comment"]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Const"}))

    assert "_Const1" not in rels


def test_build_relationships_unresolved_prefix():
    """Unresolvable prefix gets wildcard fallback."""
    tables = {
        "_Test": _make_table_info(["Unknown123_RRef"]),
    }
    entries = []
    rels = build_relationships(tables, entries, frozenset({"Reference"}))

    assert "_Test" in rels
    refs = rels["_Test"]
    assert any("_Unknown123*" in r["target_table"] for r in refs)


# ── _resolve_ref_target ──────────────────────────────────────────────────────


def test_resolve_id_self_reference():
    """ID prefix resolves to self-reference."""
    result = _resolve_ref_target("ID", [], frozenset(), {})
    assert result == "_IDRRef (self)"


def test_resolve_ref_by_number():
    """Resolve by ref number in DBNames entries."""
    entries = _make_dbnames_entries([
        ("aaaa-0000-0000-0000-000000000010", "Reference", 10),
    ])
    uuid_map = {e.uuid: e for e in entries}
    result = _resolve_ref_target("ref10", entries, frozenset({"Reference"}), uuid_map)
    assert result is not None
    assert "reference" in result.lower()


def test_resolve_ref_by_uuid():
    """Resolve by UUID prefix in column name."""
    uuid = "aaaa0000-0000-0000-0000-000000000020"
    entries = _make_dbnames_entries([
        (uuid, "Document", 5),
    ])
    uuid_map = {e.uuid: e for e in entries}
    result = _resolve_ref_target(uuid, entries, frozenset({"Document"}), uuid_map)
    assert result is not None


def test_resolve_non_main_type_ignored():
    """Non-main types are skipped during resolution."""
    entries = _make_dbnames_entries([
        ("aaaa-0000-0000-0000-000000000030", "Fld", 1),
    ])
    uuid_map = {e.uuid: e for e in entries}
    result = _resolve_ref_target("ref1", entries, frozenset({"Reference"}), uuid_map)
    assert result is None


# ── RelationshipBuilderImpl (contract class) ─────────────────────────────────


def test_impl_build_with_dicts():
    """Impl accepts raw dicts and converts them to DBNamesEntry."""
    impl = RelationshipBuilderImpl()

    cols = [_make_col("Ref1_RRef")]
    tables = {
        "_TestTable": ObjectInfo(
            uuid="00000000-0000-0000-0000-000000000099",
            tech_name="TestTable",
            display_ru="ТестТаблица",
            type_num=1,
            category="main",
            main_table="_Reference1",
            table_number=1,
            columns=cols,
        ),
    }

    entries = [
        {"uuid": "aaaa-0000-0000-0000-000000000099", "type_name": "Reference", "number": 1},
    ]
    main_types = frozenset({"Reference"})

    rels = impl.build_relationships(tables, entries, main_types)
    assert "_TestTable" in rels


def test_impl_build_with_dbnames_entries():
    """Impl accepts pre-built DBNamesEntry objects."""
    impl = RelationshipBuilderImpl()

    cols = [_make_col("Catalog5_RRef")]
    tables = {
        "_TestTable2": ObjectInfo(
            uuid="00000000-0000-0000-0000-000000000098",
            tech_name="TestTable2",
            display_ru="ТестТаблица2",
            type_num=40,
            category="main",
            main_table="_Document5",
            table_number=5,
            columns=cols,
        ),
    }

    entries = [DBNamesEntry(
        uuid="bbbb-0000-0000-0000-000000000098",
        type_name="Reference",
        number=5,
    )]
    main_types = frozenset({"Reference", "Document"})

    rels = impl.build_relationships(tables, entries, main_types)
    assert "_TestTable2" in rels


def test_impl_ignores_non_object_info():
    """Impl skips non-ObjectInfo/non-ServiceTableInfo values."""
    impl = RelationshipBuilderImpl()

    tables = {
        "random_key": {"not": "an ObjectInfo"},
        42: "also not valid",
    }
    entries = []
    main_types = frozenset()

    rels = impl.build_relationships(tables, entries, main_types)
    assert len(rels) == 0
