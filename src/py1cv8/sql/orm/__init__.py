"""ORM слой — модели, engine, запросы к таблицам 1С.

Асинхронный API — основной для ``sql/`` слоя.
Синхронные функции (legacy) доступны для обратной совместимости.
"""

from py1cv8.sql.orm.config_queries import ConfigTable, select_config_rows
from py1cv8.sql.orm.engine import (
    PgAsyncDatabaseProvider,
    PgDatabaseProvider,
    async_session_scope,
    get_async_engine,
    get_async_session,
    get_engine,
    get_session,
    is_mssql_url,
    is_postgres_url,
    normalise_async_db_url,
    normalise_db_url,
    quote_ident,
    session_scope,
    set_base_url,
)
from py1cv8.sql.orm.models import (
    Base,
    Config,
    ConfigCas,
    ConfigSave,
    InformationSchemaColumn,
    InformationSchemaKeyColumnUsage,
    InformationSchemaTableConstraint,
    Params,
)
from py1cv8.sql.types import DatabaseDsn

__all__ = [
    "async_session_scope",
    "Base",
    "Config",
    "ConfigCas",
    "ConfigSave",
    "ConfigTable",
    "DatabaseDsn",
    "get_async_engine",
    "get_async_session",
    "get_engine",
    "get_session",
    "InformationSchemaColumn",
    "InformationSchemaKeyColumnUsage",
    "InformationSchemaTableConstraint",
    "is_mssql_url",
    "is_postgres_url",
    "normalise_async_db_url",
    "normalise_db_url",
    "Params",
    "PgAsyncDatabaseProvider",
    "PgDatabaseProvider",
    "quote_ident",
    "select_config_rows",
    "session_scope",
    "set_base_url",
]
