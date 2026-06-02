"""MCP server for 1C SQL access — tools for LLM to query & understand 1C data."""

from __future__ import annotations

import dataclasses
import json
import re as _re

import psycopg2
import psycopg2.extras
from mcp.server import Server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)
from pydantic import AnyUrl

from py1cv8.config import AVAILABLE_DBS, DB_HOST, DB_PASS, DB_PORT, DB_USER
from py1cv8.schema import ObjectInfo, SchemaLoader, ServiceTableInfo

_loader = SchemaLoader()

# ── Helpers ─────────────────────────────────────────────────────────────


def _connect(dbname: str):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=dbname,
        user=DB_USER, password=DB_PASS,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _safe_sql(sql: str) -> str:
    stripped = sql.strip().lstrip("(")
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        raise ValueError("Only SELECT / WITH queries allowed (read-only mode).")
    return sql


def _serialize(val: object) -> object:
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray, memoryview)):
        n = len(val) if isinstance(val, (bytes, bytearray)) else val.nbytes
        return f"<binary {n} bytes>"
    return val


def _xml_summary(obj: ObjectInfo) -> dict:
    """Extract a human-readable summary from XML metadata."""
    xm = obj.metadata_xml
    if xm is None:
        return {}
    summary: dict = {
        "synonym": xm.synonym,
        "comment": xm.comment,
    }
    if xm.attributes:
        summary["attributes"] = sorted(
            [
                {
                    "name": a.name,
                    "synonym": a.synonym,
                    "type": a.type_info.display,
                    "indexing": a.indexing,
                    "password_mode": a.password_mode,
                    "full_text_search": a.full_text_search,
                }
                for a in xm.attributes
            ],
            key=lambda a: a["name"],
        )
    if xm.tabular_sections:
        summary["tabular_sections"] = [
            {
                "name": ts.name,
                "synonym": ts.synonym,
                "attributes": len(ts.attributes),
            }
            for ts in xm.tabular_sections
        ]
    if xm.enum_values:
        summary["enum_values"] = [
            {"name": v.name, "synonym": v.synonym} for v in xm.enum_values
        ]
    if xm.forms:
        summary["forms"] = xm.forms
    if xm.commands:
        summary["commands"] = [
            {"name": c.name, "synonym": c.synonym, "modifies_data": c.modifies_data}
            for c in xm.commands
        ]
    if xm.generated_types:
        summary["generated_types"] = [
            {"name": g.name, "category": g.category}
            for g in xm.generated_types
        ]
    # Business logic
    biz: dict = {}
    for key in (
        "hierarchical", "hierarchy_type", "subordination_use",
        "code_length", "description_length", "code_type",
        "check_unique", "autonumbering", "posting",
        "number_type", "number_length", "number_periodicity",
        "periodicity", "write_mode", "edit_type", "choice_mode",
        "data_lock_control_mode", "full_text_search", "data_history",
        "create_on_input", "input_by_string",
    ):
        val = getattr(xm, key, None)
        if val is not None and val != "" and val != []:
            biz[key] = val
    if biz:
        summary["business_logic"] = biz
    if xm.object_presentation:
        summary["object_presentation"] = xm.object_presentation
    if xm.list_presentation:
        summary["list_presentation"] = xm.list_presentation
    return summary


def _obj_to_dict(obj: ObjectInfo) -> dict:
    result: dict = {
        "uuid": obj.uuid,
        "tech_name": obj.tech_name,
        "display_ru": obj.display_ru,
        "type_num": obj.type_num,
        "category": obj.category,
        "main_table": obj.main_table,
        "table_number": obj.table_number,
        "columns": len(obj.columns),
        "sub_tables": obj.sub_tables,
    }
    xs = _xml_summary(obj)
    if xs:
        result["metadata"] = xs
    return result


def _svc_to_dict(svc: ServiceTableInfo) -> dict:
    return {"table": svc.db_name, "description": svc.description, "columns": len(svc.columns)}


def _columns_to_dicts(info: ObjectInfo | ServiceTableInfo) -> list[dict]:
    return [
        {"name": c.name, "type": c.data_type, "nullable": c.nullable, "pk": c.is_pk}
        for c in info.columns
    ]


# ── Create server ───────────────────────────────────────────────────────

server = Server("py1cv8")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="query",
            description=f"Execute read-only SQL SELECT. Available DBs: {', '.join(AVAILABLE_DBS)}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {"type": "string", "enum": AVAILABLE_DBS},
                    "sql": {"type": "string", "description": "SELECT SQL"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["dbname", "sql"],
            },
        ),
        Tool(
            name="schema",
            description="Describe a table or list all tables with their 1C object mapping.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {"type": "string", "enum": AVAILABLE_DBS},
                    "table": {"type": "string", "description": "Table name (optional)"},
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="metadata",
            description="Browse 1C metadata objects and their DB mappings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {"type": "string", "enum": AVAILABLE_DBS},
                    "uuid": {"type": "string"},
                    "category": {"type": "string"},
                    "search": {"type": "string"},
                },
                "required": ["dbname"],
            },
        ),
        Tool(
            name="analyze",
            description="Full business+technical analysis of a 1C object or table.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dbname": {"type": "string", "enum": AVAILABLE_DBS},
                    "name": {
                        "type": "string",
                        "description": "Table name, tech_name, or display name",
                    },
                },
                "required": ["dbname", "name"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    dbname = arguments.get("dbname", "")

    if name == "query":
        return await _query(dbname, arguments)
    elif name == "schema":
        return await _schema(dbname, arguments)
    elif name == "metadata":
        return await _metadata(dbname, arguments)
    elif name == "analyze":
        return _analyze(dbname, arguments)
    raise ValueError(f"Unknown tool: {name}")


# ── Tool implementations ────────────────────────────────────────────────


async def _query(dbname: str, args: dict) -> list[TextContent]:
    sql = args.get("sql", "").strip()
    limit = min(args.get("limit", 100), 1000)

    try:
        _safe_sql(sql)
    except ValueError as e:
        return [TextContent(type="text", text=str(e))]

    safe_sql = f"SELECT * FROM ({sql}) AS _q LIMIT {limit}"

    conn = _connect(dbname)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(safe_sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        data = {
            "columns": cols,
            "rows": [{c: _serialize(r[c]) for c in cols} for r in rows],
            "row_count": len(rows),
        }
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    finally:
        conn.close()


async def _schema(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    table_name = args.get("table", "")

    if table_name:
        info = reg.get_object_by_table(table_name)
        if not info:
            return [TextContent(type="text", text=f"Table '{table_name}' not found.")]
        base = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
        base["columns"] = _columns_to_dicts(info)
        base["column_count"] = len(info.columns)
        return [TextContent(type="text", text=json.dumps(base, ensure_ascii=False, indent=2))]
    else:
        cats: dict[str, list[str]] = {}
        for tname, info in sorted(reg.tables.items()):
            cat = info.category if isinstance(info, ObjectInfo) else "System"
            cats.setdefault(cat, []).append(
                f"{tname} ({info.tech_name if isinstance(info, ObjectInfo) else info.db_name})"
            )
        data = {"database": dbname, "total_tables": len(reg.tables), "by_category": cats}
        return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


async def _metadata(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    uuid_filter = (args.get("uuid") or "").lower()
    category_filter = (args.get("category") or "").lower()
    search_q = (args.get("search") or "").lower()

    if not uuid_filter and not category_filter and not search_q:
        text = json.dumps(reg.summary, ensure_ascii=False, indent=2)
        return [TextContent(type="text", text=text)]

    matched: list[dict] = []
    for obj in reg.objects.values():
        if uuid_filter and uuid_filter not in obj.uuid:
            continue
        if category_filter and category_filter not in obj.category.lower():
            continue
        if search_q and (
            search_q not in obj.tech_name.lower()
            and search_q not in obj.display_ru.lower()
        ):
            continue
        matched.append(_obj_to_dict(obj))

    return [TextContent(
        type="text",
        text=json.dumps({"count": len(matched), "objects": matched}, ensure_ascii=False, indent=2),
    )]


def _xml_full(obj: ObjectInfo) -> dict | None:
    """Full XML metadata detail for analyze."""
    xm = obj.metadata_xml
    if xm is None:
        return None
    result = {}
    for f in dataclasses.fields(xm):
        val = getattr(xm, f.name)
        if val is not None and val != "" and val != []:
            if f.name == "attributes":
                result[f.name] = [
                    {
                        "name": a.name,
                        "synonym": a.synonym,
                        "type": a.type_info.display,
                        "type_raw": a.type_info.types,
                        "qualifiers": {
                            k: v for k, v in dataclasses.asdict(a.type_info.qualifiers).items()
                            if v is not None
                        },
                        "comment": a.comment,
                        "indexing": a.indexing,
                        "full_text_search": a.full_text_search,
                        "password_mode": a.password_mode,
                        "multiline": a.multiline,
                    }
                    for a in val
                ]
            elif f.name == "tabular_sections":
                result[f.name] = [
                    {
                        "name": ts.name,
                        "synonym": ts.synonym,
                        "attributes": [
                            {
                                "name": a.name,
                                "type": a.type_info.display,
                            }
                            for a in ts.attributes
                        ],
                        "generated_types": [
                            {"name": g.name, "category": g.category}
                            for g in ts.generated_types
                        ],
                    }
                    for ts in val
                ]
            elif f.name == "enum_values":
                result[f.name] = [
                    {"name": v.name, "synonym": v.synonym} for v in val
                ]
            elif f.name == "commands":
                result[f.name] = [
                    {
                        "name": c.name,
                        "synonym": c.synonym,
                        "comment": c.comment,
                        "modifies_data": c.modifies_data,
                        "representation": c.representation,
                    }
                    for c in val
                ]
            elif f.name == "generated_types":
                result[f.name] = [
                    {"name": g.name, "category": g.category}
                    for g in val
                ]
            elif f.name in ("forms", "templates", "synonym", "comment"):
                result[f.name] = val
            elif f.name in ("object_presentation", "list_presentation", "explanation"):
                if val:
                    result[f.name] = val
            elif f.name in (
                "hierarchical", "hierarchy_type", "subordination_use",
                "code_length", "description_length", "code_type",
                "check_unique", "autonumbering", "posting",
                "number_type", "number_length", "number_periodicity",
                "periodicity", "write_mode", "edit_type", "choice_mode",
                "data_lock_control_mode", "full_text_search", "data_history",
                "create_on_input", "input_by_string", "default_presentation",
                "quick_choice", "numerator",
            ):
                result[f.name] = val
    return result if result else None


def _analyze(dbname: str, args: dict) -> list[TextContent]:
    reg = _loader(dbname)
    name = (args.get("name") or "").lower()

    if not name:
        return [TextContent(type="text", text="Provide a name to analyze.")]

    candidates: list[dict] = []
    for tname, info in reg.tables.items():
        if name not in tname.lower():
            if isinstance(info, ObjectInfo):
                if (
                    name not in info.tech_name.lower()
                    and name not in info.display_ru.lower()
                    and name not in info.uuid.lower()
                ):
                    continue
            else:
                continue

        base = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
        base["columns"] = _columns_to_dicts(info)
        if isinstance(info, ObjectInfo) and info.main_table in reg.relationships:
            base["references"] = reg.relationships[info.main_table]
        if isinstance(info, ObjectInfo) and info.metadata_xml is not None:
            xf = _xml_full(info)
            if xf:
                base["metadata_detail"] = xf
        candidates.append(base)

    if not candidates:
        return [TextContent(type="text", text=f"No results for '{args.get('name')}'.")]

    return [TextContent(
        type="text",
        text=json.dumps(
            {"count": len(candidates), "objects": candidates},
            ensure_ascii=False, indent=2,
        ),
    )]


# ── Resources ───────────────────────────────────────────────────────────


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    resources: list[Resource] = []
    for dbname in AVAILABLE_DBS:
        reg = _loader(dbname)
        for tname, info in reg.tables.items():
            label = info.tech_name if isinstance(info, ObjectInfo) else info.db_name
            desc = info.display_ru if isinstance(info, ObjectInfo) else info.description
            resources.append(Resource(
                uri=AnyUrl(f"1c://{dbname}/tables/{tname}"),
                name=f"{tname} ({label})",
                description=desc,
                mimeType="application/json",
            ))
    return resources


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    m = _re.match(r"1c://([^/]+)/tables/(.+)", uri)
    if not m:
        raise ValueError(f"Unknown resource: {uri}")
    dbname, tname = m.group(1), m.group(2)
    reg = _loader(dbname)
    info = reg.get_object_by_table(tname)
    if not info:
        raise ValueError(f"Table {tname} not found.")

    result = _obj_to_dict(info) if isinstance(info, ObjectInfo) else _svc_to_dict(info)
    result["columns"] = _columns_to_dicts(info)
    if isinstance(info, ObjectInfo) and info.main_table in reg.relationships:
        result["references"] = reg.relationships[info.main_table]
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Run ─────────────────────────────────────────────────────────────────


def run() -> None:
    import asyncio

    from mcp.server.stdio import stdio_server

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    run()
