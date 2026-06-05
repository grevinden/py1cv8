"""Memory persistence for MCP sessions — сохранение заметок и траекторий между сессиями.

Хранилище:
    Windows: %LOCALAPPDATA%/py1cv8/notes/{db_hash}.json
    macOS:   ~/Library/Application Support/py1cv8/notes/{db_hash}.json
    Linux:   ~/.local/share/py1cv8/notes/{db_hash}.json
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ── App data directory ────────────────────────────────────────────────────


def _get_app_dir() -> Path:
    """Получить стандартный каталог приложения py1cv8."""
    if sys.platform == "win32":  # Windows
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return Path(base) / "py1cv8"
    elif sys.platform == "darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / "py1cv8"
    else:  # Linux / BSD
        xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return Path(xdg) / "py1cv8"


# ── Key derivation ────────────────────────────────────────────────────────


def _db_key(db_url: str) -> str:
    """Хеш от db_url для изоляции заметок между базами."""
    return hashlib.sha256(db_url.encode("utf-8")).hexdigest()[:16]


# ── Notes API ──────────────────────────────────────────────────────────────


def _notes_dir() -> Path:
    """Директория для заметок — {app_dir}/notes/."""
    d = _get_app_dir() / "notes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _notes_path(db_url: str) -> Path:
    """Путь к файлу заметок для конкретной базы."""
    return _notes_dir() / f"{_db_key(db_url)}.json"


def load_notes(db_url: str) -> dict[str, Any]:
    """Загрузить заметки для базы данных.

    Возвращает словарь:
    ```json
    {
      "mappings": {"Контрагенты": "_Reference53", ...},
      "rules": ["У _inforg{N} нет _IDRRef"],
      "patterns": [
        {"situation": "выбрала неверную таблицу",
         "correction": "сначала get_context"}
      ]
    }
    ```
    """
    path = _notes_path(db_url)
    if not path.exists():
        return {"mappings": {}, "rules": [], "patterns": []}
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {"mappings": {}, "rules": [], "patterns": []}


def save_notes(db_url: str, notes: dict[str, Any]) -> None:
    """Сохранить заметки для базы данных.

    Полностью перезаписывает файл — модель должна передать весь контекст.
    """
    path = _notes_path(db_url)
    path.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Trajectories API ──────────────────────────────────────────────────────


def _trajs_dir() -> Path:
    """Директория для траекторий — {app_dir}/trajectories/."""
    d = _get_app_dir() / "trajectories"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_trajectory(db_url: str, trajectory: dict[str, Any]) -> str:
    """Сохранить траекторию сессии.

    Ожидает dict с ключами:
        messages: list[dict] — массив сообщений диалога
        metadata: dict — опционально: модель, теги

    Возвращает имя файла (по timestamp).
    """
    from datetime import UTC, datetime

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    key = _db_key(db_url)
    filename = f"{key}_{ts}.json"
    path = _trajs_dir() / filename
    payload = {
        "db_key": key,
        "timestamp": ts,
        "trajectory": trajectory,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return filename


def load_recent_trajectories(db_url: str, limit: int = 5) -> list[dict[str, Any]]:
    """Загрузить последние N траекторий для базы (по дате файла).

    Возвращает список траекторий, отсортированных от новых к старым.
    """
    key = _db_key(db_url)
    trajs_dir = _trajs_dir()
    if not trajs_dir.exists():
        return []

    matches: list[tuple[float, dict[str, Any]]] = []
    for fpath in sorted(trajs_dir.iterdir(), reverse=True):
        if fpath.name.startswith(key) and fpath.suffix == ".json":
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                mtime = fpath.stat().st_mtime
                matches.append((mtime, data))
            except (json.JSONDecodeError, OSError):
                continue

    # Оставляем только limit штук, уже отсортировано по убыванию времени
    return [m[1] for m in matches[:limit]]
