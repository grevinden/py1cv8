"""Database access via SQLAlchemy ORM — реэкспорт из py1cv8.sql.orm.engine.

Вся ORM-инфраструктура перенесена в ``py1cv8.sql.orm.engine``.
Этот файл — временная прокладка для обратной совместимости.
"""

from py1cv8.sql.orm.engine import (
    PgDatabaseProvider,
    _base_url,
    _dsn,
    _engines,
    _sessions,
    get_engine,
    get_session,
    is_postgres_url,
    normalise_db_url,
    quote_ident,
    session_scope,
    set_base_url,
)

__all__ = [
    "PgDatabaseProvider",
    "_base_url",
    "_dsn",
    "_engines",
    "_sessions",
    "get_engine",
    "get_session",
    "is_postgres_url",
    "normalise_db_url",
    "quote_ident",
    "session_scope",
    "set_base_url",
]
