"""Database access via SQLAlchemy ORM — engine, session factory, helpers.

Содержит как синхронные (legacy), так и асинхронные функции.
Асинхронный API — основной для ``sql/`` слоя.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from pydantic import PostgresDsn
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

# ── Хранилища движков (sync + async) ───────────────────────────────────────

_engines: dict[str, Engine] = {}
_sessions: dict[str, sessionmaker] = {}

_async_engines: dict[str, AsyncEngine] = {}
_async_sessions: dict[str, async_sessionmaker[AsyncSession]] = {}

_base_url: str = "postgresql+psycopg2://postgres:qwaseD12@localhost:5433"


# ── Утилиты URL ────────────────────────────────────────────────────────────


def normalise_db_url(db_url: str) -> str:
    """Нормализовать URL PostgreSQL.

    Заменяет устаревший ``postgres://`` на ``postgresql://``.
    """
    return db_url.replace("postgres://", "postgresql://", 1)


def normalise_async_db_url(db_url: str) -> str:
    """Нормализовать URL и переключить драйвер на asyncpg.

    >>> normalise_async_db_url("postgresql+psycopg2://u:p@h/db")
    'postgresql+asyncpg://u:p@h/db'
    """
    url = normalise_db_url(db_url)
    # Замена драйвера: +psycopg2 → +asyncpg
    url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    # Если драйвер не указан (+psycopg2), добавляем +asyncpg
    if "+asyncpg" not in url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def is_postgres_url(db_url: str) -> bool:
    """Проверить, указывает ли URL на PostgreSQL."""
    return "postgresql" in db_url or "postgres" in db_url


def quote_ident(name: str, db_url: str) -> str:
    """Экранировать идентификатор для SQL.

    PostgreSQL — двойные кавычки, MSSQL — квадратные скобки.
    """
    if is_postgres_url(db_url):
        return f'"{name}"'
    return f"[{name}]"


# ── Базовый URL ────────────────────────────────────────────────────────────


def set_base_url(url: PostgresDsn | str) -> None:
    """Установить базовый URL (без имени БД). Очищает кэш движков."""
    global _base_url
    _engines.clear()
    _sessions.clear()
    _async_engines.clear()
    _async_sessions.clear()
    _base_url = str(url).rstrip("/")


def _dsn(dbname: str) -> str:
    return f"{_base_url}/{dbname}"


def _async_dsn(dbname: str) -> str:
    """Собрать DSN с asyncpg-драйвером."""
    return normalise_async_db_url(f"{_base_url}/{dbname}")


# ═══════════════════════════════════════════════════════════════════════════
# СИНХРОННЫЙ API (legacy — потребители вне sql/ слоя)
# ═══════════════════════════════════════════════════════════════════════════


def get_engine(dbname: str) -> Engine:
    """Получить (или создать) синхронный Engine."""
    if dbname not in _engines:
        engine = create_engine(
            _dsn(dbname),
            pool_pre_ping=True,
            execution_options={"isolation_level": "AUTOCOMMIT"},
        )
        _engines[dbname] = engine
    return _engines[dbname]


def get_session(dbname: str) -> Session:
    """Создать синхронную read-only ORM-сессию (legacy)."""
    if dbname not in _sessions:
        _sessions[dbname] = sessionmaker(bind=get_engine(dbname))
    return _sessions[dbname]()


@contextmanager
def session_scope(dbname: str) -> Iterator[Session]:
    """Синхронный контекстный менеджер сессии (legacy)."""
    session = get_session(dbname)
    try:
        yield session
    finally:
        session.close()


class PgDatabaseProvider:
    """Синхронный read-only database provider (legacy)."""

    def __init__(self, base_url: PostgresDsn | str) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._engines: dict[str, Engine] = {}
        self._sessions: dict[str, sessionmaker] = {}

    def _dsn(self, dbname: str) -> str:
        return f"{self._base_url}/{dbname}"

    def get_session(self, dbname: str) -> Session:
        """Открыть синхронную read-only сессию."""
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
        session = self.get_session(dbname)
        try:
            yield session
        finally:
            session.close()


# ═══════════════════════════════════════════════════════════════════════════
# АСИНХРОННЫЙ API (основной для sql/ слоя)
# ═══════════════════════════════════════════════════════════════════════════


def get_async_engine(dbname: str) -> AsyncEngine:
    """Получить (или создать) асинхронный AsyncEngine."""
    if dbname not in _async_engines:
        engine = create_async_engine(
            _async_dsn(dbname),
            pool_pre_ping=True,
            execution_options={"isolation_level": "AUTOCOMMIT"},
        )
        _async_engines[dbname] = engine
    return _async_engines[dbname]


async def get_async_session(dbname: str) -> AsyncSession:
    """Создать асинхронную read-only ORM-сессию.

    Пример использования::

        async with await get_async_session("MyDB") as session:
            result = await session.execute(stmt)
    """
    if dbname not in _async_sessions:
        _async_sessions[dbname] = async_sessionmaker(
            bind=get_async_engine(dbname),
            expire_on_commit=False,
        )
    return _async_sessions[dbname]()


@asynccontextmanager
async def async_session_scope(dbname: str) -> AsyncIterator[AsyncSession]:
    """Асинхронный контекстный менеджер сессии.

    >>> async with async_session_scope("MyDB") as session:
    ...     result = await session.execute(stmt)
    """
    session = await get_async_session(dbname)
    try:
        yield session
    finally:
        await session.close()


class PgAsyncDatabaseProvider:
    """Read-only async database provider через SQLAlchemy async."""

    def __init__(self, base_url: PostgresDsn | str) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._engines: dict[str, AsyncEngine] = {}
        self._sessions: dict[str, async_sessionmaker[AsyncSession]] = {}

    def _dsn(self, dbname: str) -> str:
        return normalise_async_db_url(f"{self._base_url}/{dbname}")

    async def get_session(self, dbname: str) -> AsyncSession:
        """Открыть асинхронную read-only сессию."""
        if dbname not in self._sessions:
            engine = create_async_engine(
                self._dsn(dbname),
                pool_pre_ping=True,
                execution_options={"isolation_level": "AUTOCOMMIT"},
            )
            self._engines[dbname] = engine
            self._sessions[dbname] = async_sessionmaker(
                bind=engine,
                expire_on_commit=False,
            )
        return self._sessions[dbname]()

    @asynccontextmanager
    async def session_scope(self, dbname: str) -> AsyncIterator[AsyncSession]:
        session = await self.get_session(dbname)
        try:
            yield session
        finally:
            await session.close()
