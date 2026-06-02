"""Schema discovery — lazy reflection of 1C databases.

Orchestrates DBNames parsing, information_schema queries, config metadata,
and XML metadata into a unified SchemaRegistry.
"""

from __future__ import annotations

import zlib
from collections import defaultdict
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

from py1cv8.config import (
    DB_HOST,
    DB_PASS,
    DB_PORT,
    DB_USER,
    DBNAMES_CATEGORY_MAP,
    EXPORT_DIR,
    MAIN_TABLE_TYPES,
    SERVICE_TABLE_TYPES,
    SUB_TABLE_TYPES,
    TYPE_MAP,
)
from py1cv8.dbnames import DBNamesEntry, generate_db_name, parse_dbnames_text
from py1cv8.metadata_binary import build_metadata_map
from py1cv8.metadata_xml import ObjectMetadata, scan_export_directory
from py1cv8.relationships import build_relationships

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
    metadata_xml: ObjectMetadata | None = None


@dataclass
class ServiceTableInfo:
    """A system/service DB table without 1C metadata object."""

    db_name: str
    description: str = ""
    columns: list[ColumnInfo] = field(default_factory=list)


# ── Schema registry ─────────────────────────────────────────────────────


def _read_information_schema(dbname: str) -> dict[str, list[ColumnInfo]]:
    """Read all _* table columns from information_schema."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=dbname,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT table_name, column_name, data_type, "
        "       is_nullable, ordinal_position "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "AND table_name LIKE '\\_%' "
        "ORDER BY table_name, ordinal_position"
    )

    tables: dict[str, list[ColumnInfo]] = {}
    for row in cur.fetchall():
        tname = row["table_name"]
        if tname not in tables:
            tables[tname] = []
        tables[tname].append(ColumnInfo(
            name=row["column_name"],
            data_type=row["data_type"],
            nullable=row["is_nullable"] == "YES",
            is_pk=False,
            ordinal=row["ordinal_position"],
        ))

    try:
        cur.execute(
            "SELECT kcu.table_name, kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "AND tc.table_schema = 'public' "
            "AND tc.table_name LIKE '\\_%'"
        )
        pk_cols: dict[str, set[str]] = defaultdict(set)
        for row in cur.fetchall():
            pk_cols[row["table_name"]].add(row["column_name"])
        for tname, cols in tables.items():
            for col in cols:
                if col.name in pk_cols.get(tname, set()):
                    col.is_pk = True
    except Exception:
        pass

    cur.close()
    conn.close()
    return tables


def _read_config_metadata(dbname: str) -> dict[str, dict]:
    try:
        return build_metadata_map(dbname)
    except Exception:
        return {}


class SchemaRegistry:
    """Lazy-loaded schema registry for a 1C database."""

    def __init__(self, dbname: str) -> None:
        self.dbname = dbname
        self._loaded = False
        self.objects: dict[str, ObjectInfo] = {}
        self.tables: dict[str, ObjectInfo | ServiceTableInfo] = {}
        self.dbnames_entries: list[DBNamesEntry] = []
        self.relationships: dict[str, list[dict]] = {}

    def lazy_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._do_load()

    def _do_load(self) -> None:
        # 1. Read DBNames from params table
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=self.dbname,
            user=DB_USER, password=DB_PASS,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT filename, binarydata FROM params "
            "WHERE filename = 'DBNames' OR filename LIKE 'DBNames-Ext%' "
            "ORDER BY filename"
        )

        all_entries: list[DBNamesEntry] = []
        for _fname, raw in cur.fetchall():
            if not raw:
                continue
            try:
                dec = zlib.decompress(bytes(raw), -15)
            except zlib.error:
                continue
            text = dec.decode("utf-8-sig", errors="replace")
            all_entries.extend(parse_dbnames_text(text))
        cur.close()
        conn.close()

        self.dbnames_entries = all_entries

        # 2. Read information_schema
        all_columns = _read_information_schema(self.dbname)

        # 3. Read config metadata
        meta_map = _read_config_metadata(self.dbname)

        # 4. Index DBNames entries
        main_entries: list[DBNamesEntry] = []
        sub_entries: list[DBNamesEntry] = []
        service_entries: list[DBNamesEntry] = []

        for entry in all_entries:
            if entry.type_name in SUB_TABLE_TYPES:
                sub_entries.append(entry)
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

            self.objects[uuid_val] = obj
            self.tables[db_name] = obj

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
                xml_meta = scan_export_directory()
                for obj in self.objects.values():
                    xm = xml_meta.get(obj.uuid)
                    if xm is not None:
                        obj.metadata_xml = xm
            except Exception:
                pass

        # 10. Build relationship graph
        self.relationships = build_relationships(
            self.tables, self.dbnames_entries, MAIN_TABLE_TYPES,
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

    def __init__(self) -> None:
        self._registries: dict[str, SchemaRegistry] = {}

    def __call__(self, dbname: str) -> SchemaRegistry:
        if dbname not in self._registries:
            reg = SchemaRegistry(dbname)
            reg.lazy_load()
            self._registries[dbname] = reg
        return self._registries[dbname]

    def clear(self) -> None:
        self._registries.clear()


_loader = SchemaLoader()


def get_loader() -> SchemaLoader:
    return _loader
