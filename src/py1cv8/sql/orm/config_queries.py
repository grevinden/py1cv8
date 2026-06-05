"""ORM-запросы к таблицам config и configcas 1С.

Использует асинхронный SQLAlchemy API (``get_async_session``).
"""

from __future__ import annotations

from typing import Any, Literal, cast

from sqlalchemy import select

from py1cv8.sql.orm.engine import get_async_session
from py1cv8.sql.orm.models import Config, ConfigCas
from py1cv8.sql.types import get_db_name, validate_db_url

ConfigTable = Literal["config", "configcas"]


def _resolve_model(table: ConfigTable) -> type[Config | ConfigCas]:
    """Вернуть ORM-модель для указанной таблицы."""
    if table == "config":
        return Config
    if table == "configcas":
        return ConfigCas
    raise ValueError(f"Unknown table: {table!r}. Choose from: config, configcas")


async def select_config_rows(
    db_url: str,
    *,
    table: ConfigTable = "config",
    filename: str | None = None,
    partno: int | None = None,
    uuid: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Выбрать строки из config/configcas через асинхронный ORM.

    Чистый ORM-слой. Возвращает сырые данные **без** декомпрессии блобов.

    Parameters
    ----------
    db_url : str
        URL подключения к БД (SQLAlchemy). Валидируется автоматически.
    table : Literal["config", "configcas"]
    filename : str, optional
        Паттерн ILIKE для фильтрации имени файла.
    partno : int, optional
        Точный номер части.
    uuid : str, optional
        UUID для поиска в имени файла (ILIKE).
    limit : int
        Максимум строк.

    Returns
    -------
    list[dict[str, Any]]
        Словари с ключами ``filename``, ``partno``, ``binarydata``.
    """
    validate_db_url(db_url)
    model_cls = _resolve_model(table)
    dbname = get_db_name(db_url)

    async with await get_async_session(dbname) as session:
        stmt = select(model_cls)

        if uuid:
            stmt = stmt.filter(model_cls.filename.ilike(f"%{uuid.lower()}%"))
        elif filename:
            pattern = filename.replace("%", "%%")
            stmt = stmt.filter(model_cls.filename.ilike(pattern))

        if partno is not None:
            stmt = stmt.filter(model_cls.partno == int(partno))

        stmt = stmt.order_by(
            model_cls.filename,
            model_cls.partno,
        ).limit(int(limit))

        result = await session.execute(stmt)
        rows = cast(
            list[Config | ConfigCas],
            result.scalars().all(),
        )

        return [
            {
                "filename": row.filename,
                "partno": row.partno,
                "binarydata": bytes(row.binarydata) if row.binarydata else None,
            }
            for row in rows
        ]
