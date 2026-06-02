"""Composition root — wires contract implementations via Dependency Injection.

Every production entry point goes through this module.
Test code may bypass this and wire mocks/stubs directly.
"""

from __future__ import annotations

from py1cv8.db import PgDatabaseProvider
from py1cv8.dbnames import DBNamesProviderImpl
from py1cv8.metadata_binary import ConfigMetadataProvider
from py1cv8.metadata_xml import XmlMetadataProviderImpl
from py1cv8.relationships import RelationshipBuilderImpl
from py1cv8.schema import SchemaLoader

# ── Singleton cache ─────────────────────────────────────────────────────


class _Providers:
    """Lazy singleton container for all DI providers."""

    def __init__(self) -> None:
        self._db: PgDatabaseProvider | None = None
        self._meta: ConfigMetadataProvider | None = None
        self._xml: XmlMetadataProviderImpl | None = None
        self._dbnames: DBNamesProviderImpl | None = None
        self._rels: RelationshipBuilderImpl | None = None

    @property
    def db(self) -> PgDatabaseProvider:
        if self._db is None:
            from py1cv8.config import DB_HOST, DB_PASS, DB_PORT, DB_USER
            self._db = PgDatabaseProvider(DB_HOST, DB_PORT, DB_USER, DB_PASS)
        return self._db

    @property
    def metadata(self) -> ConfigMetadataProvider:
        if self._meta is None:
            self._meta = ConfigMetadataProvider(self.db)
        return self._meta

    @property
    def xml(self) -> XmlMetadataProviderImpl:
        if self._xml is None:
            self._xml = XmlMetadataProviderImpl()
        return self._xml

    @property
    def dbnames(self) -> DBNamesProviderImpl:
        if self._dbnames is None:
            self._dbnames = DBNamesProviderImpl()
        return self._dbnames

    @property
    def relationships(self) -> RelationshipBuilderImpl:
        if self._rels is None:
            self._rels = RelationshipBuilderImpl()
        return self._rels


_providers = _Providers()


# ── Public factories ────────────────────────────────────────────────────


def create_schema_loader() -> SchemaLoader:
    """Create a SchemaLoader wired with production providers."""
    return SchemaLoader(
        db_provider=_providers.db,
        metadata_provider=_providers.metadata,
        xml_provider=_providers.xml,
        dbnames_provider=_providers.dbnames,
        relationship_builder=_providers.relationships,
    )


def create_mcp_loader() -> SchemaLoader:
    """Alias for create_schema_loader — used by MCP server."""
    return create_schema_loader()


def run_mcp() -> None:
    """Run the MCP server with DI-wired schema loader."""
    from py1cv8.mcp_server import run
    run(schema_loader=create_schema_loader())


def run_schema_summary(dbname: str) -> dict:
    """Print and return schema summary for a database."""
    import json

    loader = create_schema_loader()
    reg = loader(dbname)
    summary = reg.summary
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
