"""Typer CLI for py1cv8 — context generation, SQL, blob, find, schema, resolve."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from py1cv8.agent_prompt import AGENT_PROMPT
from py1cv8.db import normalise_db_url
from py1cv8.mcp_server import main as run_mcp_server
from py1cv8.output import print_json
from py1cv8.sql.orm import ConfigTable

app = typer.Typer(
    name="py1cv8",
    help="1C metadata parser + LLM context generator",
    rich_markup_mode="markdown",
)


@app.command()
def agent() -> None:
    """Показать промпт для LLM-агента — инструкции по автономному анализу 1С.

    Выводит полный набор правил, команды и стратегии анализа, которые
    нейросеть использует для работы с базой данных 1С через **py1cv8**.

    **Содержание промпта:**
    - Доступные команды (`context`, `describe`, `graph`, ...)
    - Стратегия анализа связей между объектами
    - Типичные ошибки и как их избежать
    - Примеры рабочих процессов
    - Ограничения и формат ответа пользователю
    """
    typer.echo(AGENT_PROMPT)


@app.command()
def mcp(
    transport: Annotated[
        str,
        typer.Option(
            "--transport",
            "-t",
            help="Транспорт: stdio (по умолч.) или sse (HTTP+SSE)",
        ),
    ] = "stdio",
    host: Annotated[
        str,
        typer.Option(
            "--host",
            "-H",
            help="Хост для SSE-транспорта",
        ),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Порт для SSE-транспорта",
        ),
    ] = 8100,
) -> None:
    """Запустить MCP-сервер для интеграции с LLM-клиентами.

    Сервер реализует **Model Context Protocol** — позволяет LLM (Claude Desktop,
    VS Code, Copilot и др.) вызывать инструменты для анализа 1С-метаданных:
    - `get_context` — полная карта метаданных
    - `describe_object` — детальное описание объекта по UUID
    - `find_objects` — поиск объектов по имени
    - `get_graph` — граф связей объекта
    - `run_sql` — read-only SQL-запросы
    - `get_table_schema` — структура таблицы
    - `resolve_uuid` — UUID → человекочитаемое имя
    - `get_blob` — извлечение и декомпрессия блобов
    - `compare_configs` — сравнение версий конфигурации

    **Транспорты:**
    - `stdio` (по умолчанию) — для Claude Desktop, VS Code через локальный запуск
    - `sse` (HTTP+SSE) — для удалённого подключения, веб-клиентов, Docker

    **Примеры:**
    ```bash
    python -m py1cv8 mcp                                    # stdio
    python -m py1cv8 mcp --transport sse --port 8100        # SSE+HTTP
    python -m py1cv8 mcp -t sse -H 0.0.0.0 -p 8100          # на всех интерфейсах
    ```

    **Подключение (stdio):**
    ```json
    {
      "mcpServers": {
        "py1cv8": {
          "command": "python",
          "args": ["-m", "py1cv8", "mcp"]
        }
      }
    }
    ```

    **Подключение (SSE):**
    ```json
    {
      "mcpServers": {
        "py1cv8": {
          "url": "http://localhost:8100/sse"
        }
      }
    }
    ```
    """
    asyncio.run(run_mcp_server(transport=transport, host=host, port=port))


@app.command()
def context(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5433/dbname)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    with_tables: Annotated[
        bool,
        typer.Option("--with-tables", "-t", help="Only show objects that have a physical table"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
    table: Annotated[
        str,
        typer.Option(
            "--table", "-t", help="Source table: config (default), configcas, or configsave"
        ),
    ] = "config",
) -> None:
    """Print LLM-friendly context from 1C metadata.

    Parameters
    ----------
    table : str
        Таблица-источник метаданных: config (текущая конфигурация),
        configcas (кэш), configsave (предыдущая версия).
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.context import build_llm_context

    ctx = build_llm_context(db_url, table=table)
    if with_tables:
        ctx["objects"] = [o for o in ctx["objects"] if o.get("table_name")]
        ctx["object_count"] = len(ctx["objects"])
    print_json(ctx, pretty=pretty)


@app.command()
def sql(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (e.g. postgresql+psycopg2://user:pass@host:5433/dbname)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    query: Annotated[
        str,
        typer.Argument(help="SQL query to execute"),
    ],
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Выполнить read-only SQL-запрос и вывести результат как JSON.

    Поддерживаются только **SELECT**, **EXPLAIN** и **WITH** —
    любые модифицирующие запросы блокируются.

    **Важно:** таблицы 1С имеют технические имена (`_Reference53`,
    `_Document209`, `_InfoRg148`). Используй `context` или `tables`,
    чтобы узнать соответствие tech_name → table_name.

    **Особенности:**
    - Результат возвращается как **JSON-массив** строк
    - UUID и `_IDRRef` конвертируются в hex-строки
    - При ошибке показывает человекочитаемое сообщение без traceback
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.sql_proxy import ReadOnlyError, execute_readonly

    try:
        rows = execute_readonly(db_url, query)
        print_json(rows, pretty=pretty)
    except ReadOnlyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
async def blob(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    table: Annotated[
        ConfigTable,
        typer.Option(
            "--table", "-t", help="Source table: config (default), configcas, or configsave"
        ),
    ] = "config",
    uuid: Annotated[
        str | None,
        typer.Option("--uuid", "-u", help="UUID to search for in filename"),
    ] = None,
    filename: Annotated[
        str | None,
        typer.Option("--filename", "-f", help="Filename ILIKE pattern"),
    ] = None,
    partno: Annotated[
        int | None,
        typer.Option("--partno", help="Part number filter"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max rows"),
    ] = 20,
    raw_content: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Include decompressed blob content (adds ~50KB per row)",
        ),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Извлечь и декомпрессировать блобы конфигурации 1С.

    Читает бинарные блобы из таблиц `config`, `configcas` или `configsave`,
    распаковывает zlib-сжатые данные и парсит метаданные 1С.

    **Режимы вывода:**
    - Без `--raw` — мета-информация: размеры, категория, распарсенные поля
    - С `--raw` — полное содержимое блоба в bracket-формате (+ ~50KB на строку)

    **Источники данных (--table):**
    - `config` — текущая конфигурация (по умолчанию)
    - `configcas` — кэш метаданных
    - `configsave` — предыдущая версия (до применения изменений)
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.blob_fetch import BLOB_FORMAT_DESCRIPTION, extract_metadata_blobs

    rows = await extract_metadata_blobs(
        db_url=db_url,
        table=table,
        filename=filename,
        partno=partno,
        uuid=uuid,
        limit=limit,
        raw=raw_content,
    )
    output: dict | list[dict] = {
        "blobs": rows,
        "format_description": BLOB_FORMAT_DESCRIPTION if raw_content else None,
    }
    print_json(output, pretty=pretty)


@app.command()
def find(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    keyword: Annotated[
        str,
        typer.Argument(help="Keyword to search in object names"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max results"),
    ] = 50,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Найти объекты метаданных по имени.

    Ищет по `tech_name` (техническое имя) и `display_names`
    (человекочитаемые имена на разных языках).

    **Алгоритм:**
    1. Сначала точное совпадение подстроки (case-insensitive)
    2. Потом fuzzy-поиск (похожие имена)
    3. Результаты сортируются по релевантности

    **Типичное использование:**
    ```
    py1cv8 find <db_url> Контрагенты
    py1cv8 find <db_url> модуль
    py1cv8 find <db_url> обработка
    ```
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.find_objects import find_objects

    rows = find_objects(db_url, keyword, limit=limit)
    print_json(rows, pretty=pretty)


@app.command()
def schema(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    table_name: Annotated[
        str,
        typer.Argument(help="Table name to describe (e.g. _Reference53)"),
    ],
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Показать структуру таблицы через **information_schema**.

    Выводит список колонок с их типами данных, длиной, nullable,
    и прочими атрибутами из `information_schema.columns`.

    **Если таблица не найдена** — показывает похожие имена
    (например, `_Reference53` вместо `Reference53`).

    **Пример:**
    ```
    py1cv8 schema <db_url> _Reference53
    ```
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.schema_describe import describe_table

    rows = describe_table(db_url, table_name)
    print_json(rows, pretty=pretty)


@app.command()
def resolve(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID to resolve (with or without dashes)"),
    ],
    table_name: Annotated[
        str | None,
        typer.Argument(help="Optional table name (e.g. _Reference53)"),
    ] = None,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", hidden=True, help="Output as JSON (default)"),
    ] = False,
) -> None:
    """Преобразовать UUID в человекочитаемое имя (_Description / _Code).

    Ищет UUID в метаданных конфигурации и во всех таблицах данных,
    возвращая найденные `_Description`, `_Code` и другую информацию.

    **Форматы UUID:**
    - Полный: `550e8400-e29b-41d4-a716-446655440000`
    - Без дефисов: `550e8400e29b41d4a716446655440000`
    - Частичный (последние 12 символов): `446655440000`

    **Примеры:**
    ```
    py1cv8 resolve <db_url> 550e8400-e29b-41d4-a716-446655440000
    py1cv8 resolve <db_url> 446655440000
    py1cv8 resolve <db_url> 550e8400... _Reference53
    ```
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.resolve_uuid import resolve_uuid

    rows = resolve_uuid(db_url, uuid, table_name=table_name)
    print_json(rows, pretty=pretty or json_output)


@app.command()
async def describe(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID of the metadata object"),
    ],
    sample_rows: Annotated[
        int,
        typer.Option("--sample-rows", "-n", help="Number of sample data rows"),
    ] = 3,
    resolve_refs: Annotated[
        bool,
        typer.Option("--resolve", "-r", help="Resolve UUID refs to names in sample data"),
    ] = False,
    no_blob: Annotated[
        bool,
        typer.Option("--no-blob", help="Skip raw blob content in output"),
    ] = False,
) -> None:
    """Полное описание объекта метаданных 1С по UUID.

    Объединяет четыре источника в один читаемый отчёт:
    - **Метаданные** — категория, type_num, display_names из `context`
    - **Схема таблицы** — колонки с расшифровкой типов 1С
    - **Sample data** — N строк данных с разрешением UUID-ссылок
    - **Blob** — содержимое блоба конфигурации (можно отключить `--no-blob`)

    **Флаги:**
    - `-n` / `--sample-rows` — сколько строк sample data показать (по умолч. 3)
    - `-r` / `--resolve` — разрешить UUID-ссылки в имена (_Description)
    - `--no-blob` — не показывать сырой blob (ускоряет вывод)
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.describe_object import describe_text

    text = await describe_text(
        db_url,
        uuid,
        sample_limit=sample_rows,
        resolve_refs=resolve_refs,
        no_blob=no_blob,
    )
    typer.echo(text)


@app.command()
def lookup(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str,
        typer.Argument(help="UUID to search (with or without dashes)"),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Max tables to search"),
    ] = 50,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Глубокий поиск UUID по **всем** таблицам базы данных.

    В отличие от `resolve`, который ищет только в метаданных и
    стандартных таблицах, `lookup` сканирует **каждую** таблицу
    с колонкой `_IDRRef` и ищет совпадение.

    **Форматы UUID:**
    - Полный: `550e8400-e29b-41d4-a716-446655440000`
    - Без дефисов: `550e8400e29b41d4a716446655440000`
    - Частичный: `446655440000` (последние 12 символов)

    **Применение:** когда `resolve` не нашёл объект — `lookup`
    проверит все таблицы, включая служебные.
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.lookup_uuid import lookup_uuid

    rows = lookup_uuid(db_url, uuid, limit=limit)
    print_json(rows, pretty=pretty)


@app.command()
def tables(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    only_with_table: Annotated[
        bool,
        typer.Option("--with-table", "-t", help="Only objects that have a physical table"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON"),
    ] = False,
) -> None:
    """Маппинг tech_name → физическая таблица для всех объектов.

    Показывает какие объекты метаданных имеют физические таблицы
    в базе данных и как они называются.

    **Флаг `-t` / `--with-table`:** показывает только те объекты,
    у которых есть физическая таблица (отфильтровывает общие модули,
    обработки и другие объекты без таблиц).

    **Пример вывода:**
    ```
    {"tech_name": "Справочник.Контрагенты", "table_name": "_Reference53"}
    ```
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.list_tables import list_tables

    rows = list_tables(db_url)
    if only_with_table:
        rows = [r for r in rows if r.get("table_name")]
    print_json(rows, pretty=pretty)


@app.command()
async def graph(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    uuid: Annotated[
        str | None,
        typer.Argument(help="UUID of the object (optional with --all)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output raw JSON instead of formatted text"),
    ] = False,
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON (only with --json)"),
    ] = False,
    mermaid_output: Annotated[
        bool,
        typer.Option("--mermaid", "-m", help="Output Mermaid classDiagram"),
    ] = False,
    all_flag: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show graph for ALL objects"),
    ] = False,
) -> None:
    """Граф связей объекта метаданных 1С.

    Показывает одним вызовом:
    - **Владелец (Owner)** — кто владеет объектом
    - **Родитель (Parent)** — иерархический родитель
    - **Поля-ссылки** — `_fld{N}rref`/`_rtref` с именами полей
    - **Цели ссылок** — разрешённые UUID → имена таблиц + tech_name
    - **Тип-дискриминаторы** — значения `_type` колонок
    - **Обратные ссылки** — какие объекты ссылаются на этот

    **Формат вывода:**
    - `-j` / `--json` — сырой JSON для машинной обработки
    - `-m` / `--mermaid` — Mermaid classDiagram для Markdown
    - Без флагов — человекочитаемый текст

    **Для всей базы:** используй `--all` / `-a`
    """
    db_url = normalise_db_url(db_url)
    from py1cv8.graph import (
        build_graph,
        graph_all_mermaid,
        graph_all_text,
        graph_mermaid,
        graph_text,
    )  # fmt: skip

    if all_flag:
        if mermaid_output:
            typer.echo(await graph_all_mermaid(db_url))
        elif json_output:
            from py1cv8.graph import build_global_graph

            print_json(await build_global_graph(db_url), pretty=pretty)
        else:
            typer.echo(await graph_all_text(db_url))
    elif not uuid:
        typer.echo("Error: provide a UUID or use --all", err=True)
        raise typer.Exit(1)
    elif mermaid_output:
        typer.echo(await graph_mermaid(db_url, uuid))
    elif json_output:
        print_json(await build_graph(db_url, uuid), pretty=pretty)
    else:
        typer.echo(await graph_text(db_url, uuid))


@app.command()
def translate(
    db_url: Annotated[
        str,
        typer.Argument(
            help="Full SQLAlchemy database URL (for table name resolution)",
            envvar="PY1CV8_DB_URL",
            show_envvar=True,
        ),
    ],
    query: Annotated[
        str,
        typer.Argument(help="1C query text or BSL source code (see --bsl)"),
    ],
    bsl_mode: Annotated[
        bool,
        typer.Option("--bsl", "-b", help="Input is BSL code, extract queries from Запрос.Текст"),
    ] = False,
    dialect: Annotated[
        str,
        typer.Option("--dialect", "-d", help="Target SQL dialect: postgresql or mssql"),
    ] = "postgresql",
    pretty: Annotated[
        bool,
        typer.Option("--pretty", "-p", help="Pretty-print JSON output"),
    ] = False,
) -> None:
    """Трансляция языка запросов 1С в SQL с подстановкой реальных имён таблиц.

    Поддерживает:
    - **SELECT**, **JOIN**, **UNION**, **CASE-WHEN**
    - Группировка и агрегатные функции
    - Даты: `ГОД`, `МЕСЯЦ`, `ДОБАВИТЬКДАТЕ`, `РАЗНОСТЬДАТ`, `ДАТАВРЕМЯ`
    - Виртуальные таблицы: `Остатки`, `Обороты`, `СрезПоследних`
    - Параметры: `&Имя` → `:Имя` (SQLAlchemy bind params)
    - Вложенные запросы

    **Режимы:**
    - Без `--bsl` — чистый запрос 1С одной строкой
    - С `--bsl` — BSL-код с `Запрос.Текст = "..."` (извлекает все запросы)

    **--dialect:** `postgresql` (по умолч.) или `mssql`

    **Примеры:**
    ```
    py1cv8 translate <db_url> "ВЫБРАТЬ Наименование ИЗ Справочник.Контрагенты"
    py1cv8 translate <db_url> --bsl "Запрос.Текст = \"ВЫБРАТЬ 1\";" --dialect mssql
    ```
    """
    db_url = normalise_db_url(db_url)
    from dataclasses import asdict

    # Build resolver from context
    from py1cv8.context import build_llm_context
    from py1cv8.query_translator import (
        extract_queries_from_bsl,
        translate_1c_query,
    )

    ctx = build_llm_context(db_url)
    table_by_name: dict[tuple[str, str], str] = {}
    for obj in ctx["objects"]:
        tn = obj.get("table_name")
        tech = obj.get("tech_name") or ""
        if tn and "." in tech:
            obj_type, obj_name = tech.split(".", 1)
            table_by_name[(obj_type, obj_name)] = tn

    def resolver(obj_type: str, obj_name: str) -> str | None:
        return table_by_name.get((obj_type, obj_name))

    try:
        if bsl_mode:
            result = extract_queries_from_bsl(query, resolver=resolver, dialect=dialect)
            output = asdict(result)
        else:
            tq = translate_1c_query(query, resolver=resolver, dialect=dialect)
            output = asdict(tq)

        print_json(output, pretty=pretty)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
