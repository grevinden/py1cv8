"""Pydantic-типы для описания DSN подключения к базе данных 1С.

Предоставляет валидированный тип ``DatabaseDsn`` на основе ``Annotated[str, ...]``
с проверкой схемы (postgresql / mssql+pyodbc), нормализацией устаревшего
``postgres://`` и обязательным именем базы данных в пути URL.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from pydantic import TypeAdapter
from pydantic.functional_validators import AfterValidator, BeforeValidator

# ── Разрешённые схемы подключения ──────────────────────────────────────────

ALLOWED_SCHEMES: frozenset[str] = frozenset(
    {
        "postgresql",
        "postgresql+psycopg2",
        "postgresql+asyncpg",
        "postgres",
        "mssql+pyodbc",
    }
)


# ── Внутренние валидаторы ──────────────────────────────────────────────────


def _normalise_scheme(url: str) -> str:
    """Заменить устаревший ``postgres://`` на ``postgresql://``."""
    return url.replace("postgres://", "postgresql://", 1)


def _check_scheme(url: str) -> str:
    """Проверить, что схема подключения поддерживается."""
    parsed = urlparse(url)
    if not parsed.scheme:
        raise ValueError(f"Unsupported database URL: no scheme found in {url!r}.")
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported scheme: {parsed.scheme!r}. Allowed: {', '.join(sorted(ALLOWED_SCHEMES))}."
        )
    return url


def _check_db_path(url: str) -> str:
    """Проверить, что URL содержит путь с именем базы данных."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Database URL must include a path (database name): {url}")
    return url


# ── Pydantic-тип DSN ───────────────────────────────────────────────────────

DatabaseDsn = Annotated[
    str,
    BeforeValidator(_normalise_scheme),
    AfterValidator(_check_scheme),
    AfterValidator(_check_db_path),
]
"""Pydantic-валидируемый тип для URL подключения к БД.

Поддерживает PostgreSQL (``postgresql://``, ``postgresql+psycopg2://``,
``postgresql+asyncpg://``) и MSSQL (``mssql+pyodbc://``).

Автоматически нормализует ``postgres://`` в ``postgresql://``.

Примеры использования в Pydantic-моделях::

    class Config(BaseModel):
        db_url: DatabaseDsn
"""

_dsn_adapter: TypeAdapter[str] = TypeAdapter(DatabaseDsn)


# ── Публичные функции ──────────────────────────────────────────────────────


def validate_db_url(db_url: str) -> str:
    """Проверить и нормализовать URL подключения к базе данных.

    Args:
        db_url: Строка URL (например,
            ``postgresql://user:pass@host:5432/dbname``
            или ``mssql+pyodbc://user:pass@host:port/dbname``).

    Returns:
        Нормализованный URL в виде строки.

    Raises:
        ValueError: Если схема не поддерживается или отсутствует имя БД.
    """
    return _dsn_adapter.validate_python(db_url)


def get_db_name(db_url: str) -> str:
    """Извлечь имя базы данных из URL подключения.

    >>> get_db_name("postgresql://user:pass@localhost:5432/mydb")
    'mydb'

    Args:
        db_url: Строка URL подключения к базе данных.

    Returns:
        Имя базы данных (последний сегмент пути URL).

    Raises:
        ValueError: Если URL не содержит схему или имя базы данных.
    """
    parsed = urlparse(db_url)

    if not parsed.scheme:
        raise ValueError(f"Cannot extract database name from {db_url!r}: no scheme found")

    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Cannot extract database name from {db_url!r}: empty path")

    return path.rsplit("/", 1)[-1]
