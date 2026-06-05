"""Database access via SQLAlchemy ORM — engine, session factory, helpers.

All database operations MUST go through this module.
No raw psycopg2 connections allowed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import PostgresDsn
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engines: dict[str, Engine] = {}
_sessions: dict[str, sessionmaker] = {}
_base_url: str = "postgresql+psycopg2://postgres:qwaseD12@localhost:5433"


def normalise_db_url(db_url: str) -> str:
    """Normalise PostgreSQL URL aliases.

    SQLAlchemy uses ``postgresql://`` as the canonical scheme.
    The ``postgres://`` alias is deprecated — replace it transparently.
    """
    return db_url.replace("postgres://", "postgresql://", 1)


def is_postgres_url(db_url: str) -> bool:
    """Check if the URL points to a PostgreSQL database."""
    return "postgresql" in db_url or "postgres" in db_url


def quote_ident(name: str, db_url: str) -> str:
    """Quote an identifier for use in SQL queries.

    PostgreSQL uses double quotes, MSSQL uses square brackets.
    This prevents case-folding and reserved-word issues with 1C identifiers.
    """
    if is_postgres_url(db_url):
        return f'"{name}"'
    return f"[{name}]"


def set_base_url(url: PostgresDsn | str) -> None:
    """Set the base database URL (without database name).

    Must be called before any ``get_engine`` / ``get_session`` call.
    """
    global _base_url
    # Clear cached engines so they reconnect with the new URL
    _engines.clear()
    _sessions.clear()
    _base_url = str(url).rstrip("/")


def _dsn(dbname: str) -> str:
    return f"{_base_url}/{dbname}"


def get_engine(dbname: str) -> Engine:
    if dbname not in _engines:
        engine = create_engine(
            _dsn(dbname),
            pool_pre_ping=True,
            execution_options={"isolation_level": "AUTOCOMMIT"},
        )
        _engines[dbname] = engine
    return _engines[dbname]


def get_session(dbname: str) -> Session:
    """Create a new read-only ORM session for the given database."""
    if dbname not in _sessions:
        _sessions[dbname] = sessionmaker(bind=get_engine(dbname))
    return _sessions[dbname]()


@contextmanager
def session_scope(dbname: str) -> Iterator[Session]:
    """Context manager that yields a session and closes it on exit."""
    session = get_session(dbname)
    try:
        yield session
    finally:
        session.close()


class PgDatabaseProvider:
    """Read-only database provider via SQLAlchemy.

    Satisfies: contracts.database.DatabaseSessionProvider
    """

    def __init__(self, base_url: PostgresDsn | str) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._engines: dict[str, Engine] = {}
        self._sessions: dict[str, sessionmaker] = {}

    def _dsn(self, dbname: str) -> str:
        return f"{self._base_url}/{dbname}"

    def get_session(self, dbname: str) -> Session:
        """Open a read-only session for *dbname*."""
        if dbname not in self._sessions:
            engine = create_engine(
                self._dsn(dbname),
                pool_pre_ping=True,
                execution_options={"isolation_level": "AUTOCOMMIT"},
            )
            self._engines[dbname] = engine
            self._sessions[dbname] = sessionmaker(bind=engine)
        return self._sessions[dbname]()

    @contextmanager
    def session_scope(self, dbname: str) -> Iterator[Session]:
        """Context manager: yield a session, auto-close on exit."""
        session = self.get_session(dbname)
        try:
            yield session
        finally:
            session.close()
