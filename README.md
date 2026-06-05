# py1cv8

**Дайте LLM понять вашу базу 1С.**

`py1cv8` — прослойка между нейросетью и базой 1С (PostgreSQL или MSSQL). Она достаёт метаданные из двоичного конфига, объясняет LLM правила именования таблиц и даёт выполнять read-only SQL.

Никакого сервера приложений 1С не нужно. Просто доступ к базе.

---

## Как это работает

```
Вопрос от человека:
  "сколько заказов в январе?"
        │
        ▼
py1cv8 context "postgresql://..." ──────► JSON с метаданными
  • 897 объектов конфигурации                 │
  • type_num → категория 1С                   │
  • правила DBNames (_Reference{N}...)        │
  • правила связей (_IDRRef → _FldRRef)       │
        │                                     │
        ▼                                     ▼
┌─────────────────────────────────────────────────┐
│  LLM читает JSON как документацию:               │
│                                                  │
│  "Ага, type_num 22 = Documents,                  │
│   значит таблица _Document{N}.                   │
│   Ищу через information_schema.columns,          │
│   нахожу _Document209 с колонками _Date_Time,    │
│   _Number, _Posted...                            │
│   Строю SELECT и выполняю через sql."            │
└─────────────────────────────────────────────────┘
        │
        ▼
py1cv8 sql "postgresql://..." "SELECT ..." ──► JSON-результат
        │
        ▼
LLM отвечает человеку
```

Никакого MCP-сервера. Никаких специальных API. LLM получает данные и сама разбирается.

---

## Быстрый старт

```bash
# Установка
uv add py1cv8

# PostgreSQL
py1cv8 context "postgresql+psycopg2://user:pass@host:5433/dbname"
py1cv8 sql "postgresql+psycopg2://user:pass@host:5433/dbname" \
  "SELECT _IDRRef, _Code FROM _Reference1 LIMIT 10"

# Microsoft SQL Server (через pyodbc)
py1cv8 context "mssql+pyodbc://user:pass@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
py1cv8 sql "mssql+pyodbc://user:pass@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" \
  "SELECT _IDRRef, _Code FROM _Reference1 LIMIT 10"
```

---

## Команды

### `agent` / без аргументов — инструкция для LLM

При запуске без аргументов py1cv8 выводит подробный английский промпт,
который объясняет нейросети, как пользоваться инструментом:

```
py1cv8                                          # → агентский промпт
py1cv8 agent                                    # → то же самое явно
```

Промпт содержит:
- список команд `context`, `sql`, `blob` с параметрами
- правила DBNames (тип объекта → имя таблицы)
- ключевые колонки (_IDRRef, _Code, _Description, _Fld{N}_RRef...)
- пошаговый алгоритм: context → найти type_num → sql
- полные примеры цикла анализа

LLM (Claude, ChatGPT и др.) получает этот промпт при запуске и может
автономно анализировать базу 1С без участия человека.

### `context` — метаданные для LLM

Выдаёт JSON с полной картиной конфигурации 1С: какие объекты есть, какого они типа, как называются их таблицы в БД.

```bash
# PostgreSQL
py1cv8 context "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

# MSSQL
py1cv8 context "mssql+pyodbc://sa:pass@localhost:1433/MessageCenter?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
```

Что внутри:

```json
{
  "db_database": "MessageCenter",
  "object_count": 897,
  "objects": [
    {
      "uuid": "aaa-bbb-ccc",
      "tech_name": "Справочник.Клиенты",
      "display_names": {"ru": "Клиенты"},
      "type_num": 57,
      "category": "Catalogs",
      "table_name": "_Reference53"        ← маппинг UUID → таблица (из DBNames)
    }
  ],
  "type_map": {...},
  "dbnames_rules": "# Документы → _Document{N}\n# Справочники → _Reference{N}",
  "relationship_rules": "# _IDRRef — первичный ключ UUID\n# _Fld{N}_RRef — ссылка на _IDRRef"
}
```

LLM скармливается этот JSON — и она понимает про базу всё:
- какие объекты есть (`objects[]`)
- что за типы (`type_num` + `type_map`)
- как искать таблицы (`dbnames_rules`)
- как соединять таблицы (`relationship_rules`)

### `sql` — read-only запросы

Выполняет SELECT, EXPLAIN, WITH. Всё остальное — ошибка.

```bash
# PostgreSQL — узнать какие таблицы есть
py1cv8 sql "postgresql+psycopg2://user:pass@host:5433/dbname" \
  "SELECT table_name FROM information_schema.tables
   WHERE table_name LIKE '_Document%' ORDER BY table_name"

# MSSQL — те же запросы, другой URL
py1cv8 sql "mssql+pyodbc://sa:pass@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" \
  "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
   WHERE TABLE_NAME LIKE '_Document%' ORDER BY TABLE_NAME"

# смотрим структуру таблицы
py1cv8 sql "postgresql+psycopg2://user:pass@host:5433/dbname" \
  "SELECT column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_name = '_Document209'
   ORDER BY ordinal_position"

# данные
py1cv8 sql "postgresql+psycopg2://user:pass@host:5433/dbname" \
  "SELECT _IDRRef, _Date_Time, _Number, _Posted
   FROM _Document209 WHERE _Date_Time >= '2026-01-01' LIMIT 100"
```

### `blob` — сырой блоб объекта (для LLM-исследований)

Когда `context` показывает объект с незнакомым `type_num` или LLM хочет заглянуть внутрь бинарного конфига — `blob` достаёт блоб, декомпрессит, парсит и возвращает структурированный результат.

```bash
# найти все блобы с определённым UUID в имени
py1cv8 blob "postgresql+psycopg2://user:pass@host:5433/dbname" --uuid "aaa-bbb-ccc"

# найти по шаблону имени файла
py1cv8 blob "postgresql+psycopg2://user:pass@host:5433/dbname" --filename "%metadata%"

# посмотреть конкретную часть (partno) из configcas
py1cv8 blob "postgresql+psycopg2://user:pass@host:5433/dbname" --table configcas --filename "metadata.something" --partno 0

# без фильтра — показывает первые 20 блобов таблицы config
py1cv8 blob "postgresql+psycopg2://user:pass@host:5433/dbname"
```

Что LLM получает — и сырой `content` (скобочный формат), и разобранный `parsed`, и правила формата `format_description`:

```json
{
  "filename": "metadata.xxx",
  "partno": 0,
  "size": 45231,
  "decompressed_size": 128456,
  "content": "{1,\n{57,\n{aaa-bbb-ccc},\"Справочник.Клиенты\",{\"ru\",\"Клиенты\"},1}",
  "parsed": {
    "uuid": "aaa-bbb-ccc",
    "tech_name": "Справочник.Клиенты",
    "display_names": {"ru": "Клиенты"},
    "type_num": 57
  },
  "category": "Catalogs",
  "format_description": "# 1C binary metadata blob format\n\nBlobs in config/configcas store..."
}
```

Три поля, которые LLM может использовать:

| Поле | Описание |
|------|----------|
| `content` | Сырой скобочный формат — если LLM хочет изучить структуру вручную |
| `parsed` | Уже разобранные поля: uuid, tech_name, display_names, type_num |
| `format_description` | Документация формата — что означают `{1,0,...}`, `{type,...}`, MOXCEL, BOM-сплит |
| `category` | Категория из `type_map` (если type_num известен) |

Зачем: LLM вызывает `blob` с UUID неизвестного объекта, получает `parsed` со всеми полями + `format_description` с правилами формата. Даже если type_num неизвестен `type_map` — LLM может прочитать скобочный формат по документации и понять структуру объекта.

### `find` — поиск объектов по имени

```bash
py1cv8 find <db_url> <keyword> [--limit 50]
```

Ищет объекты метаданных, у которых `tech_name` или `display_name` содержит *keyword* (регистронезависимо). Не требует ручного `Select-String` по файлу:

```bash
py1cv8 find "postgresql+psycopg2://..." контрагент --limit 10
# → [{"uuid": "...", "tech_name": "Справочник.Контрагенты", ...}]
```

### `schema` — структура таблицы

```bash
py1cv8 schema <db_url> <table_name>
```

Вытаскивает колонки таблицы из `information_schema.columns` — не надо писать SQL вручную:

```bash
py1cv8 schema "postgresql+psycopg2://..." _Reference53
# → [{"column_name": "_idrref", "data_type": "bytea", ...}, ...]
```

> **Совет:** `py1cv8 describe` делает то же самое плюс метаданные, семплинг данных и blob — одной командой.

### `resolve` — UUID → _Description / _Code (и метаданные)

```bash
py1cv8 resolve <db_url> <uuid> [table_name]
```

Преобразует UUID (из `_IDRRef` или `_Fld{N}_RRef`) в человекочитаемое имя. Если UUID принадлежит объекту метаданных — сразу показывает tech_name и category без SQL. Если это data-запись — ищет по DBNames-таблицам:

```bash
# UUID метаданных — ответ из context без SQL:
py1cv8 resolve "postgresql+psycopg2://..." "e70db5ca-460d-4fb5-bc6e-6460d67278cf"
# → [{"table": "_document209", "tech_name": "Уведомления",
#      "category": "Documents", "source": "metadata"}]

# UUID данных — поиск по таблицам:
py1cv8 resolve "postgresql+psycopg2://..." "550e8400-e29b-..." _Reference53
# → [{"table": "_Reference53", "description": "ООО Ромашка",
#      "code": "00042", "source": "data"}]
```

### `describe` — полное описание объекта по UUID

```bash
py1cv8 describe <db_url> <uuid> [--sample-rows 3]
```

Заменяет 4 ручных запроса. За один вызов показывает:
- метаданные (tech_name, display_names, category, type_num)
- имя таблицы (из DBNames)
- схему таблицы (все колонки с описанием)
- первые N строк данных
- сырой blob конфига

```bash
py1cv8 describe "postgresql+psycopg2://..." "e70db5ca-..."
```
Вывод (человекочитаемый текст):
```
=== e70db5ca-460d-4fb5-bc6e-6460d67278cf ===
Technical name : Уведомления
  [ru]       : Уведомления
Category       : Documents (type_num=40)
Table          : _document209

--- Table schema (_document209) ---
  _idrref                   bytea         Primary UUID key
  _version                  integer       Record version
  _date_time                timestamp     Document date & time
  _number                   USER-DEFINED  Document number
  _posted                   boolean       Document posted flag
  _fld246rref               bytea         Reference field
  _fld222rref               bytea         Reference field
  _fld223                   USER-DEFINED  Custom field #223

--- Sample data (first 3 rows) ---
  Row 1:
    _version    = 0
    _date_time  = 2026-05-17 15:21:42.827003
    _number     = 0000001
    _posted     = True
    _fld223     = Тест

--- Blob content (raw metadata) ---
{1,
{40,c1e406d9-9395-....
```

Для объектов без DBNames (нет таблицы) показывает метаданные + blob.

### Исправление UUID

Во всех командах UUID (`_IDRRef`, `_Fld{N}_RRef`, бинарные поля) сериализуются как hex-строка `550e8400-e29b-41d4-a716-446655440000`, а не как `<memory at 0x...>`. Можно копировать, сравнивать, подставлять в `resolve` и SQL.

---

## Сценарий: LLM + человек

**Человек:** «Сколько клиентов добавили в этом месяце?»

**Шаг 1.** Человек (или система) подкладывает в контекст LLM вывод `py1cv8 context`:
```json
{
  "objects": [
    {"type_num": 57, "tech_name": "Справочник.Клиенты"},
    ...
  ],
  "type_map": {"57": "Catalogs"},
  "dbnames_rules": "Catalogs → _Reference{N}",
  "relationship_rules": "…"
}
```

**Шаг 2.** LLM читает и рассуждает:
- type_num 57 = Catalogs = справочник
- имя "Справочник.Клиенты" → таблица `_Reference{N}`
- через SQL узнаю что N: `SELECT table_name FROM information_schema.tables WHERE table_name LIKE '_Reference%'`

**Шаг 3.** LLM даёт SQL или человек выполняет через `sql`:
```sql
SELECT _IDRRef, _Description, _Code
FROM _Reference53
WHERE _Date > '2026-06-01'
```

---

## Для кого

- **Разработчикам 1С** — быстро понять структуру базы без запуска платформы
- **Аналитикам** — достать данные SQL напрямую, зная правила именования
- **LLM-инженерам** — дать нейросети контекст для генерации корректных запросов к 1С

---

## Тестирование

```bash
uv run pytest tests/ -v
```

---

## Лицензия

MIT
