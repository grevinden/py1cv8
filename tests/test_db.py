"""Tests for database access module."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import py1cv8.db
from py1cv8.db import (
    _dsn,
    _engines,
    _sessions,
    get_engine,
    get_session,
    session_scope,
    set_base_url,
)


def test_dsn_default() -> None:
    dsn = _dsn("testdb")
    assert dsn.endswith("/testdb")


def test_set_base_url_clears_caches() -> None:
    _orig_url = py1cv8.db._base_url
    _engines["_test"] = "dummy"
    _sessions["_test"] = "dummy"  # type: ignore[assignment]
    set_base_url("postgresql+psycopg2://other:pass@otherhost:5432")
    assert "_test" not in _engines
    assert "_test" not in _sessions
    assert not py1cv8.db._base_url.endswith(":5433")
    assert py1cv8.db._base_url == "postgresql+psycopg2://other:pass@otherhost:5432"
    # Restore original URL before it breaks other tests
    set_base_url(_orig_url)


def test_get_engine_creates_and_caches() -> None:
    _engines.clear()
    _sessions.clear()
    eng = get_engine("test_get_engine")
    assert isinstance(eng, Engine)
    assert "test_get_engine" in _engines
    assert _engines["test_get_engine"] is eng


def test_get_engine_reuses() -> None:
    _engines.clear()
    eng1 = get_engine("test_reuse")
    eng2 = get_engine("test_reuse")
    assert eng1 is eng2


def test_get_session_creates_and_caches() -> None:
    _engines.clear()
    _sessions.clear()
    sess = get_session("test_get_session")
    assert isinstance(sess, Session)
    assert "test_get_session" in _sessions


def test_get_session_reuses() -> None:
    _engines.clear()
    _sessions.clear()
    sess1 = get_session("test_get_session_reuse")
    sess2 = get_session("test_get_session_reuse")
    assert sess1 is not sess2


def test_session_scope_context_manager() -> None:
    _engines.clear()
    _sessions.clear()
    with session_scope("test_scope") as sess:
        assert isinstance(sess, Session)
    # Session should be closed after scope exit; close() is a no-op if already
    sess.close()  # should not raise


def test_session_scope_closes_on_error() -> None:
    _engines.clear()
    _sessions.clear()
    with session_scope("test_scope_error") as sess:
        pass
    sess.close()  # should not raise
