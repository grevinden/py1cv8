"""Filesystem and checkpoint utilities.

Responsibilities:
  - Sanitize filenames for Windows filesystem
  - Checkpoint load/save for incremental extraction
  - Write extracted module files to disk

Satisfies: contracts.filesystem.FileSystemProvider
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from py1cv8.config import CHECKPOINT_PATH


def sanitize(name: str) -> str:
    """Remove Windows-illegal characters from filename."""
    name = re.sub(r'[/\\:*?"<>|]', "", name).strip()
    if len(name) > 200:
        name = name[:197] + "..."
    return name


def load_checkpoint() -> set[str]:
    """Load set of already-extracted UUIDs from checkpoint file."""
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_checkpoint(uuids: set[str]) -> None:
    """Save set of extracted UUIDs to checkpoint file."""
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(uuids), f, ensure_ascii=False)
    os.replace(tmp, CHECKPOINT_PATH)


def write_module_file(
    out_dir: Path,
    category: str,
    tech_name: str,
    code: str,
    block_index: int = 0,
    total_blocks: int = 1,
    use_subdir: bool = True,
) -> str:
    """Write a single BSL module file to disk. Returns relative path.

    If use_subdir=True (default), places file in:
        out_dir / category / tech_name / tech_name[_N][_counter].bsl

    If use_subdir=False:
        out_dir / category / tech_name[_N][_counter].bsl
    """
    cat_dir = out_dir / sanitize(category)
    mod_dir = cat_dir / tech_name if use_subdir else cat_dir
    os.makedirs(mod_dir, exist_ok=True)

    stem = tech_name
    suffix = f"_{block_index + 1}" if total_blocks > 1 else ""
    fn = f"{stem}{suffix}.bsl"
    out_path = mod_dir / fn

    counter = 0
    while out_path.exists():
        counter += 1
        out_path = mod_dir / f"{stem}{suffix}_{counter}.bsl"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)

    return str(out_path.relative_to(out_dir))


# ── Class implementation (satisfies FileSystemProvider contract) ──────────


class FileSystemProviderImpl:
    """File I/O and checkpoint management for extraction pipeline.

    Satisfies: contracts.filesystem.FileSystemProvider
    """

    def __init__(self, checkpoint_path: str | Path | None = None) -> None:
        self._checkpoint_path = Path(checkpoint_path) if checkpoint_path else CHECKPOINT_PATH

    @staticmethod
    def ensure_dir(path: str | Path) -> Path:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def write_text(self, path: str | Path, content: str) -> None:
        Path(path).write_text(content, encoding="utf-8")

    @staticmethod
    def sanitize_name(name: str) -> str:
        return sanitize(name)

    def load_checkpoint(self, path: str | Path | None = None) -> set[str] | None:
        cp = Path(path) if path else self._checkpoint_path
        try:
            with open(cp, encoding="utf-8") as f:
                return set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_checkpoint(self, path: str | Path, data: set[str]) -> None:
        cp = Path(path)
        tmp = cp.parent / (cp.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(data), f, ensure_ascii=False)
        os.replace(tmp, cp)
