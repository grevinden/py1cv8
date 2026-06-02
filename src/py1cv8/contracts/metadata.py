"""Metadata provider contract — reading config/configcas binary blobs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetadataProvider(Protocol):
    """Reads 1C metadata from config/configcas binary blobs."""

    def build_metadata_map(self, dbname: str) -> dict[str, dict]:
        """Build metadata map from Config table (DBName → blob info).

        Returns: {uuid_str: {"name": ..., "type": ..., ...}, ...}
        """
        ...

    def parse_metadata_blob(self, txt: str) -> dict | None:
        """Parse a single metadata blob (MOXCEL or {1,\n{type})."""
        ...

    def extract_type_from_configcas_blob(self, dec: bytes) -> int | None:
        """Extract type_num from decompressed configcas blob."""
        ...
