"""Parse 1C metadata XML export — re-exports from mx_parser + provider class."""

from __future__ import annotations

from pathlib import Path

from py1cv8.config import EXPORT_DIR
from py1cv8.mx_models import (  # noqa: F401
    AttributeInfo,
    AttributeTypeInfo,
    CommandInfo,
    EnumValueInfo,
    GeneratedTypeInfo,
    ObjectMetadata,
    TabularSectionInfo,
    TypeQualifierInfo,
)
from py1cv8.mx_parser import (  # noqa: F401
    DIR_TO_TYPE,
    parse_object_xml,
    scan_export_directory,
)

# ── Provider implementation (satisfies XmlMetadataProvider contract) ──────


class XmlMetadataProviderImpl:
    """Scans .staff/.export_from_1c/ directories and parses XML metadata."""

    def __init__(self, export_dir: str | Path | None = None) -> None:
        self._export_dir = Path(export_dir) if export_dir else EXPORT_DIR

    def scan_export_directory(
        self,
        export_dir: str | Path | None = None,
    ) -> dict[str, ObjectMetadata]:
        base = Path(export_dir) if export_dir else self._export_dir
        return scan_export_directory(str(base))

    @staticmethod
    def parse_object_xml(filepath: str | Path) -> ObjectMetadata | None:
        return parse_object_xml(str(filepath))
