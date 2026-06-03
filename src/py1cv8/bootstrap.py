"""Composition root — wires contract implementations via Dependency Injection.

Every production entry point goes through this module.
Test code may bypass this and wire mocks/stubs directly.
"""

from __future__ import annotations

from py1cv8.db import PgDatabaseProvider, set_base_url
from py1cv8.dbnames import DBNamesProviderImpl
from py1cv8.metadata_binary import ConfigMetadataProvider
from py1cv8.metadata_xml import XmlMetadataProviderImpl
from py1cv8.relationships import RelationshipBuilderImpl
from py1cv8.schema import SchemaLoader

# ── Singleton cache ─────────────────────────────────────────────────────


class _Providers:
    """Lazy singleton container for all DI providers."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._db: PgDatabaseProvider | None = None
        self._meta: ConfigMetadataProvider | None = None
        self._xml: XmlMetadataProviderImpl | None = None
        self._dbnames: DBNamesProviderImpl | None = None
        self._rels: RelationshipBuilderImpl | None = None

    @property
    def db(self) -> PgDatabaseProvider:
        if self._db is None:
            self._db = PgDatabaseProvider(self._base_url)
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


_providers: _Providers | None = None


def _get_providers(base_url: str) -> _Providers:
    global _providers
    if _providers is None:
        _providers = _Providers(base_url)
    return _providers


# ── Public factories ────────────────────────────────────────────────────


def create_schema_loader(base_url: str) -> SchemaLoader:
    """Create a SchemaLoader wired with production providers."""
    p = _get_providers(base_url)
    return SchemaLoader(
        db_provider=p.db,
        metadata_provider=p.metadata,
        xml_provider=p.xml,
        dbnames_provider=p.dbnames,
        relationship_builder=p.relationships,
    )


def create_mcp_loader(base_url: str) -> SchemaLoader:
    """Alias for create_schema_loader — used by MCP server."""
    set_base_url(base_url)
    return create_schema_loader(base_url)


def run_mcp(base_url: str) -> None:
    """Run the MCP server with DI-wired schema loader."""
    from py1cv8.mcp_server import run
    run(schema_loader=create_mcp_loader(base_url))


def run_schema_summary(dbname: str, base_url: str) -> dict:
    """Print and return schema summary for a database."""
    import json

    loader = create_schema_loader(base_url)
    reg = loader(dbname)
    summary = reg.summary
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
