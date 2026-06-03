"""Tests for bootstrap composition root."""

from __future__ import annotations

import py1cv8.bootstrap
from py1cv8.bootstrap import (
    _get_providers,
    _Providers,
    create_mcp_loader,
    create_schema_loader,
    run_schema_summary,
)
from py1cv8.db import PgDatabaseProvider
from py1cv8.dbnames import DBNamesProviderImpl
from py1cv8.metadata_binary import ConfigMetadataProvider
from py1cv8.metadata_xml import XmlMetadataProviderImpl
from py1cv8.relationships import RelationshipBuilderImpl
from py1cv8.schema import SchemaLoader

_BASE_URL = "postgresql+psycopg2://postgres:qwaseD12@localhost:5433"


def test_providers_lazy_init() -> None:
    p = _Providers(_BASE_URL)
    # All providers start as None
    assert p._db is None
    assert p._meta is None
    assert p._xml is None
    assert p._dbnames is None
    assert p._rels is None

    # Access each to trigger lazy init
    db = p.db
    assert isinstance(db, PgDatabaseProvider)
    assert p._db is db

    meta = p.metadata
    assert isinstance(meta, ConfigMetadataProvider)
    assert p._meta is meta

    xml = p.xml
    assert isinstance(xml, XmlMetadataProviderImpl)
    assert p._xml is xml

    dbnames = p.dbnames
    assert isinstance(dbnames, DBNamesProviderImpl)
    assert p._dbnames is dbnames

    rels = p.relationships
    assert isinstance(rels, RelationshipBuilderImpl)
    assert p._rels is rels


def test_providers_lazy_caches() -> None:
    p = _Providers(_BASE_URL)
    assert p.db is p.db
    assert p.metadata is p.metadata
    assert p.xml is p.xml
    assert p.dbnames is p.dbnames
    assert p.relationships is p.relationships


def test_get_providers_global() -> None:
    py1cv8.bootstrap._providers = None
    p1 = _get_providers(_BASE_URL)
    p2 = _get_providers(_BASE_URL)
    assert p1 is p2


def test_create_schema_loader() -> None:
    py1cv8.bootstrap._providers = None
    loader = create_schema_loader(_BASE_URL)
    assert isinstance(loader, SchemaLoader)
    reg = loader("test")
    assert reg.dbname == "test"
    assert len(reg.tables) > 0


def test_create_mcp_loader() -> None:
    py1cv8.bootstrap._providers = None
    loader = create_mcp_loader(_BASE_URL)
    assert isinstance(loader, SchemaLoader)
    reg = loader("test")
    assert reg.dbname == "test"


def test_run_schema_summary() -> None:
    py1cv8.bootstrap._providers = None
    result = run_schema_summary("test", _BASE_URL)
    assert isinstance(result, dict)
    assert result["database"] == "test"
    assert result["total_tables"] > 0
