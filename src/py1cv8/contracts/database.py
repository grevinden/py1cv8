"""Database session provider contract."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session


@runtime_checkable
class DatabaseSessionProvider(Protocol):
    """Provides read-only SQLAlchemy sessions for 1C databases."""

    def get_session(self, dbname: str) -> Session:
        """Open a read-only session for *dbname*."""
        ...

    def session_scope(self, dbname: str) -> AbstractContextManager[Session]:
        """Context manager: yield a session, auto-close on exit."""
        ...
