"""Entry point: delegates to Typer CLI."""

from __future__ import annotations

import sys

from py1cv8.agent_prompt import AGENT_PROMPT
from py1cv8.cli import app
from py1cv8.output import ensure_utf8, print_text

ensure_utf8()

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print_text(AGENT_PROMPT)
    else:
        app()
