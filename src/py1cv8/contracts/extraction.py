"""Extraction pipeline contract — BSL extraction orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ExtractionPipeline(Protocol):
    """Orchestrates BSL code extraction from config/configcas binary tables."""

    def extract_config(
        self,
        dbname: str,
        meta_map: dict[str, dict],
        out_dir: str | Path,
    ) -> list[dict]:
        """Extract BSL from objects with meta_len > 0 in Config table."""
        ...

    def extract_configcas(
        self,
        dbname: str,
        out_dir: str | Path,
    ) -> list[dict]:
        """Extract BSL from ConfigCas table (full code)."""
        ...

    def run(
        self,
        config_db: str = "MessageCenter",
        configcas_db: str | None = None,
    ) -> None:
        """Run full extraction pipeline."""
        ...
