"""Парсинг DBNames и генерация имён таблиц БД.

Единственная ответственность (SRP):
  - Разбор текстового содержимого системной таблицы ``_DBNames__``
    в структурированные записи ``DBNamesEntry``.
  - Генерация физических имён таблиц БД (``_ReferenceNN``,
    ``_DocumentNN``, ``_InfoRgNN`` и т.д.) на основе записей DBNames.
  - Классификация записей: основная таблица (``main``),
    подчинённая (``sub``), сопутствующая (``companion``), служебная (``service``).

Не занимается:
  - Подключением к БД или выполнением SQL-запросов.
  - Парсингом бинарных блобов config/configcas.
  - Поиском UUID по таблицам.

Контракты:
  - Удовлетворяет ``contracts.dbnames.DBNamesProvider``.

Пример использования:
    >>> text = '{550e8400-e29b-41d4-a716-446655440000,"Reference",53}'
    >>> entries = parse_dbnames_text(text)
    >>> entries[0].uuid
    '550e8400-e29b-41d4-a716-446655440000'
    >>> generate_db_name(entries[0])
    '_reference53'
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── DBNames type → category (from schema discovery) ────────────────────────

# ── Sub-table types and their parent type names ────────────────────────────

SUB_TABLE_TYPES: frozenset[str] = frozenset(
    {
        "Fld",
        "VT",
        "LineNo",
        "ByDims",
        "BPr",
        "BPrPoints",
        "Node",
    }
)

SUB_TABLE_PARENT: dict[str, str] = {
    "Fld": "Reference",
    "VT": "Reference",
    "LineNo": "Reference",
    "ByDims": "Reference",
    "BPr": "BusinessProcess",
    "BPrPoints": "BusinessProcess",
    "Node": "ExchangePlan",
}

# ── Subordinate-main companion table mapping ───────────────────────────────
# These accompany a main table (same UUID) but are standalone tables
# with their own schema, not true sub-tables.

COMPANION_TABLE_TYPES: frozenset[str] = frozenset(
    {
        "ChrcSInf",
        "IntegServiceSettings",
        "IntegServiceMsgBody",
        "IntegServiceExtMsgBody",
        "EcsBotInQueue",
    }
)

COMPANION_TABLE_PARENT: dict[str, str] = {
    "ChrcSInf": "Chrc",
    "IntegServiceSettings": "IntegrationService",
    "IntegServiceMsgBody": "IntegrationService",
    "IntegServiceExtMsgBody": "IntegrationService",
    "EcsBotInQueue": "Bots",
}

# ── Table naming conventions ───────────────────────────────────────────────

MAIN_TABLE_TYPES: frozenset[str] = frozenset(
    {
        "Reference",
        "Document",
        "InfoRg",
        "Chrc",
        "Const",
        "Enum",
        "ScheduledJobs",
        "ChrcSInf",
        "AccRg",
        "AccRgT",
        "CalcRg",
        "CalcRgT",
        "BusinessProcess",
        "ExchangePlan",
        "Sequence",
        "DocumentJournal",
        "Task",
        "CommonAttribute",
        "SessionParameter",
        "SettingsStorage",
    }
)

SERVICE_TABLE_TYPES: frozenset[str] = frozenset(
    {
        "STTSettings",
        "STTGrammar",
        "STTGrammarChecksum",
        "STTModels",
        "STTModelsDesc",
        "Descr",
        "Acoustic",
        "LangModel",
        "DbSegments",
        "DbSegmentsItems",
        "ExtensionsRestruct",
        "ExtensionsRestructNGS",
        "ExtensionsInfo",
        "ExtensionsInfoNGS",
        "SystemSettings",
        "CommonSettings",
        "RepSettings",
        "RepVarSettings",
        "FrmDtSettings",
        "DynListSettings",
        "ErrorProcessingSettings",
        "URLExternalData",
        "InternalSettings",
        "DefaultSystemSettings",
        "DefaultInternalSettings",
        "DbCopiesInfoBaseUse",
        "DbCopiesUpdateTableStat",
        "DbCopiesUpdateStat",
        "DbCopies",
        "DbCopiesSettings",
        "DbCopiesTrLogs",
        "DbCopiesTrTables",
        "DbCopiesUpdates",
        "DbCopiesTablesStates",
        "DbCopiesInitialLast",
        "DbCopiesTrChanges",
        "DbCopiesTrChObj",
        "MobileClientDataExchange",
        "Bots",
        "ODataSettings",
        "DataHistoryQueue0",
        "DataHistoryVersions",
        "DataHistoryLatestVersions",
        "DataHistoryMetadata",
        "DataHistorySettings",
        "DataHistoryAfterWriteQueue",
        "DataHistoryLatestVerExt",
        "DataHistoryMetadataExt",
        "DataHistorySettingsExt",
        "DataHistoryVersionsExt",
        "RefOpt",
        "ChrcOpt",
        "AccOpt",
        "CKindsOpt",
        "UsersWorkHistory",
        "UsersDmm",
        "FilesStruDmm",
        "IBVersionStruDmm",
        "YearOffset",
        "Consts",
        "ExtDataSrcPrms",
        "WebSocketClients",
    }
)


@dataclass
class DBNamesEntry:
    """Одна запись из DBNames — связка UUID → тип → номер таблицы.

    Каждая строка системной таблицы ``_DBNames__`` после парсинга
    превращается в такой объект. Хранит тройку ``(uuid, type_name, number)``,
    по которой можно сгенерировать физическое имя таблицы и определить
    категорию.

    Attributes:
        uuid: Уникальный идентификатор объекта метаданных 1С в формате
              ``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``.
        type_name: Тип DBNames — строка вроде ``"Reference"``,
              ``"Document"``, ``"InfoRg"``, ``"Fld"`` и т.д.
        number: Внутренний номер таблицы (присваивается конфигуратором
              1С, не связан с ``type_num``). Используется как суффикс
              в имени физической таблицы.

    Example:
        >>> entry = DBNamesEntry(
        ...     uuid="550e8400-e29b-41d4-a716-446655440000",
        ...     type_name="Reference",
        ...     number=53,
        ... )
        >>> entry.category
        'main'
        >>> generate_db_name(entry)
        '_reference53'
    """

    uuid: str
    type_name: str
    number: int

    @property
    def category(self) -> str:
        """Классифицировать запись по типу таблицы.

        Определяет, к какой категории относится таблица:

        * ``"main"`` — основная таблица (``Reference``, ``Document``,
          ``InfoRg``, ``Chrc`` и др. из ``MAIN_TABLE_TYPES``).
        * ``"sub"`` — подчинённая таблица (``Fld``, ``VT``,
          ``LineNo``, ``ByDims``, ``BPr``, ``BPrPoints``, ``Node``).
        * ``"companion"`` — сопутствующая таблица (``ChrcSInf``,
          ``IntegServiceSettings`` и др. из ``COMPANION_TABLE_TYPES``).
        * ``"service"`` — служебная таблица (``STTSettings``,
          ``Bots``, ``Consts`` и др. из ``SERVICE_TABLE_TYPES``),
          а также запись с нулевым UUID.

        Returns:
            Одна из строк: ``"main"``, ``"sub"``, ``"companion"``,
            ``"service"``.

        Example:
            >>> DBNamesEntry("uuid", "Reference", 1).category
            'main'
            >>> DBNamesEntry("uuid", "Fld", 1).category
            'sub'
            >>> DBNamesEntry("uuid", "Bots", 1).category
            'service'
            >>> DBNamesEntry("00000000-0000-0000-0000-000000000000", "X", 0).category
            'service'
        """
        if self.type_name in SUB_TABLE_TYPES:
            return "sub"
        if self.type_name in COMPANION_TABLE_TYPES:
            return "companion"
        if (
            self.type_name in SERVICE_TABLE_TYPES
            or self.uuid == "00000000-0000-0000-0000-000000000000"
        ):
            return "service"
        return "main"


def parse_dbnames_text(text: str) -> list[DBNamesEntry]:
    """Разобрать декомпрессированный текст DBNames в список записей.

    Принимает текстовое содержимое системной таблицы ``_DBNames__``
    (после декомпрессии zlib) и извлекает все записи вида
    ``{uuid,"type_name",number}`` с помощью регулярного выражения.

    Формат одной записи в тексте::

        {550e8400-e29b-41d4-a716-446655440000,"Reference",53}

    Args:
        text: Сырой текст из ``_DBNames__`` после декомпрессии.
              Может быть пустой строкой или содержать мусор вне
              фигурных скобок — всё, кроме паттерна ``{...}``,
              игнорируется.

    Returns:
        Список ``DBNamesEntry`` в порядке обнаружения в тексте.
        Если ни одной записи не найдено — пустой список.

    Example:
        >>> text = '{uuid1,"Reference",53}{uuid2,"Document",12}'
        >>> entries = parse_dbnames_text(text)
        >>> len(entries)
        2
        >>> entries[0].type_name
        'Reference'
        >>> parse_dbnames_text("  ")  # пустой текст
        []
    """
    entries: list[DBNamesEntry] = []
    for m in re.finditer(
        r"\{([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}),"
        r'"([^"]+)",(\d+)\}',
        text,
    ):
        entries.append(
            DBNamesEntry(
                uuid=m.group(1).lower(),
                type_name=m.group(2),
                number=int(m.group(3)),
            )
        )
    return entries


def generate_db_name(entry: DBNamesEntry, parent_db_name: str | None = None) -> str | None:
    """Сгенерировать ожидаемое имя таблицы БД по записи DBNames.

    На основе ``type_name`` и ``number`` из DBNamesEntry формирует
    физическое имя таблицы в формате 1С. Правила генерации:

    * **Основные (main)**: ``_<type_name><number>``, напр. ``_Reference53``.
    * **Подчинённые (sub)**: ``<parent>_<subtype><number>``.
      Требуется ``parent_db_name``, иначе ``None``.
    * **Сопутствующие (companion)**: ``_<type_name><number>``.
    * **Служебные (service)**: ``_<type_name>`` (без номера).
    * **Неизвестный тип**: ``None``.

    Args:
        entry: Запись DBNames, содержащая ``type_name`` и ``number``.
        parent_db_name: Имя родительской таблицы (только для подчинённых
             типов). Для основных/сопутствующих/служебных игнорируется.

    Returns:
        Имя таблицы в нижнем регистре (например ``"_reference53"``)
        или ``None``, если ``type_name`` не распознан или для
        подчинённой таблицы не указан ``parent_db_name``.

    Example:
        >>> e1 = DBNamesEntry("u", "Reference", 53)
        >>> generate_db_name(e1)
        '_reference53'
        >>> e2 = DBNamesEntry("u", "Fld", 7)
        >>> generate_db_name(e2, "_reference53")
        '_reference53_fld7'
        >>> generate_db_name(e2)  # нет parent_db_name
        >>> e3 = DBNamesEntry("u", "UnknownType", 1)
        >>> generate_db_name(e3)
    """
    tname = entry.type_name
    num = entry.number

    if tname in MAIN_TABLE_TYPES:
        return f"_{tname.lower()}{num}"

    if tname in SUB_TABLE_TYPES:
        if parent_db_name:
            return f"{parent_db_name}_{tname.lower()}{num}"
        return None

    if tname in COMPANION_TABLE_TYPES:
        return f"_{tname.lower()}{num}"

    if tname in SERVICE_TABLE_TYPES:
        return f"_{tname.lower()}"

    return None


def get_parent_type(tname: str, category: str) -> str | None:
    """Определить родительский DBNames-тип для подчинённых/сопутствующих таблиц.

    Для подчинённых (``sub``) и сопутствующих (``companion``) таблиц
    возвращает имя родительского DBNames-типа. Например,
    ``"Fld"`` → ``"Reference"``, ``"ChrcSInf"`` → ``"Chrc"``.

    Args:
        tname: Имя DBNames-типа (``"Fld"``, ``"VT"``, ``"ChrcSInf"`` и т.д.).
        category: Категория записи (``"sub"`` или ``"companion"``).
             Параметр не используется в текущей реализации — поиск
             ведётся только по ``tname``. Оставлен для обратной
             совместимости.

    Returns:
        Имя родительского типа (например ``"Reference"``) или ``None``,
        если тип не найден в словарях ``SUB_TABLE_PARENT`` или
        ``COMPANION_TABLE_PARENT``.

    Example:
        >>> get_parent_type("Fld", "sub")
        'Reference'
        >>> get_parent_type("ChrcSInf", "companion")
        'Chrc'
        >>> get_parent_type("UnknownType", "sub")
    """
    if tname in SUB_TABLE_PARENT:
        return SUB_TABLE_PARENT[tname]
    if tname in COMPANION_TABLE_PARENT:
        return COMPANION_TABLE_PARENT[tname]
    return None


# ── Class implementation (satisfies DBNamesProvider contract) ─────────────


class DBNamesProviderImpl:
    """Реализация провайдера DBNames — парсинг ``_DBNames__`` и генерация имён таблиц.

    Удовлетворяет контракт ``contracts.dbnames.DBNamesProvider``.
    Предоставляет статические методы-обёртки над модульными функциями
    ``parse_dbnames_text`` и ``generate_db_name``, возвращая результат
    в виде списка словарей для удобной сериализации.

    Единственная ответственность:
      - Адаптация модульных функций (``dbnames.parse_dbnames_text``,
        ``dbnames.generate_db_name``) под интерфейс провайдера.

    Пример использования:
        >>> provider = DBNamesProviderImpl()
        >>> entries = provider.parse_dbnames_text('{"uuid","Reference",53}')
        >>> entries[0]["db_name"]
        '_reference53'
    """

    @staticmethod
    def parse_dbnames_text(text: str) -> list[dict]:
        """Разобрать сырой ``_DBNames__`` в список словарей с обогащёнными полями.

        Аналог модульной функции ``dbnames.parse_dbnames_text``, но
        возвращает не список ``DBNamesEntry``, а список словарей с
        дополнительными вычисленными полями:

        * ``uuid`` — UUID объекта метаданных.
        * ``type_name`` — DBNames-тип (``"Reference"``, ``"Document"`` и т.д.).
        * ``number`` — номер таблицы.
        * ``category`` — категория (``"main"``/``"sub"``/``"companion"``/``"service"``).
        * ``db_name`` — сгенерированное имя таблицы (или пустая строка).

        Args:
            text: Текстовое содержимое ``_DBNames__`` после декомпрессии.

        Returns:
            Список словарей. Каждый словарь содержит ключи
            ``uuid``, ``type_name``, ``number``, ``category``, ``db_name``.
            Если имя таблицы не удалось сгенерировать, ``db_name`` будет
            пустой строкой.

        Example:
            >>> provider = DBNamesProviderImpl()
            >>> result = provider.parse_dbnames_text('{uuid,"Reference",53}')
            >>> result[0]["db_name"]
            '_reference53'
        """
        entries = parse_dbnames_text(text)
        return [
            {
                "uuid": e.uuid,
                "type_name": e.type_name,
                "number": e.number,
                "category": e.category,
                "db_name": generate_db_name(e) or "",
            }
            for e in entries
        ]

    @staticmethod
    def generate_db_name(
        entry: dict,
        parent_db_name: str | None = None,
    ) -> str | None:
        """Сгенерировать имя таблицы БД из словарного представления DBNamesEntry.

        Обёртка над модульной функцией ``dbnames.generate_db_name``:
        принимает словарь (как из ``parse_dbnames_text``) и делегирует
        вызов датаклассу ``DBNamesEntry``.

        Args:
            entry: Словарь с ключами ``uuid``, ``type_name``, ``number``.
            parent_db_name: Имя родительской таблицы (для подчинённых
                 типов). По умолчанию ``None``.

        Returns:
            Имя таблицы (например ``"_reference53"``) или ``None``,
            если тип не распознан или отсутствует ``parent_db_name``
            для подчинённой таблицы.

        Example:
            >>> provider = DBNamesProviderImpl()
            >>> provider.generate_db_name(
            ...     {"uuid": "u", "type_name": "Reference", "number": 53}
            ... )
            '_reference53'
        """
        tname = entry.get("type_name", "")
        num = entry.get("number", 0)
        return generate_db_name(
            DBNamesEntry(
                uuid=entry.get("uuid", ""),
                type_name=tname,
                number=num,
            ),
            parent_db_name,
        )
