"""Tests for CLI helpers."""

from __future__ import annotations

import pytest

from py1cv8.cli import _parse_db_url


def test_parse_db_url_standard() -> None:
    base, dbname = _parse_db_url("postgresql+psycopg2://user:pass@host:5433/mydb")
    assert dbname == "mydb"
    assert base == "postgresql+psycopg2://user:pass@host:5433"


def test_parse_db_url_no_credentials() -> None:
    base, dbname = _parse_db_url("postgresql+psycopg2://localhost:5433/testdb")
    assert dbname == "testdb"
    assert base == "postgresql+psycopg2://localhost:5433"


def test_parse_db_url_no_port() -> None:
    base, dbname = _parse_db_url("postgresql+psycopg2://localhost/mydb")
    assert dbname == "mydb"
    assert base == "postgresql+psycopg2://localhost"


def test_parse_db_url_nested_path() -> None:
    base, dbname = _parse_db_url("postgresql+psycopg2://host:5433/schema/mydb")
    assert dbname == "mydb"
    assert "schema" not in base


def test_parse_db_url_via_socket() -> None:
    base, dbname = _parse_db_url("postgresql+psycopg2:///runsocket?host=/var/run")
    assert dbname == "runsocket"


def test_parse_db_url_no_path_raises() -> None:
    with pytest.raises(ValueError, match="Database URL must include a path"):
        _parse_db_url("postgresql+psycopg2://user:pass@host:5433")


def test_parse_db_url_empty_path_raises() -> None:
    with pytest.raises(ValueError, match="Database URL must include a path"):
        _parse_db_url("postgresql+psycopg2://user:pass@host:5433/")
