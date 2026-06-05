"""JSON encoder — handles UUID, memoryview, bytes for clean serialisation.

Usage:
    from py1cv8.json_encoder import default as json_default
    json.dumps(data, default=json_default)
"""

from __future__ import annotations

import uuid


def _format_uuid_hex(raw: bytes) -> str:
    """Format 16-byte UUID as ``550e8400-e29b-41d4-a716-446655440000``."""
    h = raw.hex()
    if len(h) == 32:
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    return h


def default(obj: object) -> str:
    """json.dumps default handler — converts UUID types to hex strings."""
    if isinstance(obj, memoryview):
        return _format_uuid_hex(bytes(obj))
    if isinstance(obj, bytes):
        return _format_uuid_hex(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)
