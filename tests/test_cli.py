"""Tests for CLI helpers."""

from __future__ import annotations


def test_cli_app_invoke() -> None:
    """Direct app invocation is reachable (covers app() in __main__ block)."""
    from typer.testing import CliRunner

    from py1cv8.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_cli_commands_listed() -> None:
    """CLI has context and sql commands."""
    from typer.testing import CliRunner

    from py1cv8.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "context" in result.stdout
    assert "sql" in result.stdout
