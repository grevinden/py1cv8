"""py1cv8 — MCP server for 1C SQL access with metadata understanding.

Usage:
  python -m py1cv8               # BSL extraction (legacy)
  python -m py1cv8 mcp           # Run MCP server for LLM
  python -m py1cv8 schema [db]   # Print schema summary
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) >= 2:
        mode = sys.argv[1].lower()
        if mode == "mcp":
            from py1cv8.bootstrap import run_mcp
            run_mcp()
            return
        elif mode == "schema":
            dbname = sys.argv[2] if len(sys.argv) >= 3 else "MessageCenter"
            from py1cv8.bootstrap import run_schema_summary
            run_schema_summary(dbname)
            return
        else:
            print(f"Unknown: {mode}")
            print("Usage: python -m py1cv8 [mcp|schema <db>]")

    from py1cv8.bootstrap import run_extraction_pipeline
    run_extraction_pipeline()


if __name__ == "__main__":
    main()
