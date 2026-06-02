"""Read-only database connection helper."""

from __future__ import annotations

import psycopg2
import psycopg2.extensions

from py1cv8.config import DB_HOST, DB_PASS, DB_PORT, DB_USER


def connect(dbname: str) -> psycopg2.extensions.connection:
    """Open a read-only connection to the given database."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=dbname,
        user=DB_USER, password=DB_PASS,
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn
