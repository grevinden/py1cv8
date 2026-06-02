"""Database access via SQLAlchemy ORM — engine, session factory, helpers.

All database operations MUST go through this module.
No raw psycopg2 connections allowed.

Satisfies: contracts.database.DatabaseSessionProvider
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from py1cv8.config import DB_HOST, DB_PASS, DB_PORT, DB_USER

_engines: dict[str, object] = {}
_sessions: dict[str, sessionmaker] = {}


def _dsn(dbname: str) -> str:
    return (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{dbname}"
    )


def get_engine(dbname: str):
    """Return (and cache) a SQLAlchemy engine for the given database."""
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


# ── Class implementation (satisfies DatabaseSessionProvider contract) ────


class PgDatabaseProvider:
    """Read-only PostgreSQL provider via SQLAlchemy.

    Satisfies: contracts.database.DatabaseSessionProvider
    """

    def __init__(
        self,
        host: str = DB_HOST,
        port: int = DB_PORT,
        user: str = DB_USER,
        password: str = DB_PASS,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._engines: dict[str, object] = {}
        self._sessions: dict[str, sessionmaker] = {}

    def _dsn(self, dbname: str) -> str:
        return (
            f"postgresql+psycopg2://{self._user}:{self._password}"
            f"@{self._host}:{self._port}/{dbname}"
        )

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
