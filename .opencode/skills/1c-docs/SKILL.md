---
name: 1c-docs
description: |
  Use ONLY when the task involves 1C:Enterprise documentation — type_nums,
  metadata structure, binary format (config/configcas blobs), object types,
  DBNames naming, table layout, or internal 1C platform details.
  Trigger keywords: its.1c.ru, type_num, MOXCEL, DBNames, 1C binary, 1C metadata,
  configcas, v8unpack, 1C object types, Reference, Document, InfoRg, AccRg.
  Do NOT use for general SQL questions or MCP server development.
---

# 1C Documentation Reader

## Access

- **URL**: `https://its.1c.ru/`
- **Credentials**: `30550-40` / `63c7bfd9`
- **Auth**: form-based login (username + password), NOT HTTP Basic Auth

## How to authorize

1. Open browser and navigate to `https://its.1c.ru/`
2. Find login form — fill `30550-40` / `63c7bfd9`
3. Submit — after successful login, all documentation sections are accessible

## Key documentation sections on its.1c.ru

| Section | Content |
|---------|---------|
| **Руководство разработчика** | Object types, metadata structure, DB schema |
| **Техническая документация** | Binary format, config storage, DBNames |
| **Конфигурирование и администрирование** | Platform internals |
| **Руководство пользователя** | End-user features |

## What to search for

When investigating 1C internals, search for:

1. **Object types** — "Справочник", "Документ", "Регистр сведений", "План видов характеристик", "Константа", "Перечисление"
2. **Table naming** — "Имя таблицы", "DBNames", "_reference", "_document", "_inforg", "_accrg"
3. **Metadata storage** — "Хранение метаданных", "config", "configcas", "бинарный формат"
4. **Type system** — "Типы данных", "Ссылочные типы", "Реквизиты", "Табличные части"
5. **Binary format** — "MOXCEL", "заголовок блоба", "сериализация"

## RBAC note

Firefox/Playwright can handle the form auth. Use `npx @playwright/mcp` or your
browser tool to open a browser, fill credentials, submit, then navigate to
documentation pages.

## Using agent-browser (installed)

`agent-browser` (v0.27.0) is installed globally. Use it from bash:

```powershell
# Open login page
agent-browser open https://its.1c.ru/ --session-name 1c-docs

# Take accessibility snapshot to find login form elements
agent-browser snapshot -i

# Fill credentials (use refs from snapshot)
agent-browser fill @eN "30550-40"
agent-browser fill @eM "63c7bfd9"
agent-browser click @eK  # submit button

# Wait for login to complete, then navigate to docs
agent-browser wait --text "Поиск"
agent-browser snapshot

# Search for documentation
agent-browser fill @eS "Справочник DBNames"
agent-browser press Enter
agent-browser snapshot
```

Session state is auto-saved with `--session-name 1c-docs`, so subsequent runs
don't need to re-authenticate.

## Output format

Extract relevant documentation sections as markdown. Always include:
- Russian terminology (as written on its.1c.ru)
- English equivalent if available
- Direct URL to the source page

## Reference document

Смотри `REFERENCE.md` в этой же директории — содержит полную карту отображения
1С-объектов на физические таблицы (table prefixes, field names, field types,
type UUIDs, reference UUIDs, DBNames format). Этот документ основан на
реверс-инжиниринге DaJet Metadata (zhichkin/dajet-metadata) и v8unpack.
Официальная документация its.1c.ru НЕ содержит этих деталей.
