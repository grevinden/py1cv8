# py1cv8 — MCP-сервер для SQL-доступа к базам 1С

**py1cv8** даёт нейросети (LLM) прямой read-only SQL-доступ к базам 1С (PostgreSQL) с полным пониманием метаданных — минуя сервер приложения 1С:Предприятие.

## Возможности

### 🔍 Schema discovery
Автоматически читает и связывает три источника метаданных:

1. **DBNames** — бинарный blob в таблице `params`. Распаковывает zlib, парсит записи вида `{UUID,"Reference",53}`, строит соответствие `1C-тип → таблица БД`
2. **information_schema.columns** — читает все колонки `_*` таблиц, включая primary key constraints
3. **Config metadata** — читает UUID → type_num → display_name из сжатых блобов таблицы `config`

Результат: объект `ObjectInfo` с русским именем, категорией, списком колонок, связями и подтаблицами.

### 🧠 Граф связей
Автоматически определяет межтабличные ссылки:
- `_*RRef` → внешняя ссылка на другую таблицу (по номеру таблицы)
- `_IDRRef` → self-reference (ссылка на себя)
- `Owner`, `Parent`, `Recorder`, `Folder` — типизированные ссылки

### 🛠️ MCP-сервер (4 tools)

Сервер реализует протокол **Model Context Protocol** (stdio транспорт) и предоставляет LLM четыре инструмента:

| Tool | Описание |
|------|----------|
| `query` | Выполнить read-only SQL SELECT. Автоматический `LIMIT`, безопасность — только SELECT/WITH |
| `schema` | Описать таблицу (колонки, типы, nullable, PK) или вывести все таблицы с категориями |
| `metadata` | Поиск объектов 1С по UUID, категории или имени |
| `analyze` | Полный бизнес + технический анализ: колонки, связи, подтаблицы |

Дополнительно: **Resources** по URI `1c://{db}/tables/{table}` возвращают JSON-схему.

### 📦 BSL extraction (legacy)
Извлечение BSL-модулей из таблиц `config` и `configcas`:
- Декомпрессия zlib (wbits=-15/+15)
- Детекция кодировок через chardet
- Разделение блобов по BOM-маркерам
- Инкрементальный режим через checkpoint-файл

## Быстрый старт

```bash
# MCP-сервер (для подключения LLM)
python -m py1cv8 mcp

# Сводка схемы БД
python -m py1cv8 schema MessageCenter

# BSL extraction (legacy)
python -m py1cv8
```

## Тесты

```bash
python -m pytest tests/       # 44 тестов
python -m ruff check .        # 0 errors
python -m mypy src/py1cv8/    # 0 errors
```

## Доступные БД

| База | Таблиц | Объектов 1С | Источник |
|------|--------|-------------|----------|
| `MessageCenter` | 94 | 19 (Catalogs=7, InfoRg=3, Const=3, Enums=2, ScheduledJobs=2, Chrc=1, Docs=1) | config |
| `test` | 100 | 8 | configcas |

## Категории объектов

Полный список категорий с type_num:

| Категория | type_num | Примеры |
|-----------|----------|---------|
| Catalogs (Reference) | 57 (OtherTypes) | Контрагенты, Номенклатура |
| Documents | 22, 40 | РеализацияТоваров |
| DataProcessors | 1, 4, 17, 19 | Исполняемый запрос |
| CommonModules | 2 | Общие модули (170) |
| CommonForms | 0 | Формы (263 meta) |
| CommonTemplates | 12 | Макеты (66) |
| Constants | 16 | Константы (3) |
| Enums | 20 | Перечисления (2) |
| InformationRegisters | 33 | Регистры сведений |
| ChartsOfCharacteristicTypes | 34 | Планы видов характеристик |
| Roles | 6, 7 | Роли (6) |
| Subsystems | 3 | Подсистемы (9) |

## Архитектура

```
         ┌──────────────────────┐
         │    LLM / Claude      │
         │   (MCP клиент)       │
         └──────┬───────────────┘
                │ stdio
         ┌──────▼───────────────┐
         │   mcp_server.py      │  ← MCP SDK, 4 tools + resources
         └──────┬───────────────┘
                │
         ┌──────▼───────────────┐
         │   schema.py          │  ← Registry, DBNames parser, graph
         └──────┬───────────────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
 params   information_   config
 DBNames  schema.columns  metadata
 (binary)  (SQL)        (binary)
```

## Соединение с БД

- Хост: `localhost:5433`
- Пользователь: `postgres`
- Режим: **read-only** (autocommit, SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY)
- Никаких INSERT/UPDATE/DELETE ни при каких условиях

## Структура проекта

```
src/py1cv8/
├── __init__.py
├── __main__.py       # Точка входа (3 режима)
├── extract.py        # BSL extraction (legacy)
├── schema.py         # Schema discovery + DBNames
└── mcp_server.py     # MCP-сервер
tests/
├── test_extract.py   # 30 тестов legacy
└── test_schema.py    # 14 тестов schema
```

## Требования

- Python ≥ 3.13
- PostgreSQL (локальный) с базами `MessageCenter` и/или `test`
- Зависимости: `psycopg2-binary`, `chardet`, `asyncpg`, `mcp`
