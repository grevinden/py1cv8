"""Распаковка и декодирование бинарных блобов 1С."""

from py1cv8.blob.decompress import (
    decode_blob_chunk,
    extract_code_blocks,
    try_decompress,
)

__all__ = [
    "decode_blob_chunk",
    "extract_code_blocks",
    "try_decompress",
]
