"""File system provider contract — file I/O operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileSystemProvider(Protocol):
    """Abstract file I/O for extraction pipeline output and checkpoints."""

    def ensure_dir(self, path: str | Path) -> Path:
        """Create directory if not exists, return Path."""
        ...

    def write_text(self, path: str | Path, content: str) -> None:
        """Write UTF-8 text to file."""
        ...

    def sanitize_name(self, name: str) -> str:
        """Sanitize a filename — remove/replace invalid chars."""
        ...

    def load_checkpoint(self, path: str | Path | None = None) -> set[str] | None:
        """Load checkpoint file, return set of processed UUIDs or None.
        If path is None, uses provider's default checkpoint path.
        """
        ...

    def save_checkpoint(self, path: str | Path, data: set[str]) -> None:
        """Save checkpoint (processed UUIDs) to file."""
        ...
