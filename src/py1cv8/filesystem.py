"""Filesystem and checkpoint utilities.

Responsibilities:
  - Sanitize filenames for Windows filesystem
  - Checkpoint load/save for incremental extraction
  - Write extracted module files to disk
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
