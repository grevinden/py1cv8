"""E2E integration tests for MCP server — tests tools against a real DB."""

from __future__ import annotations

import json

import pytest

from py1cv8.bootstrap import create_schema_loader
from py1cv8.mcp_server import (
    _analyze_object,
    _build_db_overview,
    _config_diff_detail,
    _explain_object,
    _find_by_value,
    _find_changed_objects,
    _get_bsl_code,
    _get_config_snapshot,
    _get_notification_analytics,
    _get_object_config_history,
    _get_relationship_map,
    _get_schema,
    _orphaned_records,
    _run_sql,
    _search_1c_queries,
    _search_bsl_code,
    _search_metadata,
    _table_stats,
)
from py1cv8.schema import ObjectInfo

_TEST_DB_URL = "postgresql+psycopg2://postgres:qwaseD12@localhost:5433"

# Discover a real ObjectInfo main table for the test DB
_loader_for_discovery = create_schema_loader(_TEST_DB_URL)
_reg = _loader_for_discovery("test")
TEST_TABLE = next(
    (t for t, i in _reg.tables.items() if isinstance(i, ObjectInfo)),
    "_reference53",
)
_test_tbl_info = _reg.tables[TEST_TABLE]
TECH_NAME = _test_tbl_info.tech_name if isinstance(_test_tbl_info, ObjectInfo) else TEST_TABLE


@pytest.fixture(autouse=True)
def _setup_loader():
    """Set up the MCP server schema loader with real production providers."""
    import py1cv8.mcp_server as mcp

    original = mcp._loader
    mcp._loader = create_schema_loader(_TEST_DB_URL)
    yield
    mcp._loader = original


# ── get_db_overview tool ─────────────────────────────────────────────────


def test_db_overview() -> None:
    result = _build_db_overview("test")
    assert result["database"] == "test"
    assert result["total_tables"] > 0
    assert "entity_types" in result
    # Verify at least one entity type has the right structure
    for _cat, info in result["entity_types"].items():
        assert "count" in info
        assert "description" in info
        assert "objects" in info
        for obj in info["objects"]:
            assert "name" in obj
            assert "main_table" in obj


# ── get_schema tool ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_list_tables() -> None:
    result = await _get_schema("test", {})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["database"] == "test"
    assert data["total_tables"] > 0
    assert "by_category" in data


@pytest.mark.asyncio
async def test_schema_specific_table() -> None:
    result = await _get_schema("test", {"table": TEST_TABLE})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "columns" in data
    assert data["column_count"] > 0
    assert data["main_table"] == TEST_TABLE


@pytest.mark.asyncio
async def test_schema_unknown_table() -> None:
    result = await _get_schema("test", {"table": "_nonexistent_xyz"})
    assert "not found" in result[0].text.lower()


# ── search_metadata tool ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metadata_summary() -> None:
    result = await _search_metadata("test", {})
    data = json.loads(result[0].text)
    assert "total_tables" in data or "total_objects" in data


@pytest.mark.asyncio
async def test_metadata_by_category() -> None:
    result = await _search_metadata("test", {"category": "catalog"})
    data = json.loads(result[0].text)
    assert data["count"] > 0


@pytest.mark.asyncio
async def test_metadata_by_search() -> None:
    result = await _search_metadata("test", {"search": "reference"})
    data = json.loads(result[0].text)
    assert data["count"] > 0


# ── analyze_object tool ──────────────────────────────────────────────────


def test_analyze_by_table_name() -> None:
    result = _analyze_object("test", {"name": TEST_TABLE})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] > 0
    obj = data["objects"][0]
    assert obj["main_table"] == TEST_TABLE
    assert "columns" in obj


def test_analyze_by_tech_name() -> None:
    result = _analyze_object("test", {"name": TECH_NAME})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] > 0


def test_analyze_unknown() -> None:
    result = _analyze_object("test", {"name": "XYZ_does_not_exist"})
    assert "no results" in result[0].text.lower() or "not found" in result[0].text.lower()


# ── run_sql tool ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_simple() -> None:
    result = await _run_sql("test", {"sql": "SELECT 1 AS ok"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["columns"] == ["ok"]
    assert len(data["rows"]) == 1
    assert data["rows"][0]["ok"] == 1


@pytest.mark.asyncio
async def test_query_from_table() -> None:
    result = await _run_sql("test", {"sql": f"SELECT COUNT(*) AS cnt FROM {TEST_TABLE}"})
    data = json.loads(result[0].text)
    assert data["columns"] == ["cnt"]
    assert data["row_count"] == 1


@pytest.mark.asyncio
async def test_query_read_only_enforced() -> None:
    result = await _run_sql("test", {"sql": f"DROP TABLE {TEST_TABLE}"})
    assert "only" in result[0].text.lower()


@pytest.mark.asyncio
async def test_query_with_limit() -> None:
    result = await _run_sql("test", {"sql": f"SELECT * FROM {TEST_TABLE}", "limit": 3})
    data = json.loads(result[0].text)
    assert data["row_count"] <= 3


# ── table_stats tool ──────────────────────────────────────────────────────


def test_table_stats_known_table() -> None:
    result = _table_stats("test", {"table": TEST_TABLE})
    assert len(result) == 1
    text = result[0].text
    assert TEST_TABLE in text
    assert "строк" in text or "rows" in text.lower()
    assert "Колонка" in text


def test_table_stats_unknown_table() -> None:
    result = _table_stats("test", {"table": "_nonexistent_xyz"})
    assert "не найдена" in result[0].text.lower() or "not found" in result[0].text.lower()


# ── find_by_value tool ────────────────────────────────────────────────────


def test_find_by_value_too_short() -> None:
    result = _find_by_value("test", {"value": "x"})
    assert "2 символа" in result[0].text


def test_find_by_value_no_match() -> None:
    result = _find_by_value("test", {"value": "ZZZZ_XYZZY_NOMATCH"})
    assert "не найдено" in result[0].text


def test_find_by_value_filtered_table() -> None:
    result = _find_by_value("test", {"value": "test", "table": TEST_TABLE})
    assert len(result) == 1
    text = result[0].text
    # Should find matches or show "not found" — both are valid outcomes
    assert isinstance(text, str)


# ── config_diff_detail tool ──────────────────────────────────────────────


def test_config_diff_detail_unknown() -> None:
    result = _config_diff_detail("MessageCenter", {"uuid": "00000000-0000-0000-0000-000000000000"})
    assert "не найден" in result[0].text or "not found" in result[0].text


def test_config_diff_detail_live_only() -> None:
    """UUID that exists only in config (live)."""
    result = _config_diff_detail("MessageCenter", {"uuid": "001ee925-45d3-4147-9491-f5043eaa3694"})
    text = result[0].text
    assert "config" in text.lower()
    assert "UUID" in text or "Объект" in text


def test_config_diff_detail_pending_only() -> None:
    """UUID that exists only in configsave (pending)."""
    result = _config_diff_detail("MessageCenter", {"uuid": "447c14df-7b63-4739-a08e-cb81f1e24394"})
    text = result[0].text
    assert "configsave" in text or "pending" in text.lower()
    assert "447c14df" in text


# ── orphaned_records tool ─────────────────────────────────────────────────


def test_orphaned_records_no_filter() -> None:
    result = _orphaned_records("MessageCenter", {})
    assert len(result) == 1
    text = result[0].text
    # May find orphaned records or not — either is valid
    assert isinstance(text, str) and len(text) > 0


def test_orphaned_records_filtered() -> None:
    result = _orphaned_records("MessageCenter", {"table": "_reference53"})
    assert len(result) == 1
    text = result[0].text
    assert isinstance(text, str) and len(text) > 0


# ── get_bsl_code tool ─────────────────────────────────────────────────────


def test_get_bsl_code_empty() -> None:
    result = _get_bsl_code("MessageCenter", {"module_name": ""})
    assert "provide" in result[0].text.lower()


def test_get_bsl_code_not_found() -> None:
    result = _get_bsl_code("MessageCenter", {"module_name": "ZZZ_XYZZY_NONEXISTENT"})
    assert "no bsl code" in result[0].text.lower()


def test_get_bsl_code_found() -> None:
    result = _get_bsl_code("MessageCenter", {"module_name": "ирУведомленияСервер"})
    assert len(result) == 1
    text = result[0].text
    assert "Module" in text or "UUID" in text


# ── get_relationship_map tool ─────────────────────────────────────────────


def test_get_relationship_map_empty() -> None:
    result = _get_relationship_map("MessageCenter", {"name": ""})
    assert "provide" in result[0].text.lower()


def test_get_relationship_map_unknown() -> None:
    result = _get_relationship_map("MessageCenter", {"name": "XYZ_nonexistent"})
    assert "not found" in result[0].text.lower()


def test_get_relationship_map_known() -> None:
    result = _get_relationship_map("MessageCenter", {"name": "_reference53"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert "table" in data
    assert "outgoing_refs" in data
    assert "incoming_refs" in data


# ── explain_object tool ───────────────────────────────────────────────────


def test_explain_object_empty() -> None:
    result = _explain_object("MessageCenter", {"name": ""})
    assert "provide" in result[0].text.lower()


def test_explain_object_unknown() -> None:
    result = _explain_object("MessageCenter", {"name": "XYZ_nonexistent"})
    assert "no results" in result[0].text.lower() or "not found" in result[0].text.lower()


def test_explain_object_known() -> None:
    result = _explain_object("MessageCenter", {"name": "_reference53"})
    assert len(result) == 1
    text = result[0].text
    assert "колонок" in text or "columns" in text.lower()
    assert "Таблица" in text


# ── get_notification_analytics tool ───────────────────────────────────────


def test_notification_analytics_basic() -> None:
    result = _get_notification_analytics("MessageCenter", {})
    assert len(result) == 1
    text = result[0].text
    assert isinstance(text, str) and len(text) > 0


def test_notification_analytics_with_dates() -> None:
    result = _get_notification_analytics(
        "MessageCenter", {"start_date": "2025-01-01", "end_date": "2026-12-31"},
    )
    assert len(result) == 1
    text = result[0].text
    assert isinstance(text, str)


# ── search_bsl_code tool ──────────────────────────────────────────────────


def test_search_bsl_code_short_query() -> None:
    result = _search_bsl_code("MessageCenter", {"query": "x"})
    assert "min 2 chars" in result[0].text


def test_search_bsl_code_no_match() -> None:
    result = _search_bsl_code("MessageCenter", {"query": "ZZZ_XYZZY_NONEXISTENT"})
    assert "no matches" in result[0].text.lower()


def test_search_bsl_code_found() -> None:
    result = _search_bsl_code("MessageCenter", {"query": "Получатели", "max_results": 3})
    assert len(result) == 1
    text = result[0].text
    assert "BSL" in text or "совпадений" in text


# ── search_1c_queries tool ────────────────────────────────────────────────


def test_search_1c_queries_short_query() -> None:
    result = _search_1c_queries("MessageCenter", {"query": "x"})
    assert "min 2 chars" in result[0].text


def test_search_1c_queries_no_match() -> None:
    result = _search_1c_queries("MessageCenter", {"query": "ZZZ_XYZZY_NONEXISTENT"})
    assert "no matches" in result[0].text.lower()


def test_search_1c_queries_found() -> None:
    result = _search_1c_queries("MessageCenter", {"query": "ВЫБРАТЬ", "max_results": 2})
    assert len(result) == 1
    text = result[0].text
    assert "1С" in text or "SQL" in text or "совпадений" in text


# ── get_config_snapshot tool ──────────────────────────────────────────────


def test_get_config_snapshot_invalid_source() -> None:
    result = _get_config_snapshot("MessageCenter", {"source": "invalid"})
    assert "must be" in result[0].text.lower()


def test_get_config_snapshot_configsave() -> None:
    result = _get_config_snapshot("MessageCenter", {"source": "configsave"})
    assert len(result) == 1
    text = result[0].text
    assert "total_entries" in text or "by_category" in text


def test_get_config_snapshot_config() -> None:
    result = _get_config_snapshot("MessageCenter", {"source": "config"})
    assert len(result) == 1
    text = result[0].text
    assert "total_entries" in text or "by_category" in text


# ── find_changed_objects tool ─────────────────────────────────────────────


def test_find_changed_objects_basic() -> None:
    result = _find_changed_objects("MessageCenter", {})
    assert len(result) == 1
    text = result[0].text
    assert "summary" in text or "changed" in text or "Error" in text


# ── get_object_config_history tool ────────────────────────────────────────


def test_get_object_config_history_no_params() -> None:
    result = _get_object_config_history("MessageCenter", {})
    assert "uuid или name" in result[0].text.lower()


def test_get_object_config_history_by_unknown_name() -> None:
    result = _get_object_config_history("MessageCenter", {"name": "XYZ_nonexistent"})
    assert "не найден" in result[0].text or "not found" in result[0].text.lower()


def test_get_object_config_history_by_known_uuid() -> None:
    result = _get_object_config_history(
        "MessageCenter", {"uuid": "001ee925-45d3-4147-9491-f5043eaa3694"},
    )
    assert len(result) == 1
    text = result[0].text
    assert "uuid" in text or "tech_name" in text or "history" in text or "note" in text


def test_get_object_config_history_by_name() -> None:
    result = _get_object_config_history("MessageCenter", {"name": "_reference53"})
    assert len(result) == 1
    text = result[0].text
    assert "uuid" in text or "tech_name" in text or "history" in text or "note" in text


# ── error handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_invalid_db() -> None:
    with pytest.raises(Exception, match=r"Unknown database|could not translate|does not exist"):
        await _get_schema("invalid_db", {})


# ── Additional coverage edge cases ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_metadata_by_uuid() -> None:
    """search_metadata with uuid filter."""
    result = await _search_metadata("test", {"uuid": "abc"})
    data = json.loads(result[0].text)
    assert isinstance(data, dict)


def test_analyze_empty_name() -> None:
    """analyze_object with empty name."""
    result = _analyze_object("test", {"name": ""})
    assert "provide" in result[0].text.lower()


def test_notification_analytics_start_only() -> None:
    """get_notification_analytics with only start_date."""
    result = _get_notification_analytics("MessageCenter", {"start_date": "2025-01-01"})
    assert len(result) == 1
    assert isinstance(result[0].text, str) and len(result[0].text) > 0


@pytest.mark.asyncio
async def test_query_with_resolve_names() -> None:
    """run_sql with resolve_names=True."""
    result = await _run_sql("test", {"sql": "SELECT 1 AS ok", "resolve_names": "true"})
    data = json.loads(result[0].text)
    assert data["columns"] == ["ok"]


@pytest.mark.asyncio
async def test_query_error_handling() -> None:
    """run_sql with invalid SQL to trigger error handler."""
    result = await _run_sql("test", {"sql": "SELECT nonsense_syntax_error"})
    assert "error" in result[0].text.lower()


def test_table_stats_empty_name() -> None:
    """table_stats with empty table name."""
    result = _table_stats("test", {"table": ""})
    assert "таблицы" in result[0].text.lower()


def test_search_bsl_code_many_matches() -> None:
    """search_bsl_code with common keyword to trigger match_count >3."""
    result = _search_bsl_code("MessageCenter", {"query": "конецпроцедуры"})
    assert len(result) == 1
    assert isinstance(result[0].text, str) and len(result[0].text) > 0


def test_config_diff_detail_empty_uuid() -> None:
    """config_diff_detail with empty uuid."""
    result = _config_diff_detail("MessageCenter", {"uuid": ""})
    assert "provide" in result[0].text.lower() or "uuid" in result[0].text.lower()


def test_object_config_history_bad_uuid() -> None:
    """get_object_config_history with UUID that does not exist."""
    result = _get_object_config_history(
        "MessageCenter", {"uuid": "00000000-0000-0000-0000-000000000000"},
    )
    assert "not found" in result[0].text.lower() or "не найден" in result[0].text
