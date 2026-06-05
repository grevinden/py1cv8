"""LLM agent prompt — self-contained instructions for autonomous 1C analysis.

Содержимое вынесено в ``agent_prompt.md`` рядом с этим файлом.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_FILE = Path(__file__).resolve().parent / "agent_prompt.md"

AGENT_PROMPT: str = _PROMPT_FILE.read_text(encoding="utf-8")
