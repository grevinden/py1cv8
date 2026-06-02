"""DBNames provider contract — parsing _DBNames__ system table."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DBNamesProvider(Protocol):
    """Parses _DBNames__ content and generates SQL table names."""

    def parse_dbnames_text(self, text: str) -> list[dict]:
        """Parse raw _DBNames__ table content into structured entries.

        Returns: list of {uuid, type_name, number, db_name, category, ...}
        """
        ...

    def generate_db_name(
        self,
        entry: dict,
        parent_db_name: str | None = None,
    ) -> str | None:
        """Generate SQL table name for a DBNames entry."""
        ...
