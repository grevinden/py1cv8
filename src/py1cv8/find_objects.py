"""Find metadata objects by keyword in tech_name or display_names."""

from __future__ import annotations

import difflib

from py1cv8.context import build_llm_context


def find_objects(
    db_url: str,
    keyword: str,
    limit: int = 50,
) -> list[dict]:
    """Search metadata objects whose tech_name or display_name contains *keyword*.

    Uses substring matching first, then falls back to fuzzy matching
    (difflib.get_close_matches) if fewer than *limit* results are found.

    Returns filtered list of object dicts (same schema as ``context`` output).
    """
    ctx = build_llm_context(db_url)
    keyword_lower = keyword.lower()

    seen: set[str] = set()
    results: list[dict] = []

    # Phase 1: substring matching
    for obj in ctx["objects"]:
        obj_uuid = obj.get("uuid", "")
        tech_name = obj.get("tech_name") or ""
        display_names = obj.get("display_names") or {}

        if keyword_lower in tech_name.lower():
            if obj_uuid not in seen:
                seen.add(obj_uuid)
                results.append(obj)
            continue

        for name in display_names.values():
            if keyword_lower in name.lower():
                if obj_uuid not in seen:
                    seen.add(obj_uuid)
                    results.append(obj)
                break

        if len(results) >= limit:
            return results[:limit]

    # Phase 2: fuzzy matching (if room)
    if len(results) < limit:
        fuzzy_pool: list[tuple[str, str]] = []  # (uuid, name)
        for obj in ctx["objects"]:
            obj_uuid = obj.get("uuid", "")
            if obj_uuid in seen:
                continue
            tech = obj.get("tech_name") or ""
            if tech:
                fuzzy_pool.append((obj_uuid, tech))
            for name in (obj.get("display_names") or {}).values():
                if name:
                    fuzzy_pool.append((obj_uuid, name))

        pool_map: dict[str, str] = {}
        for uid, name in fuzzy_pool:
            if uid not in pool_map:
                pool_map[uid] = name

        fuzzy_matches = difflib.get_close_matches(
            keyword_lower,
            [v.lower() for v in pool_map.values()],
            n=limit - len(results),
            cutoff=0.4,
        )

        for obj in ctx["objects"]:
            if len(results) >= limit:
                break
            obj_uuid = obj.get("uuid", "")
            if obj_uuid in seen:
                continue
            tech = (obj.get("tech_name") or "").lower()
            display_vals = [v.lower() for v in (obj.get("display_names") or {}).values()]
            if tech in fuzzy_matches or any(v in fuzzy_matches for v in display_vals):
                seen.add(obj_uuid)
                results.append(obj)

    return results[:limit]
