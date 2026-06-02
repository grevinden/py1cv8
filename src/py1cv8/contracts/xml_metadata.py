"""XML metadata provider contract — reading .staff/.export_from_1c/ XML exports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from py1cv8.metadata_xml import ObjectMetadata


@runtime_checkable
class XmlMetadataProvider(Protocol):
    """Scans and parses .staff/.export_from_1c/ XML metadata directories."""

    def scan_export_directory(
        self,
        export_dir: str | Path | None = None,
    ) -> dict[str, ObjectMetadata]:
        """Scan export directory, return {uuid: ObjectMetadata}."""
        ...

    def parse_object_xml(
        self,
        filepath: str | Path,
    ) -> ObjectMetadata | None:
        """Parse a single .xml export file into ObjectMetadata."""
        ...
