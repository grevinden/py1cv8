"""Relationship builder contract — ref-graph between 1C tables."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class RelationshipBuilder(Protocol):
    """Builds a graph of Ref/RTRef/Owner/Parent relationships between tables."""

    def build_relationships(
        self,
        tables: Mapping[str, object],
        entries: list[dict],
        main_types: frozenset[str],
    ) -> dict[str, list[dict]]:
        """Build {table_name: [relationship_dict, ...]}.
        *tables* values are ObjectInfo | ServiceTableInfo.
        """
        ...
