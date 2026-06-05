"""Протоколы (PEP 544) для всех ключевых абстракций py1cv8.

Позволяют подменять реализации для тестов и расширения без
привязки к конкретным классам (duck typing → явные интерфейсы).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping, MutableMapping, MutableSequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

# ═══════════════════════════════════════════════════════════════════════
# Database access
# ═══════════════════════════════════════════════════════════════════════


@runtime_checkable
class DatabaseProvider(Protocol):
    """Синхронный read-only provider для БД 1С.

    Оборачивает SQLAlchemy Engine + sessionmaker.
    Реализация: :class:`py1cv8.sql.orm.engine.PgDatabaseProvider`.
    """

    def get_session(self, dbname: str) -> Session:
        """Открыть синхронную read-only сессию."""
        ...

    def session_scope(self, dbname: str) -> Iterator[Session]:
        """Синхронный контекстный менеджер сессии."""
        ...


@runtime_checkable
class AsyncDatabaseProvider(Protocol):
    """Асинхронный read-only provider для БД 1С.

    Реализация: :class:`py1cv8.sql.orm.engine.PgAsyncDatabaseProvider`.
    """

    async def get_session(self, dbname: str) -> AsyncSession:
        """Открыть асинхронную read-only сессию."""
        ...

    def session_scope(self, dbname: str) -> AsyncIterator[AsyncSession]:
        """Асинхронный контекстный менеджер сессии."""
        ...


# ═══════════════════════════════════════════════════════════════════════
# URL / DB name resolvers
# ═══════════════════════════════════════════════════════════════════════


class DbUrlNormaliser(Protocol):
    """Нормализация URL подключения к БД (postgres:// → postgresql://)."""

    def __call__(self, db_url: str) -> str: ...


class DbUrlValidator(Protocol):
    """Валидация URL подключения к БД (схема, путь)."""

    def __call__(self, db_url: str) -> str: ...


class DbNameResolver(Protocol):
    """Извлечение имени базы данных из URL."""

    def __call__(self, db_url: str) -> str: ...


# ═══════════════════════════════════════════════════════════════════════
# Table / object name resolvers
# ═══════════════════════════════════════════════════════════════════════


class TableNameResolver(Protocol):
    """Резолвер 1C-имени объекта → физическая таблица в БД.

    Используется в :func:`py1cv8.query_translator.translate_query`
    для трансляции ``Документ.ЗаказПокупателя`` в ``_Document123``.
    """

    def __call__(self, obj_type: str, obj_name: str) -> str | None: ...


class ConfigTableResolver(Protocol):
    """Резолвер имени таблицы config/configcas → ORM-модель."""

    def __call__(self, table: str) -> type[Any]: ...


# ═══════════════════════════════════════════════════════════════════════
# Blob processing
# ═══════════════════════════════════════════════════════════════════════


class BlobDecompressor(Protocol):
    """zlib-декомпрессия бинарных блобов 1С."""

    def __call__(self, data: bytes) -> bytes | None: ...


class BlobDecoder(Protocol):
    """Декодирование бинарного чанка в текст (chardet + скоринг)."""

    def __call__(self, chunk: bytes) -> str | None: ...


class CodeBlockExtractor(Protocol):
    """Извлечение блоков BSL-кода из распакованного блоба."""

    def __call__(self, data: bytes) -> MutableSequence[str]: ...


# ═══════════════════════════════════════════════════════════════════════
# Metadata parsing
# ═══════════════════════════════════════════════════════════════════════


class MetadataBlobParser(Protocol):
    """Парсинг одного бинарного блоба метаданных."""

    def __call__(self, data: bytes, type_num: int) -> Mapping[str, Any] | None: ...


class MetadataMapBuilder(Protocol):
    """Построение карты метаданных UUID → {tech_name, type_num, ...}."""

    async def __call__(self, db_url: str) -> MutableMapping[str, Mapping[str, Any]]: ...


# ═══════════════════════════════════════════════════════════════════════
# Output / formatting
# ═══════════════════════════════════════════════════════════════════════


class JsonOutputPort(Protocol):
    """Вывод JSON в stdout через typer.echo с обработкой 1С-типов."""

    def __call__(
        self,
        obj: object,
        *,
        pretty: bool = False,
    ) -> None: ...
