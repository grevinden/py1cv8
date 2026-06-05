"""JSON-кодировщик — сериализация UUID, memoryview и bytes в hex-строки.

Единственная ответственность (SRP):
  - Предоставление кастомного ``default``-обработчика для ``json.dumps``.
  - Конвертация бинарных UUID-подобных типов (memoryview, bytes)
    в человекочитаемый формат ``550e8400-e29b-41d4-a716-446655440000``.

Не занимается:
  - Вызовом ``json.dumps`` — только предоставляет функцию-обработчик.
  - Сериализацией сложных моделей (Pydantic, dataclass).

Пример использования:
    >>> import json
    >>> from py1cv8.json_encoder import default as json_default
    >>> data = {"uuid": memoryview(
    ...     b"\x55\x0e\x84\x00\xe2\x9b\x41\xd4\xa7\x16\x44\x66\x55\x44\x00\x00"
    ... )}
    >>> json.dumps(data, default=json_default, ensure_ascii=False)
    '{"uuid": "550e8400-e29b-41d4-a716-446655440000"}'
"""

from __future__ import annotations

import uuid


def _format_uuid_hex(raw: bytes) -> str:
    """Форматировать 16-байтовую последовательность как UUID-строку.

    Преобразует 16 сырых байт (128 бит) в стандартный UUID-формат
    ``550e8400-e29b-41d4-a716-446655440000`` с дефисами на позициях
    8, 12, 16, 20. Если длина отличается от 16 байт, возвращает
    hex-строку без дефисов.

    Args:
        raw: 16 байт (128 бит) в бинарном представлении UUID.
             Меньшая или большая длина обрабатывается корректно,
             но даст hex-строку без дефисов.

    Returns:
        Отформатированная UUID-строка вида
        ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`` (36 символов)
        или просто hex-строка, если длина не 16 байт.

    Example:
        >>> _format_uuid_hex(bytes(range(16)))
        '00010203-0405-0607-0809-0a0b0c0d0e0f'
        >>> _format_uuid_hex(b"\x00" * 16)
        '00000000-0000-0000-0000-000000000000'
    """
    h = raw.hex()
    if len(h) == 32:
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    return h


def default(obj: object) -> str:
    """Обработчик по умолчанию для ``json.dumps`` — конвертирует UUID-типы.

    Типы, поддерживаемые конвертацией:

    * ``memoryview`` — преобразуется через ``bytes(obj)`` в UUID-строку.
    * ``bytes`` (16 байт) — напрямую форматируется как UUID-строка.
    * ``uuid.UUID`` — вызывается ``str()``, возвращает стандартный вид.
    * Любой другой тип — возвращается ``str(obj)``.

    Args:
        obj: Объект, который ``json.dumps`` не смог сериализовать
             стандартными средствами.

    Returns:
        Строковое представление объекта. Для UUID-совместимых типов —
        hex-строка в UUID-формате. Для всех остальных — результат
        ``str(obj)``.

    Example:
        >>> import uuid
        >>> default(uuid.UUID("550e8400-e29b-41d4-a716-446655440000"))
        '550e8400-e29b-41d4-a716-446655440000'
        >>> default(b"\x00" * 16)
        '00000000-0000-0000-0000-000000000000'
    """
    if isinstance(obj, memoryview):
        return _format_uuid_hex(bytes(obj))
    if isinstance(obj, bytes):
        return _format_uuid_hex(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)
