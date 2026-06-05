"""Centralised stdout/stderr output — UTF-8 JSON / text via typer.echo.

Typer's ``echo`` automatically detects pipe vs terminal context and
handles encoding correctly (unlike raw ``print`` which can choke on
cp1251/cp866 when redirecting ``> file``).

Usage:
    from py1cv8.output import print_json, print_text, ensure_utf8

    ensure_utf8()           # called once at startup
    print_json({"key": "значение"}, pretty=True)
    print_text("Hello, мир")
"""

from __future__ import annotations

import contextlib
import json
import sys

import typer

_UTF8_SETUP_DONE: bool = False


def ensure_utf8() -> None:
    """Ensure sys.stdout and sys.stderr can handle UTF-8.

    Uses ``reconfigure`` (Python 3.7+).
    Idempotent — safe to call multiple times.
    """
    global _UTF8_SETUP_DONE
    if _UTF8_SETUP_DONE:
        return

    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8")

    _UTF8_SETUP_DONE = True


def print_json(obj: object, *, pretty: bool = False) -> None:
    """Print *obj* as JSON to stdout via typer.echo (UTF-8).

    Parameters
    ----------
    obj : object
        Any JSON-serializable object.
    pretty : bool
        If True, indent output by 2 spaces.
    """
    from py1cv8.json_encoder import default as json_default

    indent = 2 if pretty else None
    text = json.dumps(obj, indent=indent, ensure_ascii=False, default=json_default)
    typer.echo(text)


def print_text(text: str) -> None:
    """Print *text* to stdout via typer.echo.

    Parameters
    ----------
    text : str
        Text to print (must be str, not bytes).
    """
    typer.echo(text)
