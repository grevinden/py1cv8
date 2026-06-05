"""Find metadata objects by keyword in tech_name or display_names."""

from __future__ import annotations

from py1cv8.context import build_llm_context


def find_objects(
    db_url: str,
    keyword: str,
    limit: int = 50,
) -> list[dict]:
    """Search metadata objects whose tech_name or display_name contains *keyword*.

    Returns filtered list of object dicts (same schema as ``context`` output).
    """
    ctx = build_llm_context(db_url)
    keyword_lower = keyword.lower()

    results: list[dict] = []
    for obj in ctx["objects"]:
        tech_name = obj.get("tech_name") or ""
        display_names = obj.get("display_names") or {}

        if keyword_lower in tech_name.lower():
            results.append(obj)
            if len(results) >= limit:
                break
            continue

        for name in display_names.values():
            if keyword_lower in name.lower():
                results.append(obj)
                if len(results) >= limit:
                    break
                break

        if len(results) >= limit:
            break

    return results
