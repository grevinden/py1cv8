"""Typer CLI for py1cv8 — mcp server and schema tools."""

from __future__ import annotations

import typer

from py1cv8.bootstrap import run_mcp, run_schema_summary

app = typer.Typer(
    name="py1cv8",
    help="MCP server for 1C SQL access with metadata understanding",
    no_args_is_help=True,
)


@app.command()
def mcp() -> None:
    """Run the MCP server for LLM integration."""
    run_mcp()


@app.command()
def schema(
    db: str = typer.Argument("MessageCenter", help="Database name"),
) -> None:
    """Print schema summary for a database."""
    run_schema_summary(db)


if __name__ == "__main__":
    app()
