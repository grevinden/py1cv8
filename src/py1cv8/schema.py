"""Schema discovery — lazy reflection of 1C databases.

Orchestrates DBNames parsing, information_schema queries, config metadata,
and XML metadata into a unified SchemaRegistry — all via SQLAlchemy ORM.

Depends ONLY on contracts (contracts.*), NOT on concrete implementations.
Dependencies are injected via constructor. Defaults use module-level bootstrap
for backward compatibility.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from py1cv8.config import (
    COMPANION_TABLE_PARENT,
    COMPANION_TABLE_TYPES,
    DBNAMES_CATEGORY_MAP,
    EXPORT_DIR,
    MAIN_TABLE_TYPES,
    SERVICE_TABLE_TYPES,
    SUB_TABLE_TYPES,
    TYPE_MAP,
)
from py1cv8.config_versions import parse_config_dump_info
from py1cv8.contracts.database import DatabaseSessionProvider
from py1cv8.contracts.dbnames import DBNamesProvider
from py1cv8.contracts.metadata import MetadataProvider
from py1cv8.contracts.relationships import RelationshipBuilder
from py1cv8.contracts.xml_metadata import XmlMetadataProvider as XmlMetadataProviderContract
from py1cv8.dbnames import DBNamesEntry, generate_db_name, parse_dbnames_text

if False:
    pass
from py1cv8.models import (
    InformationSchemaColumn,
    InformationSchemaKeyColumnUsage,
    InformationSchemaTableConstraint,
    Params,
)

# ── Default provider factories (lazy, for backward compat) ───────────────


def _default_db_provider() -> DatabaseSessionProvider:
    from py1cv8.db import PgDatabaseProvider
    return PgDatabaseProvider("postgresql+psycopg2://postgres:qwaseD12@localhost:5433")


def _default_metadata_provider() -> MetadataProvider:
    from py1cv8.metadata_binary import ConfigMetadataProvider
    return ConfigMetadataProvider(_default_db_provider())


def _default_xml_provider() -> XmlMetadataProviderContract:
    from py1cv8.metadata_xml import XmlMetadataProviderImpl
    return XmlMetadataProviderImpl()


def _default_dbnames_provider() -> DBNamesProvider:
    from py1cv8.dbnames import DBNamesProviderImpl
    return DBNamesProviderImpl()


def _default_relationship_builder() -> RelationshipBuilder:
    from py1cv8.relationships import build_relationships

    class _Builder:
        """Adapter: wraps module-level build_relationships as a RelationshipBuilder."""
        def build_relationships(
            self,
            tables: Mapping[str, object],
            entries: list[dict],
            main_types: frozenset[str],
        ) -> dict[str, list[dict]]:
            from py1cv8.schema import ObjectInfo, ServiceTableInfo
            typed_tables: dict[str, ObjectInfo | ServiceTableInfo] = {
                k: v for k, v in tables.items()
                if isinstance(v, (ObjectInfo, ServiceTableInfo))
            }
            from py1cv8.dbnames import DBNamesEntry
            parsed_entries: list[DBNamesEntry] = [
                e if isinstance(e, DBNamesEntry) else DBNamesEntry(
                    uuid=e.get("uuid", ""),
                    type_name=e.get("type_name", ""),
                    number=e.get("number", 0),
                )
                for e in entries
            ]
            return build_relationships(typed_tables, parsed_entries, main_types)

    return _Builder()


# ── Models ──────────────────────────────────────────────────────────────


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    is_pk: bool
    ordinal: int


@dataclass
class ObjectInfo:
    """A 1C metadata object mapped to its DB tables."""

    uuid: str
    tech_name: str
    display_ru: str
    type_num: int | None
    category: str
    main_table: str = ""
    table_number: int = 0
    columns: list[ColumnInfo] = field(default_factory=list)
    sub_tables: dict[str, str] = field(default_factory=dict)
    referenced_by: list[str] = field(default_factory=list)
    metadata_xml: Any | None = None  # ObjectMetadata | None


@dataclass
class ServiceTableInfo:
    """A system/service DB table without 1C metadata object."""

    db_name: str
    description: str = ""
    columns: list[ColumnInfo] = field(default_factory=list)


# ── Schema reader helpers ────────────────────────────────────────────────


def _read_information_schema(
    db_provider: DatabaseSessionProvider,
    dbname: str,
) -> dict[str, list[ColumnInfo]]:
    """Read all _* table columns from information_schema via ORM."""
    with db_provider.session_scope(dbname) as session:
        cols_q = select(InformationSchemaColumn).where(
            InformationSchemaColumn.table_name.startswith("_", autoescape=True),
            InformationSchemaColumn.table_schema == "public",
        ).order_by(
            InformationSchemaColumn.table_name,
            InformationSchemaColumn.ordinal_position,
        )
        all_cols = session.scalars(cols_q).all()

        tables: dict[str, list[ColumnInfo]] = {}
        for row in all_cols:
            tname = row.table_name
            if tname not in tables:
                tables[tname] = []
            tables[tname].append(ColumnInfo(
                name=row.column_name,
                data_type=row.data_type or "unknown",
                nullable=row.is_nullable == "YES",
                is_pk=False,
                ordinal=row.ordinal_position,
            ))

        try:
            pk_q = (
                select(
                    InformationSchemaKeyColumnUsage.table_name,
                    InformationSchemaKeyColumnUsage.column_name,
                )
                .join(
                    InformationSchemaTableConstraint,
                    InformationSchemaTableConstraint.constraint_name
                    == InformationSchemaKeyColumnUsage.constraint_name,
                )
                .where(
                    InformationSchemaTableConstraint.constraint_type == "PRIMARY KEY",
                    InformationSchemaTableConstraint.table_schema == "public",
                    InformationSchemaKeyColumnUsage.table_schema == "public",
                    InformationSchemaKeyColumnUsage.table_name.startswith("_", autoescape=True),
                )
            )
            pk_rows = session.execute(pk_q).all()
            pk_cols: dict[str, set[str]] = defaultdict(set)
            for pk_row in pk_rows:
                pk_cols[pk_row.table_name].add(pk_row.column_name)
            for tname, cols in tables.items():
                for col in cols:
                    if col.name in pk_cols.get(tname, set()):
                        col.is_pk = True
        except Exception:
            pass

        return tables


def _read_dbnames(
    db_provider: DatabaseSessionProvider,
    dbname: str,
) -> list[DBNamesEntry]:
    """Read DBNames from params table via ORM."""
    with db_provider.session_scope(dbname) as session:
        q = select(Params).where(
            (Params.filename == "DBNames") | Params.filename.like("DBNames-Ext%"),
        ).order_by(Params.filename)

        all_entries: list[DBNamesEntry] = []
        for row in session.scalars(q):
            if not row.binarydata:
                continue
            import zlib
            try:
                dec = zlib.decompress(bytes(row.binarydata), -15)
            except zlib.error:
                continue
            text = dec.decode("utf-8-sig", errors="replace")
            all_entries.extend(parse_dbnames_text(text))
        return all_entries


# ── Schema registry ─────────────────────────────────────────────────────


class SchemaRegistry:
    """Lazy-loaded schema registry for a 1C database.

    Depends on injected providers that satisfy contracts.
    If providers are not injected, defaults are used (backward compat).
    """

    def __init__(
        self,
        dbname: str,
        *,
        db_provider: DatabaseSessionProvider | None = None,
        metadata_provider: MetadataProvider | None = None,
        xml_provider: XmlMetadataProviderContract | None = None,
        dbnames_provider: DBNamesProvider | None = None,
        relationship_builder: RelationshipBuilder | None = None,
    ) -> None:
        self.dbname = dbname
        self._db = db_provider or _default_db_provider()
        self._meta = metadata_provider or _default_metadata_provider()
        self._xml = xml_provider or _default_xml_provider()
        self._dbnames = dbnames_provider or _default_dbnames_provider()
        self._rels = relationship_builder or _default_relationship_builder()
        self._loaded = False
        self.objects: dict[str, ObjectInfo] = {}
        self.tables: dict[str, ObjectInfo | ServiceTableInfo] = {}
        self.dbnames_entries: list[DBNamesEntry] = []
        self.relationships: dict[str, list[dict]] = {}
        self.config_versions: dict[str, str] = {}
        self.metadata_map: dict[str, dict] = {}

    def lazy_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._do_load()

    def _do_load(self) -> None:
        # 1. Read DBNames via injected DB provider
        all_entries = _read_dbnames(self._db, self.dbname)
        self.dbnames_entries = all_entries

        # 2. Read information_schema via injected DB provider
        all_columns = _read_information_schema(self._db, self.dbname)

        # 3. Read config metadata via injected metadata provider
        meta_map = self._meta.build_metadata_map(self.dbname)
        self.metadata_map = meta_map

        # 4. Index DBNames entries (4-way classification)
        main_entries: list[DBNamesEntry] = []
        sub_entries: list[DBNamesEntry] = []
        companion_entries: list[DBNamesEntry] = []
        service_entries: list[DBNamesEntry] = []

        for entry in all_entries:
            if entry.type_name in SUB_TABLE_TYPES:
                sub_entries.append(entry)
            elif entry.type_name in COMPANION_TABLE_TYPES:
                companion_entries.append(entry)
            elif (
                entry.type_name in SERVICE_TABLE_TYPES
                or entry.uuid == "00000000-0000-0000-0000-000000000000"
            ):
                service_entries.append(entry)
            else:
                main_entries.append(entry)

        # 5. Build main objects
        uuid_main: dict[str, DBNamesEntry] = {}
        num_main: dict[int, DBNamesEntry] = {}

        for entry in main_entries:
            uuid_main[entry.uuid] = entry
            if entry.type_name in MAIN_TABLE_TYPES:
                num_main[entry.number] = entry

        # 6. Build ObjectInfo from main entries
        for uuid_val, entry in uuid_main.items():
            meta = meta_map.get(uuid_val, {})
            type_num = meta.get("type_num")
            category = DBNAMES_CATEGORY_MAP.get(entry.type_name)
            if category is None:
                category = (
                    TYPE_MAP.get(type_num, entry.type_name)
                    if type_num is not None else entry.type_name
                )
            tech_name = meta.get("tech_name", "")
            display_ru = meta.get("display_names", {}).get("ru", tech_name or entry.type_name)

            db_name = generate_db_name(entry)
            if db_name is None or db_name not in all_columns:
                continue

            obj = ObjectInfo(
                uuid=uuid_val,
                tech_name=tech_name or f"{entry.type_name}_{entry.number}",
                display_ru=display_ru or tech_name or f"{entry.type_name}_{entry.number}",
                type_num=type_num,
                category=category,
                main_table=db_name,
                table_number=entry.number,
                columns=all_columns.get(db_name, []),
            )

            uuid_sub = [e for e in sub_entries if e.uuid == uuid_val]
            seen_sub_numbers: set[int] = set()
            for sub in uuid_sub:
                if sub.number in seen_sub_numbers:
                    continue
                seen_sub_numbers.add(sub.number)
                sub_db_name = generate_db_name(sub, db_name)
                if sub_db_name and sub_db_name in all_columns:
                    obj.sub_tables[sub.type_name] = sub_db_name
                    sub_obj = ObjectInfo(
                        uuid=uuid_val,
                        tech_name=f"{obj.tech_name}.{sub.type_name}",
                        display_ru=f"{obj.display_ru} ({sub.type_name})",
                        type_num=type_num,
                        category=f"{category}.{sub.type_name}",
                        main_table=sub_db_name,
                        table_number=sub.number,
                        columns=all_columns[sub_db_name],
                    )
                    self.tables[sub_db_name] = sub_obj

            # Link companion tables with the same UUID
            uuid_comp = [e for e in companion_entries if e.uuid == uuid_val]
            seen_comp_numbers: set[int] = set()
            for comp in uuid_comp:
                if comp.number in seen_comp_numbers:
                    continue
                seen_comp_numbers.add(comp.number)
                comp_parent = COMPANION_TABLE_PARENT.get(comp.type_name, entry.type_name)
                if comp_parent != entry.type_name:
                    continue
                comp_db_name = generate_db_name(comp)
                if comp_db_name and comp_db_name in all_columns:
                    obj.sub_tables[comp.type_name] = comp_db_name
                    comp_obj = ObjectInfo(
                        uuid=uuid_val,
                        tech_name=f"{obj.tech_name}.{comp.type_name}",
                        display_ru=f"{obj.display_ru} ({comp.type_name})",
                        type_num=type_num,
                        category=f"{category}.{comp.type_name}",
                        main_table=comp_db_name,
                        table_number=comp.number,
                        columns=all_columns[comp_db_name],
                    )
                    self.tables[comp_db_name] = comp_obj

            self.objects[uuid_val] = obj
            self.tables[db_name] = obj

        # 6b. Process companion entries that DON'T share a UUID with a main entry
        for comp in companion_entries:
            if comp.uuid in uuid_main:
                continue
            comp_db_name = generate_db_name(comp)
            if comp_db_name is None or comp_db_name not in all_columns:
                continue
            if comp_db_name in self.tables:
                continue
            comp_parent = COMPANION_TABLE_PARENT.get(comp.type_name, "")
            obj = ObjectInfo(
                uuid=comp.uuid,
                tech_name=f"{comp.type_name}_{comp.number}",
                display_ru=f"{comp.type_name}_{comp.number}",
                type_num=None,
                category=DBNAMES_CATEGORY_MAP.get(comp_parent, comp_parent or comp.type_name),
                main_table=comp_db_name,
                table_number=comp.number,
                columns=all_columns[comp_db_name],
            )
            self.objects[comp.uuid] = obj
            self.tables[comp_db_name] = obj

        # 7. Build service table entries
        for entry in service_entries:
            db_name = generate_db_name(entry)
            if db_name is None or db_name not in all_columns:
                continue
            if db_name in self.tables:
                continue
            svc = ServiceTableInfo(
                db_name=db_name,
                description=f"System table: {entry.type_name} (#{entry.number})",
                columns=all_columns.get(db_name, []),
            )
            self.tables[db_name] = svc

        # 8. Add remaining _* tables not in DBNames
        for db_name in all_columns:
            if db_name not in self.tables:
                svc = ServiceTableInfo(
                    db_name=db_name,
                    description="System table (not in DBNames)",
                    columns=all_columns.get(db_name, []),
                )
                self.tables[db_name] = svc

        # 9. Link XML export metadata
        if EXPORT_DIR.is_dir():
            try:
                xml_meta = self._xml.scan_export_directory()
                for obj in self.objects.values():
                    xm = xml_meta.get(obj.uuid)
                    if xm is not None:
                        obj.metadata_xml = xm
            except Exception:
                pass

        # 9b. Update display_ru from XML synonym if available
        for obj in self.objects.values():
            if obj.metadata_xml and obj.metadata_xml.synonym:
                ru = obj.metadata_xml.synonym.get("ru")
                if ru:
                    obj.display_ru = ru

        # 9c. Load config versions from ConfigDumpInfo.xml
        from contextlib import suppress
        for candidate in (
            EXPORT_DIR / "ConfigDumpInfo.xml",
            EXPORT_DIR / "test_database" / "ConfigDumpInfo.xml",
        ):
            if candidate.is_file():
                with suppress(Exception):
                    self.config_versions.update(parse_config_dump_info(candidate))

        # 10. Build relationship graph
        entries_as_dicts = [
            {"uuid": e.uuid, "type_name": e.type_name, "number": e.number}
            for e in self.dbnames_entries
        ]
        self.relationships = self._rels.build_relationships(
            self.tables, entries_as_dicts, MAIN_TABLE_TYPES,
        )

    # ── Public accessors ────────────────────────────────────────────────

    def __getitem__(self, key: str) -> ObjectInfo | ServiceTableInfo:
        self.lazy_load()
        if key in self.tables:
            return self.tables[key]
        raise KeyError(f"Table '{key}' not found in {self.dbname}")

    def __contains__(self, key: str) -> bool:
        self.lazy_load()
        return key in self.tables

    def get_object_by_uuid(self, uuid_val: str) -> ObjectInfo | None:
        self.lazy_load()
        return self.objects.get(uuid_val.lower())

    def get_object_by_table(self, db_name: str) -> ObjectInfo | ServiceTableInfo | None:
        self.lazy_load()
        return self.tables.get(db_name)

    def search(self, query: str) -> list[ObjectInfo]:
        self.lazy_load()
        q = query.lower()
        results: list[ObjectInfo] = []
        for obj in self.objects.values():
            if (
                q in obj.tech_name.lower()
                or q in obj.display_ru.lower()
                or q in obj.uuid.lower()
                or q in obj.main_table.lower()
            ):
                results.append(obj)
        return results

    def stale_uuids(self, new_versions: dict[str, str]) -> list[str]:
        """Return object UUIDs whose configVersion changed.

        Compares *new_versions* (from a fresh read of ConfigDumpInfo.xml)
        against the stored ``self.config_versions``.  Returns base UUIDs
        (without sub-ID suffix) that differ AND exist in ``self.objects``.
        """
        stale: set[str] = set()
        for full_id, new_cver in new_versions.items():
            old_cver = self.config_versions.get(full_id)
            if old_cver is None or old_cver != new_cver:
                base = full_id.split(".")[0].lower()
                if base in self.objects:
                    stale.add(base)
        return sorted(stale)

    @property
    def summary(self) -> dict:
        self.lazy_load()
        cats: dict[str, int] = {}
        for obj in self.objects.values():
            if obj.main_table:
                cats[obj.category] = cats.get(obj.category, 0) + 1

        svc_count = sum(
            1 for v in self.tables.values() if isinstance(v, ServiceTableInfo)
        )

        return {
            "database": self.dbname,
            "objects_with_tables": len(self.objects),
            "total_tables": len(self.tables),
            "service_tables": svc_count,
            "categories": dict(sorted(cats.items(), key=lambda x: -x[1])),
            "dbnames_entries": len(self.dbnames_entries),
        }


# ── Lazy singleton ─────────────────────────────────────────────────────


class SchemaLoader:
    """Lazy singleton for schema registries across databases."""

    def __init__(
        self,
        *,
        db_provider: DatabaseSessionProvider | None = None,
        metadata_provider: MetadataProvider | None = None,
        xml_provider: XmlMetadataProviderContract | None = None,
        dbnames_provider: DBNamesProvider | None = None,
        relationship_builder: RelationshipBuilder | None = None,
    ) -> None:
        self._db_provider = db_provider
        self._metadata_provider = metadata_provider
        self._xml_provider = xml_provider
        self._dbnames_provider = dbnames_provider
        self._relationship_builder = relationship_builder
        self._registries: dict[str, SchemaRegistry] = {}

    def __call__(self, dbname: str) -> SchemaRegistry:
        if dbname not in self._registries:
            reg = SchemaRegistry(
                dbname,
                db_provider=self._db_provider,
                metadata_provider=self._metadata_provider,
                xml_provider=self._xml_provider,
                dbnames_provider=self._dbnames_provider,
                relationship_builder=self._relationship_builder,
            )
            reg.lazy_load()
            self._registries[dbname] = reg
        return self._registries[dbname]

    def clear(self) -> None:
        self._registries.clear()


_loader = SchemaLoader()


def get_loader() -> SchemaLoader:
    return _loader
