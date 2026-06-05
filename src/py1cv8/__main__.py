"""Entry point: delegates to Typer CLI."""

from __future__ import annotations

import sys

import typer

from py1cv8.agent_prompt import AGENT_PROMPT
from py1cv8.cli import app

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        typer.echo(AGENT_PROMPT)
    else:
        app()
