"""Parse ConfigDumpInfo.xml → UUID-to-configVersion mapping.

Each metadata object in 1C has a configVersion (40 hex chars: 32 hash + 8 zeros).
When the object's code/module/form changes, the configVersion changes.
This enables cache invalidation — if an object's configVersion differs from
a previously stored version, its data is stale.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://v8.1c.ru/8.3/xcf/dumpinfo"


def parse_config_dump_info(filepath: str | Path) -> dict[str, str]:
    """Parse ConfigDumpInfo.xml → {full_id: configVersion}.

    Returns a flat dict mapping every Metadata entry's full ``id`` attribute
    (e.g. ``94a563af-...`` or ``94a563af-....0``) to its ``configVersion``
    hex string.  Only entries that carry a ``configVersion`` attribute are
    included — nested children that inherit the parent version are skipped.
    """
    tree = ET.parse(str(filepath))
    root = tree.getroot()
    versions: dict[str, str] = {}
    _collect_versions(root, versions)
    return versions


def _collect_versions(element: ET.Element, versions: dict[str, str]) -> None:
    tag = element.tag
    # Match any element in the dumpinfo namespace whose localname is Metadata
    if tag.startswith(f"{{{NS}") and tag.endswith("}Metadata"):
        cver = element.get("configVersion")
        uid = element.get("id")
        if cver is not None and uid is not None:
            versions[uid] = cver
    for child in element:
        _collect_versions(child, versions)


def resolve_config_dump_path(export_dir: str | Path) -> Path | None:
    """Return the path to ConfigDumpInfo.xml under *export_dir*, or None.

    Checks both *export_dir*/ConfigDumpInfo.xml and
    *export_dir*/test_database/ConfigDumpInfo.xml.
    """
    base = Path(export_dir)
    candidates = [
        base / "ConfigDumpInfo.xml",
        base / "test_database" / "ConfigDumpInfo.xml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None
