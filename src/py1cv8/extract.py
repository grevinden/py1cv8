"""Backward-compatible re-export facade.

All functions are now in SRP submodules. This file re-exports
everything for existing imports (tests, schema.py, mcp_server.py).
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Re-export all public symbols
from py1cv8.bsl import extract_name_from_code  # noqa: E402, F401

# Re-export _has_bsl_keywords used by tests
from py1cv8.bsl import has_bsl_keywords as _has_bsl_keywords  # noqa: E402, F401
from py1cv8.compress import (  # noqa: E402, F401
    decode_blob_chunk,
    extract_code_blocks,
    try_decompress,
)
from py1cv8.config import (  # noqa: E402, F401
    CHECKPOINT_PATH,
    DB_HOST,
    DB_PASS,
    DB_PORT,
    DB_USER,
    OUT_DIR,
    TYPE_MAP,
)
from py1cv8.extract_pipeline import (  # noqa: E402, F401
    extract_from_config_table,
    extract_from_configcas_table,
    main,
)
from py1cv8.filesystem import load_checkpoint, sanitize, save_checkpoint  # noqa: E402, F401
from py1cv8.metadata_binary import (  # noqa: E402, F401
    build_metadata_map,
    extract_type_from_configcas_blob,
    parse_metadata_blob,
)
