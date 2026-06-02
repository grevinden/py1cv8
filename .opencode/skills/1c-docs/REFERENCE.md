# 1C:Enterprise Physical Database Reference

## Источник: DaJet Metadata (zhichkin/dajet-metadata) + v8unpack
Этот документ описывает отображение объектов метаданных 1С на физические таблицы СУБД (PostgreSQL/MSSQL). Официальная документация 1С (its.1c.ru) НЕ публикует эти детали. Источник — реверс-инжиниринг платформы проектами DaJet Metadata и v8unpack.

---

## 1. Mapping: Metadata Types → Table Prefixes

### Reference types (ссылочные типы данных)

| 1C Metadata Type | MetadataNames (рус) | Table Prefix | type_num пример | Example table |
|---|---|---|---|---|
| Справочник | `Справочник` | `_Reference{code}` | 40 | `_Reference53`, `_Reference702` |
| Документ | `Документ` | `_Document{code}` | 22, 40 | `_Document209`, `_Document615` |
| План видов характеристик | `ПланВидовХарактеристик` | `_Chrc{code}` | 34 | `_Chrc34` |
| План счетов | `ПланСчетов` | `_Acc{code}` | — | `_Acc102` |
| План обмена | `ПланОбмена` | `_Node{code}` | — | `_Node1` |
| Перечисление | `Перечисление` | `_Enum{code}` | 20 | `_Enum20` |
| Бизнес-процесс | `БизнесПроцесс` | `_BPr{code}` | — | `_BPr5` |
| Задача | `Задача` | `_Task{code}` | — | `_Task8` |

### Value types (значимые типы данных)

| 1C Metadata Type | MetadataNames (рус) | Table Prefix | type_num пример | Example table |
|---|---|---|---|---|
| Константа | `Константа` | `_Const{code}` | 16 | `_Const3` |
| Регистр сведений | `РегистрСведений` | `_InfoRg{code}` | 33 | `_InfoRg119` |
| Регистр накопления | `РегистрНакопления` | `_AccumRg{code}` | — | `_AccumRg45` |
| Регистр бухгалтерии | `РегистрБухгалтерии` | `_AccRg{code}` | — | `_AccRg7` |

### Sub-tables (вспомогательные таблицы)

| Table Prefix | Belongs To | Description |
|---|---|---|
| `_InfoRgOpt{code}` | ИнфоRg | Настройки регистра сведений |
| `_InfoRgSF{code}` | ИнфоRg | Срез первых (Slice First) |
| `_InfoRgSL{code}` | ИнфоRg | Срез последних (Slice Last) |
| `_AccumRgT{code}` | AccumRg | Итоги (остатки) |
| `_AccumRgTn{code}` | AccumRg | Итоги (обороты) |
| `_AccumRgOpt{code}` | AccumRg | Настройки |
| `_AccRgOpt{code}` | AccRg | Настройки |
| `_AccRgED{code}` | AccRg | Журнал проводок |
| `_AccRgCT{code}` | AccRg | Обороты между счетами |
| `_AccRgAT0-5{code}` | AccRg | Обороты по субконто (0-5 уровней) |
| `_ExtDim{code}` | Acc | Виды субконто |
| `_BPrPoints{code}` | BPr | Точки маршрута бизнес-процесса |
| `_VT{code}` | Любой объект | Табличная часть (Tabular Section) |

### Change Tracking (регистрация изменений для планов обмена)

| Table Prefix | Object Type |
|---|---|
| `_ReferenceChngR{code}` | Справочник |
| `_DocumentChngR{code}` | Документ |
| `_InfoRgChngR{code}` | Регистр сведений |
| `_AccumRgChngR{code}` | Регистр накопления |
| `_AccRgChngR{code}` | Регистр бухгалтерии |
| `_ChrcChngR{code}` | План видов характеристик |
| `_ConstChngR{code}` | Константа |
| `_AccChngR{code}` | План счетов |
| `_BPrChngR{code}` | Бизнес-процесс |
| `_TaskChngR{code}` | Задача |

### Extension suffix
Объекты расширений конфигурации получают суффикс `x1`: `_Reference702x1`

---

## 2. System Field Naming

### Common system fields

| Field Name | Type | Purpose |
|---|---|---|
| `_IDRRef` | binary(16) | Primary key (UUID) — ссылка на объект |
| `_Version` | binary(8) | Версия данных (rowversion / integer) |
| `_Marked` | binary(1) | Пометка удаления (0/1, bool) |

### Reference/Document fields

| Field Name | Type | Object | Purpose |
|---|---|---|---|
| `_Code` | string/numeric | Catalog | Код справочника |
| `_Description` | string(150) | Catalog | Наименование (`_Description`) |
| `_ParentIDRRef` | binary(16) | Catalog | Родитель (иерархия) |
| `_Folder` | binary(1) | Catalog | ЭтоГруппа (inverted: 0x00=группа) |
| `_OwnerIDRRef` | binary(16) | Catalog | Владелец (если 1 тип) |
| `_OwnerID_TYPE` | binary(1) | Catalog | Тип владельца (составной тип) |
| `_OwnerID_RTRef` | binary(4) | Catalog | Код типа владельца (составной тип) |
| `_OwnerID_RRRef` | binary(16) | Catalog | UUID владельца (составной тип) |
| `_PredefinedID` | binary(16) | Catalog | Предопределённый (с 8.3.3) |
| `_IsMetadata` | binary(1) | Catalog | Предопределённый (до 8.3.3) |

### Document-specific fields

| Field Name | Type | Purpose |
|---|---|---|
| `_Date_Time` | datetime | Дата документа |
| `_NumberPrefix` | datetime | Период номера |
| `_Number` | string/numeric | Номер документа |
| `_Posted` | binary(1) | Проведён |

### Characteristic (ПВХ) fields

| Field Name | Type | Purpose |
|---|---|---|
| `_Type` | binary | Тип значения |

### Register fields

| Field Name | Type | Register | Purpose |
|---|---|---|---|
| `_Period` | datetime | InfoRg/AccumRg/AccRg | Период |
| `_RecorderRRef` | binary(16) | InfoRg/AccumRg/AccRg | Регистратор (1 тип) |
| `_RecorderTRef` | binary(4) | InfoRg | Тип регистратора (составной) |
| `_RecordKind` | numeric(1,0) | AccumRg | Вид движения (0=Приход, 1=Расход) |
| `_LineNo` | numeric(9,0) | InfoRg | Номер строки |
| `_Active` | binary(1) | InfoRg | Активность |
| `_SimpleKey` | binary(16) | InfoRg | SimpleKey (до 8.3.3, непериод, >1 изм) |

### Enumeration fields

| Field Name | Type | Purpose |
|---|---|---|
| `_EnumOrder` | numeric(10,0) | Порядок значения перечисления |

### Accounting Register fields

| Field Name | Type | Purpose |
|---|---|---|
| `_AccountDtRRef` | binary(16) | Счёт дебета |
| `_AccountCtRRef` | binary(16) | Счёт кредита |
| `_EDHashDt` | numeric(10,0) | Хеш проводки по дебету |
| `_EDHashCt` | numeric(10,0) | Хеш проводки по кредиту |

### Exchange Plan fields

| Field Name | Type | Purpose |
|---|---|---|
| `_NodeTRef` | binary(4) | Тип узла |
| `_NodeRRef` | binary(16) | UUID узла |
| `_MessageNo` | numeric | Номер сообщения |
| `_Splitter` | numeric(10,0) | Разделитель итогов |
| `_SentNo` | numeric | Номер отправленного |
| `_ReceivedNo` | numeric | Номер полученного |

---

## 3. Custom Field Naming (реквизиты, ресурсы, измерения)

Каждый пользовательский реквизит/ресурс/измерение получает номер (FieldNo) и префикс `_Fld{number}`.

### Simple type fields
`_Fld{number}` — например, `_Fld1234` (string, numeric, datetime, bool)

### Reference type fields (ссылочный тип)
- **Single reference type**: `_Fld{number}_RRef` — binary(16), UUID цели
- **Compound reference type** (составной тип данных):
  - `_Fld{number}_TYPE` — binary(1), тип данных
  - `_Fld{number}_RTRef` — binary(4), type code
  - `_Fld{number}_RRRef` — binary(16), UUID цели

### Type postfixes (для определения типа данных по колонке)
- `L` — Boolean
- `N` — Numeric
- `T` — DateTime
- `S` — String
- `R` / `#` — Reference type
- `B` — Boolean (в метаданных config)
- `D` — DateTime (в метаданных config)

---

## 4. Metadata Type UUIDs (GUIDs)

Эти UUID используются в файле `root` конфигурации для идентификации типа объекта:

| Type | UUID |
|---|---|
| Подсистемы (Subsystem) | `37f2fa9a-b276-11d4-9435-004095e12fc7` |
| Общие реквизиты (SharedProperty) | `15794563-ccec-41f6-a83c-ec5f7b9a5bc1` |
| Определяемые типы (DefinedType) | `c045099e-13b9-4fb6-9d50-fca00202971e` |
| Константы (Constant) | `0195e80c-b157-11d4-9435-004095e12fc7` |
| Справочники (Catalog) | `cf4abea6-37b2-11d4-940f-008048da11f9` |
| Документы (Document) | `061d872a-5787-460e-95ac-ed74ea3a3e84` |
| Перечисления (Enumeration) | `f6a80749-5ad7-400b-8519-39dc5dff2542` |
| Планы обмена (Publication) | `857c4a91-e5f4-4fac-86ec-787626f1c108` |
| Планы видов характеристик (Characteristic) | `82a1b659-b220-4d94-a9bd-14d757b95a48` |
| Регистры сведений (InformationRegister) | `13134201-f60b-11d5-a3c7-0050bae0a776` |
| Регистры накопления (AccumulationRegister) | `b64d9a40-1642-11d6-a3c7-0050bae0a776` |
| Планы счетов (Account) | `238e7e88-3c5f-48b2-8a3b-81ebbecb20ed` |
| Регистры бухгалтерии (AccountingRegister) | `2deed9b8-0056-4ffe-a473-c20a6c32a0bc` |
| Задачи (BusinessTask) | `3e63355c-1378-4953-be9b-1deb5fb6bec5` |
| Бизнес-процессы (BusinessProcess) | `fcd3404e-1523-48ce-9bc0-ecdb822684a1` |

---

## 5. Reference Type GUIDs (ссылочные типы)

Используются в поле `_TYPE` для определения типа ссылки:

| Type | UUID |
|---|---|
| ЛюбаяСсылка (AnyReference) | `280f5f0e-9c8a-49cc-bf6d-4d296cc17a63` |
| СправочникСсылка | `e61ef7b8-f3e1-4f4b-8ac7-676e90524997` |
| ДокументСсылка | `38bfd075-3e63-4aaa-a93e-94521380d579` |
| ПеречислениеСсылка | `474c3bf6-08b5-4ddc-a2ad-989cedf11583` |
| ПланОбменаСсылка | `0a52f9de-73ea-4507-81e8-66217bead73a` |
| ПланВидовХарактеристикСсылка | `99892482-ed55-4fb5-a7f7-20888820a758` |
| ПланСчетовСсылка | `ac606d60-0209-4159-8e4c-794bc091ce38` |
| ЗадачаСсылка | `6291e9b3-8df5-44e1-b6b2-d9fe008016c0` |
| БизнесПроцессСсылка | `214fa4d8-6ba4-4748-a5e1-6332b5887780` |

---

## 6. Special Types

| Type | UUID | Description |
|---|---|---|
| ХранилищеЗначения | `e199ca70-93cf-46ce-a54b-6edc88c3a296` | ValueStorage (varbinary(max)) |
| УникальныйИдентификатор | `fc01b5df-97fe-449b-83d4-218a090e681e` | UUID (binary(16)) |

---

## 7. System Config Tables (в БД)

| Table | Purpose |
|---|---|
| `_Config` | Хранилище метаданных конфигурации |
| `_ConfigCAS` | Хранилище метаданных расширений |
| `_ExtensionsInfo` | Информация о расширениях |
| `_DBSchema` | Схема БД |
| `Params` | Параметры (включая DBNames) |
| `_YearOffset` | Смещение дат |
| `1SUSERS` | Пользователи инфобазы (только MSSQL) |
| `_InfoRg, _AccumRg, _AccRg, _Const` | Таблицы регистров и констант со служебными суффиксами |
| `SchemaStorage` | Хранилище схем (для PostgreSQL) |

---

## 8. DBNames File Format

Файл `DBNames` в таблице `Params` содержит отображение UUID объекта метаданных → код + префикс таблицы.

Структура:
```
[UUID (binary(16))] [TokenName (string)] [NumericCode (int)]
```

Токены (из `MetadataToken.cs`): `Reference`, `Document`, `InfoRg`, `AccumRg`, `AccRg`, `Chrc`, `Enum`, `Const`, `Acc`, `Node`, `BPr`, `Task`, `VT`, `Fld`, `InfoRgSF`, `InfoRgSL`, `InfoRgOpt`, `AccumRgT`, `AccumRgTn`, `AccumRgOpt`, `AccRgED`, `AccRgOpt`, `AccRgCT`, `AccRgAT0`-`AccRgAT5`, `ExtDim`, `BPrPoints`, `ReferenceChngR`, `DocumentChngR`, `InfoRgChngR`, `AccumRgChngR`, `AccRgChngR`, `ChrcChngR`, `ConstChngR`, `AccChngR`, `BPrChngR`, `TaskChngR`.

---

## 9. Генерация имён таблиц

Формула: `_{prefix}{code}`

```
_Reference{code}     # Справочник
_Document{code}      # Документ  
_InfoRg{code}        # Регистр сведений
_AccumRg{code}       # Регистр накопления
_AccRg{code}         # Регистр бухгалтерии
_Enum{code}          # Перечисление
_Chrc{code}          # План видов характеристик
_Const{code}         # Константа
_Acc{code}           # План счетов
_Node{code}          # План обмена
_BPr{code}           # Бизнес-процесс
_Task{code}          # Задача
_VT{code}            # Табличная часть
```

---

## 10. type_num Mapping (из config/configcas blob)

type_num — числовой идентификатор типа объекта в бинарном блобе (MOXCEL-заголовок или паттерн `{1,\n{N`).

| type_num | Category |
|---|---|
| 0 | CommonForms |
| 1,4,17,19 | DataProcessors |
| 2 | CommonModules |
| 3 | Subsystems |
| 5,57 | OtherTypes |
| 6,7 | Roles |
| 8 | Ext (не в MessageCenter) |
| 9 | Reports (не в MessageCenter) |
| 12 | CommonTemplates |
| 16 | Constants |
| 20 | Enums |
| 22,40 | Documents |
| 33 | InformationRegisters |
| 34 | ChartsOfCharacteristicTypes |
| 68 | Configuration |
