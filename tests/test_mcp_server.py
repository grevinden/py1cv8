"""E2E integration tests for MCP server — tests tools against a real DB."""

from __future__ import annotations

import json

import pytest

from py1cv8.bootstrap import create_schema_loader
from py1cv8.mcp_server import (
    _analyze_object,
    _build_db_overview,
    _get_schema,
    _run_sql,
    _search_metadata,
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


# ── error handling ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_invalid_db() -> None:
    with pytest.raises(Exception, match=r"Unknown database|could not translate|does not exist"):
        await _get_schema("invalid_db", {})
