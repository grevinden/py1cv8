"""Typer CLI for py1cv8 — context generation, SQL, blob, find, schema, resolve."""

from __future__ import annotations

from typing import Annotated

import typer

from py1cv8.agent_prompt import AGENT_PROMPT
from py1cv8.db import normalise_db_url
from py1cv8.output import print_json, print_text
from py1cv8.sql.orm import ConfigTable

app = typer.Typer(
    name="py1cv8",
    help="1C metadata parser + LLM context generator",
    rich_markup_mode=None,
)


@app.command()
def agent() -> None:
    """Print LLM agent prompt — instructions for autonomous 1C analysis."""
    print_text(AGENT_PROMPT)


@app.command()
def context(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5433/dbname)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    with_tables: Annotated[
        bool,
        typer.Option("--with-tables", "-t", help="Only show objects that have a physical table"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Print LLM-friendly context from 1C metadata."""
    db_url = normalise_db_url(db_url)
    from py1cv8.context import build_llm_context

    ctx = build_llm_context(db_url)
    if with_tables:
        ctx["objects"] = [o for o in ctx["objects"] if o.get("table_name")]
        ctx["object_count"] = len(ctx["objects"])
    print_json(ctx, pretty=pretty)


@app.command()
def sql(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5433/dbname)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    query: Annotated[
        str,
        typer.Argument(help="SQL query to execute"),
    ],
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Execute a read-only SQL query and print results as JSON."""
    db_url = normalise_db_url(db_url)
    from py1cv8.sql_proxy import ReadOnlyError, execute_readonly

    try:
        rows = execute_readonly(db_url, query)
        print_json(rows, pretty=pretty)
    except ReadOnlyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
async def blob(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    table: Annotated[
        ConfigTable,
        typer.Option("--table", "-t", help="Source table: config or configcas"),
    ] = "config",
    uuid: Annotated[
        str | None,
        typer.Option("--uuid", "-u", help="UUID to search for in filename"),
    ] = None,
    filename: Annotated[
        str | None,
        typer.Option("--filename", "-f", help="Filename ILIKE pattern"),
    ] = None,
    partno: Annotated[
        int | None,
        typer.Option("--partno", help="Part number filter"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max rows"),
    ] = 20,
    raw_content: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Include decompressed blob content (adds ~50KB per row)",
        ),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Fetch and decompress config blobs — inspect raw metadata format."""
    db_url = normalise_db_url(db_url)
    from py1cv8.blob_fetch import BLOB_FORMAT_DESCRIPTION, extract_metadata_blobs

    rows = await extract_metadata_blobs(
        db_url=db_url,
        table=table,
        filename=filename,
        partno=partno,
        uuid=uuid,
        limit=limit,
        raw=raw_content,
    )
    output: dict | list[dict] = {
        "blobs": rows,
        "format_description": BLOB_FORMAT_DESCRIPTION if raw_content else None,
    }
    print_json(output, pretty=pretty)


@app.command()
def find(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    keyword: Annotated[
        str,
        typer.Argument(help="Keyword to search in object names"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max results"),
    ] = 50,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Search metadata objects by name (tech_name / display_name)."""
    db_url = normalise_db_url(db_url)
    from py1cv8.find_objects import find_objects

    rows = find_objects(db_url, keyword, limit=limit)
    print_json(rows, pretty=pretty)


@app.command()
def schema(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    table_name: Annotated[
        str,
        typer.Argument(help="Table name to describe (e.g. _Reference53)"),
    ],
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Describe table structure via information_schema."""
    db_url = normalise_db_url(db_url)
    from py1cv8.schema_describe import describe_table

    rows = describe_table(db_url, table_name)
    print_json(rows, pretty=pretty)


@app.command()
def resolve(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID to resolve (with or without dashes)"),
    ],
    table_name: Annotated[
        str | None,
        typer.Argument(help="Optional table name (e.g. _Reference53)"),
    ] = None,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", hidden=True, help="Output as JSON (default)"),
    ] = False,
) -> None:
    """Resolve UUID to _Description / _Code from 1C tables."""
    db_url = normalise_db_url(db_url)
    from py1cv8.resolve_uuid import resolve_uuid

    rows = resolve_uuid(db_url, uuid, table_name=table_name)
    print_json(rows, pretty=pretty or json_output)


@app.command()
async def describe(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID of the metadata object"),
    ],
    sample_rows: Annotated[
        int,
        typer.Option("--sample-rows", "-n", help="Number of sample data rows"),
    ] = 3,
    resolve_refs: Annotated[
        bool,
        typer.Option("--resolve", "-r", help="Resolve UUID refs to names in sample data"),
    ] = False,
    no_blob: Annotated[
        bool,
        typer.Option("--no-blob", help="Skip raw blob content in output"),
    ] = False,
) -> None:
    """Describe a 1C metadata object — context + schema + blob + sample data."""
    db_url = normalise_db_url(db_url)
    from py1cv8.describe_object import describe_text

    text = await describe_text(
        db_url,
        uuid,
        sample_limit=sample_rows,
        resolve_refs=resolve_refs,
        no_blob=no_blob,
    )
    print_text(text)


@app.command()
def lookup(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID to search (with or without dashes)"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max tables to search"),
    ] = 50,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Deep search UUID across ALL database tables with _idrref."""
    db_url = normalise_db_url(db_url)
    from py1cv8.lookup_uuid import lookup_uuid

    rows = lookup_uuid(db_url, uuid, limit=limit)
    print_json(rows, pretty=pretty)


@app.command()
def tables(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    only_with_table: Annotated[
        bool,
        typer.Option("--with-table", "-t", help="Only objects that have a physical table"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Show mapping: tech_name -> physical table name for all objects."""
    db_url = normalise_db_url(db_url)
    from py1cv8.list_tables import list_tables

    rows = list_tables(db_url)
    if only_with_table:
        rows = [r for r in rows if r.get("table_name")]
    print_json(rows, pretty=pretty)


@app.command()
async def graph(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str | None,
        typer.Argument(help="UUID of the object (optional with --all)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON instead of formatted text"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON (only with --json)"),
    ] = False,
    mermaid_output: Annotated[
        bool,
        typer.Option("--mermaid", "-m", help="Output Mermaid classDiagram"),
    ] = False,
    all_flag: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show graph for ALL objects"),
    ] = False,
) -> None:
    """Show relationship graph for a 1C object — refs, owners, parents.

    Use --all to see relationships for every object at once.
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.graph import (
        build_graph,
        graph_all_mermaid,
        graph_all_text,
        graph_mermaid,
        graph_text,
    )  # fmt: skip

    if all_flag:
        if mermaid_output:
            print_text(await graph_all_mermaid(db_url))
        elif json_output:
            from py1cv8.graph import build_global_graph

            print_json(await build_global_graph(db_url), pretty=pretty)
        else:
            print_text(await graph_all_text(db_url))
    elif not uuid:
        typer.echo("Error: provide a UUID or use --all", err=True)
        raise typer.Exit(1)
    elif mermaid_output:
        print_text(await graph_mermaid(db_url, uuid))
    elif json_output:
        print_json(await build_graph(db_url, uuid), pretty=pretty)
    else:
        print_text(await graph_text(db_url, uuid))


@app.command()
def translate(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (for table name resolution)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    query: Annotated[
        str,
        typer.Argument(help="1C query text or BSL source code (see --bsl)"),
    ],
    bsl_mode: Annotated[
        bool,
        typer.Option("--bsl", "-b", help="Input is BSL code, extract queries from Запрос.Текст"),
    ] = False,
    dialect: Annotated[
        str,
        typer.Option("--dialect", "-d", help="Target SQL dialect: postgresql or mssql"),
    ] = "postgresql",
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Translate 1C query language to SQL.

    Примеры::

        py1cv8 translate "postgresql://..." "ВЫБРАТЬ Наименование ИЗ Справочник.Контрагенты"

        py1cv8 translate "postgresql://..." --bsl "Запрос.Текст = \"ВЫБРАТЬ 1\";"
    """
    db_url = normalise_db_url(db_url)
    from dataclasses import asdict

    # Build resolver from context
    from py1cv8.context import build_llm_context
    from py1cv8.query_translator import (
        extract_queries_from_bsl,
        translate_1c_query,
    )

    ctx = build_llm_context(db_url)
    table_by_name: dict[tuple[str, str], str] = {}
    for obj in ctx["objects"]:
        tn = obj.get("table_name")
        tech = obj.get("tech_name") or ""
        if tn and "." in tech:
            obj_type, obj_name = tech.split(".", 1)
            table_by_name[(obj_type, obj_name)] = tn

    def resolver(obj_type: str, obj_name: str) -> str | None:
        return table_by_name.get((obj_type, obj_name))

    try:
        if bsl_mode:
            result = extract_queries_from_bsl(query, resolver=resolver, dialect=dialect)
            output = asdict(result)
        else:
            tq = translate_1c_query(query, resolver=resolver, dialect=dialect)
            output = asdict(tq)

        print_json(output, pretty=pretty)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
