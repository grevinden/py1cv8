"""BSL (1C:Enterprise) code detection and name extraction.

Responsibilities:
  - BSL keyword detection
  - Module name extraction from blob content
"""

from __future__ import annotations

import re

_BSL_KEYWORDS: tuple[str, ...] = ("Процедура", "Функция", "//", "Возврат", "Если")


def has_bsl_keywords(txt: str) -> bool:
    """Check if text contains BSL code keywords in first 1000 chars."""
    return any(kw in txt[:1000] for kw in _BSL_KEYWORDS)


def extract_name_from_code(code: str) -> tuple[str | None, str | None]:
    """Try to get module name from code content.

    Looks for:
      - Inter-module calls like ModuleName.Function()
      - Function/procedure signatures that look like module names
      - Quoted CamelCase strings (Cyrillic or Latin)
    """
    path_match = re.search(r"//\s*OneScript:\s.*?/([\wА-Яа-яЁё]+)\.os", code)
    if path_match:
        return path_match.group(1), None

    lines = code.splitlines()[:50]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        quoted = re.findall(r'"([А-Яа-яЁёA-Z][\wА-Яа-яЁё]{3,60})"', stripped)
        for q in quoted:
            if len(q) > 2 and not any(
                skip in q.lower()
                for skip in (
                    "object", "error", "not found", "invalid",
                    "формат", "значение", "параметр",
                )
            ):
                return q, None

    func_names = re.findall(
        r"(?:Процедура|Функция)\s+([А-Яа-яЁёA-Z][\w]{4,60})\(", code,
    )
    if func_names:
        return func_names[0], None

    return None, None
