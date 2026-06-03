"""Typer CLI for py1cv8 — all DB parameters visible via --help."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

import typer

from py1cv8.bootstrap import run_mcp, run_schema_summary

app = typer.Typer(
    name="py1cv8",
    help="MCP server for 1C SQL access with metadata understanding",
    no_args_is_help=True,
)


def _parse_db_url(db_url: str) -> tuple[str, str]:
    """Split ``db_url`` into ``(base_url, dbname)``.

    The full URL is parsed: the last path component becomes *dbname*,
    the rest is the *base_url* (reconstructed without the path).
    """
    parsed = urlparse(db_url)
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(
            f"Database URL must include a path (database name): {db_url}"
        )
    dbname = path.rsplit("/", 1)[-1]
    base_url = parsed._replace(path="").geturl()
    return base_url, dbname


@app.command()
def mcp(
    db_url: Annotated[
        str,
        typer.Option(
            ...,
            "--db-url",
            envvar="PY1CV8_DB_URL",
            help="Base SQLAlchemy database URL (without database name, e.g. postgresql+psycopg2://user:pass@host:5433)",
            show_envvar=True,
        ),
    ],
) -> None:
    """Run the MCP server for LLM integration."""
    run_mcp(db_url)


@app.command()
def schema(
    db_url: Annotated[
        str,
        typer.Option(
            ...,
            "--db-url",
            envvar="PY1CV8_DB_URL",
            help="Full SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5433/dbname)",
            show_envvar=True,
        ),
    ],
) -> None:
    """Print schema summary for a database."""
    base_url, dbname = _parse_db_url(db_url)
    run_schema_summary(dbname, base_url)


if __name__ == "__main__":
    app()
