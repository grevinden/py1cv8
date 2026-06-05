"""Deep UUID lookup across ALL database tables with _idrref column."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from py1cv8.db import is_postgres_url, quote_ident
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex


def lookup_uuid(
    db_url: str,
    uuid_str: str,
    limit: int = 50,
) -> list[dict]:
    """Search *uuid_str* across every table that has an ``_idrref`` column.

    Unlike ``resolve_uuid`` (which only checks DBNames tables), this
    scans **all** tables in the public schema.

    Parameters
    ----------
    db_url
        SQLAlchemy database URL.
    uuid_str
        UUID with or without dashes.
    limit
        Max tables to search.

    Returns
    -------
    list[dict]
        Each found entry: table, description, code, source.
    """
    hex_val = uuid_str.replace("-", "").strip().lower()
    idrref_hex = _uuid_to_1c_idrref_hex(hex_val)

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )
    try:
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    "SELECT DISTINCT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "AND LOWER(column_name) = '_idrref' "
                    "ORDER BY table_name"
                ),
            ).fetchall()

            results: list[dict] = []
            is_pg = is_postgres_url(db_url)

            for (tbl,) in tables:
                if len(results) >= limit:
                    break
                try:
                    qtn = quote_ident(tbl, db_url)
                    qidr = quote_ident("_idrref", db_url)

                    if is_pg:
                        sql = text(
                            f"SELECT * FROM {qtn}"
                            f" WHERE encode({qidr}::bytea, 'hex')"
                            f" IN ('{hex_val}', '{idrref_hex}')"
                            f" LIMIT 1"
                        )
                    else:
                        sql = text(
                            f"SELECT TOP 1 * FROM {qtn}"
                            f" WHERE LOWER(CONVERT(VARCHAR(32), {qidr}, 2))"
                            f" IN ('{hex_val}', '{idrref_hex}')"
                        )

                    row = conn.execute(sql).fetchone()
                    if row:
                        keys = list(row._fields) if hasattr(row, "_fields") else []
                        row_dict = dict(zip(keys, row, strict=False)) if keys else {}
                        rd = {k.lower(): v for k, v in row_dict.items()}
                        results.append(
                            {
                                "table": tbl,
                                "uuid": _format_lookup_uuid(hex_val),
                                "description": rd.get("_description"),
                                "code": rd.get("_code"),
                                "source": "data",
                            }
                        )
                except Exception:
                    continue

            return results
    finally:
        engine.dispose()


def _format_lookup_uuid(hex_str: str) -> str:
    h = hex_str.strip().lower().replace("-", "")
    if len(h) != 32:
        return hex_str
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
