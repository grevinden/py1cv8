"""Legacy entry point. All logic is in src/py1cv8/ — use `python -m py1cv8` instead."""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Backward-compat re-exports for legacy diag scripts
from py1cv8.extract import (  # noqa: E402, F401
    _has_bsl_keywords,
    build_metadata_map,
    CHECKPOINT_PATH,
    DB_HOST,
    DB_PASS,
    DB_PORT,
    DB_USER,
    decode_blob_chunk,
    extract_code_blocks,
    extract_from_config_table,
    extract_from_configcas_table,
    extract_name_from_code,
    extract_type_from_configcas_blob,
    load_checkpoint,
    main,
    OUT_DIR,
    parse_metadata_blob,
    sanitize,
    save_checkpoint,
    try_decompress,
    TYPE_MAP,
)
