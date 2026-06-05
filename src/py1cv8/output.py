"""Centralised stdout/stderr output — UTF-8 JSON / text via typer.echo.

Typer's ``echo`` automatically detects pipe vs terminal context and
handles encoding correctly (unlike raw ``print`` which can choke on
cp1251/cp866 when redirecting ``> file``).

Usage:
    from py1cv8.output import print_json

    print_json({"key": "значение"}, pretty=True)
"""

from __future__ import annotations

import json

import typer


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
