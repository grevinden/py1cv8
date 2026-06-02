"""py1cv8 — MCP server for 1C SQL access with metadata understanding.

Usage:
  python -m py1cv8               # BSL extraction (legacy)
  python -m py1cv8 mcp           # Run MCP server for LLM
  python -m py1cv8 schema [db]   # Print schema summary
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    if len(sys.argv) >= 2:
        mode = sys.argv[1].lower()
        if mode == "mcp":
            from py1cv8.mcp_server import run
            run()
            return
        elif mode == "schema":
            dbname = sys.argv[2] if len(sys.argv) >= 3 else "MessageCenter"
            from py1cv8.schema import SchemaRegistry
            reg = SchemaRegistry(dbname)
            reg.lazy_load()
            print(json.dumps(reg.summary, ensure_ascii=False, indent=2))
            return
        else:
            print(f"Unknown: {mode}")
            print("Usage: python -m py1cv8 [mcp|schema <db>]")

    from py1cv8.extract_pipeline import main as extract_main
    extract_main()


if __name__ == "__main__":
    main()
