"""List mapping of tech_name -> physical table name for 1C objects."""

from __future__ import annotations

from py1cv8.context import build_llm_context


def list_tables(db_url: str) -> list[dict]:
    """Return list of {uuid, tech_name, display_names, type_num, category, table_name}.

    Reuses :func:`build_llm_context` to avoid duplicating
    metadata-map / DBNames logic.
    """
    ctx = build_llm_context(db_url)
    return ctx["objects"]
