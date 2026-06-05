"""MCP-сервер для py1cv8 — инструменты для LLM через Model Context Protocol.

Сервер регистрирует инструменты, которые LLM-клиент (например, Claude Desktop,
VS Code, Copilot) может вызывать для анализа 1С-метаданных, структуры таблиц,
SQL-запросов и связей между объектами.

Транспорты:
    stdio   — python -m py1cv8 mcp
    sse+http — python -m py1cv8 mcp --transport sse --port 8100

Подключение:
    {
      "mcpServers": {
        "py1cv8": {
          "command": "python",
          "args": ["-m", "py1cv8", "mcp"]
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

from py1cv8.blob_fetch import extract_metadata_blobs
from py1cv8.context import build_llm_context
from py1cv8.describe_object import describe_text
from py1cv8.find_objects import find_objects
from py1cv8.graph import graph_mermaid, graph_text
from py1cv8.json_encoder import default as json_default
from py1cv8.mcp.memory import (
    load_notes as _load_notes,
)
from py1cv8.mcp.memory import (
    load_recent_trajectories as _load_recent_trajectories,
)
from py1cv8.mcp.memory import (
    save_notes as _save_notes,
)
from py1cv8.mcp.memory import (
    save_trajectory as _save_trajectory,
)
from py1cv8.mcp.system_prompt import SYSTEM_PROMPT
from py1cv8.resolve_uuid import resolve_uuid
from py1cv8.schema_describe import describe_table as get_schema
from py1cv8.sql_proxy import execute_readonly

# ── JSON helpers ──────────────────────────────────────────────────────────


def _to_json(data: Any) -> str:
    """Сериализовать данные в JSON-строку с поддержкой UUID/memoryview."""
    return json.dumps(data, default=json_default, ensure_ascii=False, indent=2)


def _to_result(text: str) -> list[TextContent]:
    """Обернуть текст в MCP TextContent."""
    return [TextContent(type="text", text=text)]


def _to_error(message: str) -> list[TextContent]:
    """Обернуть ошибку в MCP TextContent."""
    return [TextContent(type="text", text=f"ERROR: {message}")]


# ── Tool handlers ─────────────────────────────────────────────────────────


async def handle_get_context(arguments: dict) -> list[TextContent]:
    """Полная карта метаданных 1С из config/configcas/configsave.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        table: Таблица-источник (config, configcas, configsave). По умолчанию config.
    """
    db_url: str = arguments.get("db_url", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    table: str = arguments.get("table", "config")
    try:
        ctx = build_llm_context(db_url, table=table)
        return _to_result(_to_json(ctx))
    except Exception as e:
        return _to_error(f"Не удалось получить контекст: {e}")


async def handle_describe_object(arguments: dict) -> list[TextContent]:
    """Полное описание объекта 1С по UUID.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        uuid: UUID объекта.
        sample_rows: Количество семплов строк (по умолчанию 3).
        resolve_refs: Разрешать UUID-ссылки в семплах (по умолчанию False).
    """
    db_url: str = arguments.get("db_url", "")
    uuid_str: str = arguments.get("uuid", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not uuid_str:
        return _to_error("Параметр 'uuid' обязателен")
    sample_limit: int = arguments.get("sample_rows", 3)
    resolve_refs: bool = arguments.get("resolve_refs", False)
    try:
        text = await describe_text(
            db_url,
            uuid_str,
            sample_limit=sample_limit,
            resolve_refs=resolve_refs,
            no_blob=False,
        )
        return _to_result(text)
    except Exception as e:
        return _to_error(f"Не удалось описать объект: {e}")


async def handle_find_objects(arguments: dict) -> list[TextContent]:
    """Поиск объектов метаданных 1С по ключевому слову в имени.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        keyword: Ключевое слово для поиска.
        limit: Максимальное количество результатов (по умолчанию 50).
    """
    db_url: str = arguments.get("db_url", "")
    keyword: str = arguments.get("keyword", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not keyword:
        return _to_error("Параметр 'keyword' обязателен")
    limit: int = arguments.get("limit", 50)
    try:
        results = find_objects(db_url, keyword, limit=limit)
        return _to_result(_to_json(results))
    except Exception as e:
        return _to_error(f"Не удалось выполнить поиск: {e}")


async def handle_get_graph(arguments: dict) -> list[TextContent]:
    """Граф связей объекта 1С: владелец, родитель, ссылки, обратные ссылки.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        uuid: UUID объекта.
        mermaid: Если True — вернуть Mermaid-диаграмму, иначе текст (по умолчанию False).
    """
    db_url: str = arguments.get("db_url", "")
    uuid_str: str = arguments.get("uuid", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not uuid_str:
        return _to_error("Параметр 'uuid' обязателен")
    use_mermaid: bool = arguments.get("mermaid", False)
    try:
        if use_mermaid:
            text = await graph_mermaid(db_url, uuid_str)
        else:
            text = await graph_text(db_url, uuid_str)
        return _to_result(text)
    except Exception as e:
        return _to_error(f"Не удалось построить граф: {e}")


async def handle_run_sql(arguments: dict) -> list[TextContent]:
    """Выполнить read-only SQL-запрос к базе 1С.

    Разрешены только SELECT, EXPLAIN, WITH, SHOW, DESCRIBE.
    Запросы, изменяющие данные, будут отклонены.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        query: SQL-запрос (SELECT/EXPLAIN/WITH/SHOW/DESCRIBE).
    """
    db_url: str = arguments.get("db_url", "")
    query: str = arguments.get("query", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not query:
        return _to_error("Параметр 'query' обязателен")
    try:
        results = execute_readonly(db_url, query)
        return _to_result(_to_json(results))
    except Exception as e:
        error_text = str(e)
        # Автосохранение ошибочного запроса для fine-tuning
        try:
            traj = {
                "messages": [
                    {"role": "user", "content": f"SQL: {query}"},
                    {"role": "tool", "content": f"ОШИБКА: {error_text}"},
                ],
                "metadata": {
                    "type": "sql_error",
                    "tool": "run_sql",
                    "query": query[:200],
                    "error": error_text[:500],
                },
            }
            _save_trajectory(db_url, traj)
        except Exception:
            pass
        return _to_error(f"Ошибка SQL: {e}")


async def handle_get_table_schema(arguments: dict) -> list[TextContent]:
    """Структура таблицы 1С: колонки, типы, nullable.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        table_name: Имя таблицы (например, _Reference117).
    """
    db_url: str = arguments.get("db_url", "")
    table_name: str = arguments.get("table_name", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not table_name:
        return _to_error("Параметр 'table_name' обязателен")
    try:
        schema = get_schema(db_url, table_name)
        return _to_result(_to_json(schema))
    except Exception as e:
        return _to_error(f"Не удалось получить схему: {e}")


async def handle_resolve_uuid(arguments: dict) -> list[TextContent]:
    """Разрешить UUID в человекочитаемое имя: поиск в метаданных и таблицах данных.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        uuid: UUID для разрешения.
        table_name: Имя таблицы для ускорения поиска (опционально).
    """
    db_url: str = arguments.get("db_url", "")
    uuid_str: str = arguments.get("uuid", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not uuid_str:
        return _to_error("Параметр 'uuid' обязателен")
    table_name: str | None = arguments.get("table_name") or None
    try:
        results = resolve_uuid(db_url, uuid_str, table_name=table_name)
        return _to_result(_to_json(results))
    except Exception as e:
        return _to_error(f"Не удалось разрешить UUID: {e}")


async def handle_get_blob(arguments: dict) -> list[TextContent]:
    """Извлечь и декомпрессировать бинарные блобы конфигурации 1С.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        uuid: UUID объекта для поиска в filename.
        table: Таблица-источник: config (по умолчанию), configcas, configsave.
        raw: Если True — включить полное содержимое блоба (по умолчанию False).
    """
    db_url: str = arguments.get("db_url", "")
    uuid_str: str = arguments.get("uuid", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not uuid_str:
        return _to_error("Параметр 'uuid' обязателен")
    table: str = arguments.get("table", "config")
    raw: bool = arguments.get("raw", False)
    try:
        blobs = await extract_metadata_blobs(
            db_url,
            table=table,  # type: ignore[arg-type]
            uuid=uuid_str,
            raw=raw,
            limit=5,
        )
        return _to_result(_to_json(blobs))
    except Exception as e:
        return _to_error(f"Не удалось извлечь блоб: {e}")


async def handle_compare_configs(arguments: dict) -> list[TextContent]:
    """Сравнить текущую (config) и предыдущую (configsave) версии конфигурации.

    Находит добавленные, удалённые и изменённые объекты.
    Для изменённых объектов сравнивает BSL-код (если доступен).

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
    """
    db_url: str = arguments.get("db_url", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    try:
        current = build_llm_context(db_url, table="config")
        saved = build_llm_context(db_url, table="configsave")

        cur_map: dict[str, dict] = {}
        for obj in current.get("objects", []):
            uid = obj.get("uuid", "")
            if uid:
                cur_map[uid] = obj

        sav_map: dict[str, dict] = {}
        for obj in saved.get("objects", []):
            uid = obj.get("uuid", "")
            if uid:
                sav_map[uid] = obj

        cur_uuids = set(cur_map)
        sav_uuids = set(sav_map)

        added_uuids = cur_uuids - sav_uuids
        removed_uuids = sav_uuids - cur_uuids
        common_uuids = cur_uuids & sav_uuids

        lines: list[str] = []
        lines.append("=== Сравнение конфигураций: config vs configsave ===\n")

        if added_uuids:
            lines.append(f"--- Добавлено ({len(added_uuids)} объектов) ---")
            for uid in sorted(added_uuids):
                obj = cur_map[uid]
                tech = obj.get("tech_name") or "(no name)"
                cat = obj.get("category") or "?"
                lines.append(f"  + {uid} | {tech} [{cat}]")
            lines.append("")

        if removed_uuids:
            lines.append(f"--- Удалено ({len(removed_uuids)} объектов) ---")
            for uid in sorted(removed_uuids):
                obj = sav_map[uid]
                tech = obj.get("tech_name") or "(no name)"
                cat = obj.get("category") or "?"
                lines.append(f"  - {uid} | {tech} [{cat}]")
            lines.append("")

        if common_uuids:
            lines.append(f"--- Изменено ({len(common_uuids)} общих объектов) ---")
            changed = 0
            for uid in sorted(common_uuids):
                cur = cur_map[uid]
                sav = sav_map[uid]
                # Сравниваем display_names и type_num как признаки изменений
                cur_dn = cur.get("display_names", {})
                sav_dn = sav.get("display_names", {})
                cur_tn = cur.get("type_num")
                sav_tn = sav.get("type_num")
                if cur_dn != sav_dn or cur_tn != sav_tn:
                    changed += 1
                    tech = cur.get("tech_name") or "(no name)"
                    lines.append(f"  ~ {uid} | {tech}")
                    lines.append(f"      type_num: {sav_tn} → {cur_tn}" if cur_tn != sav_tn else "")
                    # Показать изменения в отображаемых именах
                    all_langs = set(cur_dn) | set(sav_dn)
                    for lang in sorted(all_langs):
                        old = sav_dn.get(lang, "(none)")
                        new = cur_dn.get(lang, "(none)")
                        if old != new:
                            lines.append(f"      [{lang}]: {old} → {new}")
            if changed == 0:
                lines.append("  (изменений в именах и type_num не обнаружено)")
            lines.append("")

        total = len(cur_uuids)
        lines.append(
            f"Итого: {total} объектов в текущей, "
            f"{len(sav_uuids)} в сохранённой, "
            f"{len(added_uuids)} добавлено, "
            f"{len(removed_uuids)} удалено."
        )

        return _to_result("\n".join(lines))
    except Exception as e:
        return _to_error(f"Не удалось сравнить конфигурации: {e}")


# ── Memory handlers ───────────────────────────────────────────────────────


async def handle_load_notes(arguments: dict) -> list[TextContent]:
    """Загрузить заметки для базы данных — накопленные между сессиями
    маппинги (tech_name → table_name), правила и паттерны ошибок.

    Вызывай этот инструмент **в начале каждого диалога**, сразу после
    того как узнал db_url. Это даст тебе знания из прошлых сессий
    с этой же базой данных.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
    """
    db_url = arguments.get("db_url", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    try:
        notes = _load_notes(db_url)
        return _to_result(_to_json(notes))
    except Exception as e:
        return _to_error(f"Не удалось загрузить заметки: {e}")


async def handle_save_notes(arguments: dict) -> list[TextContent]:
    """Сохранить заметки для базы данных — передать накопленные знания
    в постоянное хранилище для использования в будущих сессиях.

    Вызывай этот инструмент **перед завершением диалога**, когда
    накопила важные маппинги, правила и паттерны.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        notes: JSON-объект с полями:
            mappings - dict tech_name → table_name
            rules - list[str] правил
            patterns - list[dict] паттернов ошибок
    """
    db_url = arguments.get("db_url", "")
    notes = arguments.get("notes", {})
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not notes:
        return _to_error("Параметр 'notes' обязателен")
    try:
        _save_notes(db_url, notes)
        mappings = len(notes.get("mappings", {}))
        rules = len(notes.get("rules", []))
        patterns = len(notes.get("patterns", []))
        return _to_result(f"Сохранено {mappings} маппингов, {rules} правил, {patterns} паттернов.")
    except Exception as e:
        return _to_error(f"Не удалось сохранить заметки: {e}")


async def handle_save_trajectory(arguments: dict) -> list[TextContent]:
    """Сохранить траекторию текущего диалога — полную запись вопросов,
    вызовов инструментов и ответов для последующего fine-tuning.

    Вызывай **перед завершением диалога**, когда диалог содержателен
    (было несколько осмысленных вопросов и корректных ответов).

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        messages: список сообщений диалога в формате OpenAI:
            [{"role": "user|assistant|tool", "content": "..."}, ...]
        metadata: опциональный объект с доп. информацией
            (например, {"model": "qwen2.5:27b", "tags": ["catalogs"]})
    """
    db_url = arguments.get("db_url", "")
    messages = arguments.get("messages", [])
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    if not messages:
        return _to_error("Параметр 'messages' обязателен — передай массив сообщений диалога")
    metadata = arguments.get("metadata", {})
    try:
        trajectory = {
            "messages": messages,
            "metadata": metadata,
        }
        filename = _save_trajectory(db_url, trajectory)
        return _to_result(f"Траектория сохранена: {filename}")
    except Exception as e:
        return _to_error(f"Не удалось сохранить траекторию: {e}")


async def handle_get_trajectories(arguments: dict) -> list[TextContent]:
    """Загрузить последние траектории диалогов для этой базы данных.
    Полезно для анализа типичных паттернов вопросов и ошибок.

    Параметры:
        db_url: SQLAlchemy URL базы данных 1С.
        limit: количество траекторий (по умолчанию 5).
    """
    db_url = arguments.get("db_url", "")
    if not db_url:
        return _to_error("Параметр 'db_url' обязателен")
    limit = arguments.get("limit", 5)
    try:
        trajs = _load_recent_trajectories(db_url, limit=limit)
        return _to_result(_to_json(trajs))
    except Exception as e:
        return _to_error(f"Не удалось загрузить траектории: {e}")


# ── Tool registry ─────────────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool(
        name="get_context",
        description="Полная карта метаданных 1С: все объекты, их UUID, type_num, "
        "категории, имена таблиц и display_names",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "table": {
                    "type": "string",
                    "description": "Таблица-источник: config (по умолчанию), configcas, configsave",
                    "default": "config",
                },
            },
            "required": ["db_url"],
        },
    ),
    Tool(
        name="describe_object",
        description="Полное описание объекта 1С по UUID: метаданные, схема "
        "таблицы, семплы данных, блоб",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID объекта метаданных",
                },
                "sample_rows": {
                    "type": "integer",
                    "description": "Количество семплов строк (по умолчанию 3)",
                    "default": 3,
                },
                "resolve_refs": {
                    "type": "boolean",
                    "description": "Разрешать UUID-ссылки в семплах",
                    "default": False,
                },
            },
            "required": ["db_url", "uuid"],
        },
    ),
    Tool(
        name="find_objects",
        description="Поиск объектов метаданных 1С по имени или синониму",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "keyword": {
                    "type": "string",
                    "description": "Ключевое слово для поиска",
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимум результатов (по умолчанию 50)",
                    "default": 50,
                },
            },
            "required": ["db_url", "keyword"],
        },
    ),
    Tool(
        name="get_graph",
        description="Граф связей объекта 1С: владелец, родитель, поля-ссылки, обратные ссылки",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID объекта метаданных",
                },
                "mermaid": {
                    "type": "boolean",
                    "description": "Если True — вернуть Mermaid-диаграмму, иначе текст",
                    "default": False,
                },
            },
            "required": ["db_url", "uuid"],
        },
    ),
    Tool(
        name="run_sql",
        description="Выполнить read-only SQL-запрос к базе 1С. Разрешены: "
        "SELECT, EXPLAIN, WITH, SHOW, DESCRIBE",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "query": {
                    "type": "string",
                    "description": "SQL-запрос (SELECT/EXPLAIN/WITH/SHOW/DESCRIBE)",
                },
            },
            "required": ["db_url", "query"],
        },
    ),
    Tool(
        name="get_table_schema",
        description="Структура таблицы 1С: колонки, типы данных, nullable",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "table_name": {
                    "type": "string",
                    "description": "Имя таблицы (например, _Reference117)",
                },
            },
            "required": ["db_url", "table_name"],
        },
    ),
    Tool(
        name="resolve_uuid",
        description="Разрешить UUID в человекочитаемое имя: поиск по метаданным "
        "и таблицам данных 1С",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID для разрешения",
                },
                "table_name": {
                    "type": "string",
                    "description": "Имя таблицы для ускорения поиска (опционально)",
                },
            },
            "required": ["db_url", "uuid"],
        },
    ),
    Tool(
        name="get_blob",
        description="Извлечь и декомпрессировать блобы метаданных 1С из "
        "config/configcas/configsave",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID объекта для поиска",
                },
                "table": {
                    "type": "string",
                    "description": "Таблица: config (по умолчанию), configcas, configsave",
                    "default": "config",
                },
                "raw": {
                    "type": "boolean",
                    "description": "Включить полное содержимое блоба",
                    "default": False,
                },
            },
            "required": ["db_url", "uuid"],
        },
    ),
    Tool(
        name="compare_configs",
        description="Сравнить текущую (config) и предыдущую (configsave) "
        "версии конфигурации 1С: добавленные, удалённые, изменённые объекты",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
            },
            "required": ["db_url"],
        },
    ),
    Tool(
        name="load_notes",
        description="Загрузить заметки для этой базы — маппинги, правила и "
        "паттерны, накопленные в прошлых сессиях. Вызывай это в начале диалога.",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
            },
            "required": ["db_url"],
        },
    ),
    Tool(
        name="save_notes",
        description="Сохранить заметки по этой базе — маппинги tech_name→table_name, "
        "правила и паттерны ошибок для использования в будущих сессиях. "
        "Вызывай перед завершением диалога.",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "notes": {
                    "type": "object",
                    "description": "JSON: mappings, rules[], patterns[]",
                },
            },
            "required": ["db_url", "notes"],
        },
    ),
    Tool(
        name="save_trajectory",
        description="Сохранить траекторию диалога для fine-tuning — полную "
        "запись вопросов, вызовов инструментов и ответов.",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "messages": {
                    "type": "array",
                    "description": "Сообщения диалога: [{role, content}]",
                    "items": {"type": "object"},
                },
                "metadata": {
                    "type": "object",
                    "description": "Опционально: модель, теги и т.д.",
                },
            },
            "required": ["db_url", "messages"],
        },
    ),
    Tool(
        name="get_trajectories",
        description="Загрузить последние траектории диалогов для этой базы."
        " Полезно для анализа типичных паттернов вопросов.",
        inputSchema={
            "type": "object",
            "properties": {
                "db_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL базы данных 1С",
                },
                "limit": {
                    "type": "integer",
                    "description": "Количество траекторий (по умолчанию 5)",
                    "default": 5,
                },
            },
            "required": ["db_url"],
        },
    ),
]

# Карта имя_инструмента → обработчик
HANDLERS: dict[str, Any] = {
    "get_context": handle_get_context,
    "describe_object": handle_describe_object,
    "find_objects": handle_find_objects,
    "get_graph": handle_get_graph,
    "run_sql": handle_run_sql,
    "get_table_schema": handle_get_table_schema,
    "resolve_uuid": handle_resolve_uuid,
    "get_blob": handle_get_blob,
    "compare_configs": handle_compare_configs,
    "load_notes": handle_load_notes,
    "save_notes": handle_save_notes,
    "save_trajectory": handle_save_trajectory,
    "get_trajectories": handle_get_trajectories,
}


# ── Server setup ──────────────────────────────────────────────────────────


def create_server() -> Server:
    """Создать и настроить MCP-сервер py1cv8."""
    server = Server("py1cv8", instructions=SYSTEM_PROMPT)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def handle_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = HANDLERS.get(name)
        if handler is None:
            return _to_error(f"Неизвестный инструмент: {name}")
        try:
            return await handler(arguments)
        except Exception as e:
            error_text = str(e)
            # Автосохранение ошибки в траектории для fine-tuning
            db_url = arguments.get("db_url", "")
            if db_url and name in (
                "run_sql",
                "resolve_uuid",
                "get_blob",
                "describe_object",
                "get_context",
                "get_graph",
            ):
                try:
                    traj = {
                        "messages": [
                            {"role": "user", "content": f"Вызов инструмента: {name}"},
                            {"role": "assistant", "content": f"Параметры: {arguments}"},
                            {"role": "tool", "content": f"ОШИБКА: {error_text}"},
                        ],
                        "metadata": {
                            "type": "error",
                            "tool": name,
                            "error": error_text[:500],
                        },
                    }
                    _save_trajectory(db_url, traj)
                except Exception:
                    pass  # Не мешаем основной ошибке
            return _to_error(error_text)

    return server


# ── Entry points ──────────────────────────────────────────────────────────


async def run_stdio(server: Server | None = None) -> None:
    """Запустить MCP-сервер на stdio-транспорте."""
    if server is None:
        server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_sse(
    server: Server | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8100,
) -> None:
    """Запустить MCP-сервер на SSE+HTTP транспорте.

    Args:
        server: Экземпляр MCP-сервера (создаётся новый, если None).
        host: Хост для привязки (по умолч. 127.0.0.1).
        port: Порт (по умолч. 8100).

    Клиент подключается к http://{host}:{port}/sse и шлёт POST-сообщения
    на http://{host}:{port}/messages/.
    """
    if server is None:
        server = create_server()

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    routes = [
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ]
    starlette_app = Starlette(routes=routes)

    cfg = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    uvicorn_server = uvicorn.Server(cfg)
    await uvicorn_server.serve()


async def main(
    transport: str = "stdio",
    *,
    host: str = "127.0.0.1",
    port: int = 8100,
) -> None:
    """Запустить MCP-сервер с указанным транспортом.

    Args:
        transport: "stdio" (по умолч.) или "sse".
        host: Хост для SSE-транспорта.
        port: Порт для SSE-транспорта.
    """
    if transport == "stdio":
        await run_stdio()
    elif transport == "sse":
        await run_sse(host=host, port=port)
    else:
        msg = f"Неизвестный транспорт: {transport}. Допустимые: stdio, sse"
        raise ValueError(msg)


if __name__ == "__main__":
    asyncio.run(main())
