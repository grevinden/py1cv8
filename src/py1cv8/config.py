"""Central configuration — credentials, paths, type maps.

DB credentials are defaults only — override via Typer CLI ``--db-*`` options
(which support ``PY1CV8_*`` env vars natively).  Never hardcode production
secrets here.
"""

from __future__ import annotations

from pathlib import Path

# ── DB credentials (defaults — override via CLI/env) ────────────────────────

DB_HOST: str = "localhost"
DB_PORT: int = 5433
DB_USER: str = "postgres"
DB_PASS: str = "qwaseD12"

HERE: Path = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR: Path = HERE / ".staff" / ".export_from_1c"

# ── Type map: type_num → category (from 1C binary config blobs) ────────────
#
# WARNING: type_num (0-99) is NOT globally consistent across 1C configurations.
# The 1C platform assigns type_num per serialization format, which can vary
# between databases. This mapping is valid for the MessageCenter DB.
# For the test DB, see TYPE_NUM_REFERENCE in v8unpack_types.py.
#
# These are BROAD categories for BSL extraction output folders, NOT 1C type IDs.

TYPE_MAP: dict[int, str] = {
    0: "CommonForms",
    1: "DataProcessors",
    2: "CommonModules",
    3: "Subsystems",
    4: "DataProcessors",
    5: "CommonAttributes",
    6: "Roles",
    7: "Roles",
    8: "Ext",
    9: "Reports",
    12: "CommonTemplates",
    13: "OtherTypes",
    14: "OtherTypes",
    16: "Constants",
    17: "DataProcessors",
    19: "DataProcessors",
    20: "Enums",
    22: "Documents",
    26: "DocumentJournals",
    30: "OtherTypes",
    33: "InformationRegisters",
    34: "ChartsOfCharacteristicTypes",
    37: "OtherTypes",
    40: "Documents",
    57: "Catalogs",
    68: "Ext",
}

# ── DBNames type → category (from schema discovery) ────────────────────────

DBNAMES_CATEGORY_MAP: dict[str, str] = {
    "Reference": "Catalogs",
    "Document": "Documents",
    "InfoRg": "InformationRegisters",
    "Chrc": "ChartsOfCharacteristicTypes",
    "ChrcSInf": "ChartsOfCharacteristicTypes",
    "Const": "Constants",
    "Enum": "Enums",
    "ScheduledJobs": "ScheduledJobs",
    "Bots": "Bots",
    "DocumentJournal": "DocumentJournals",
    "Task": "Tasks",
    "AccRg": "AccumulationRegisters",
    "AccRgT": "AccumulationRegisters",
    "CalcRg": "AccountingRegisters",
    "CalcRgT": "AccountingRegisters",
    "BusinessProcess": "BusinessProcesses",
    "ExchangePlan": "ExchangePlans",
    "Sequence": "Sequences",
    "CommonAttribute": "CommonAttributes",
    "SessionParameter": "SessionParameters",
    "SettingsStorage": "SettingsStorages",
}

# ── Sub-table types and their parent type names ────────────────────────────

SUB_TABLE_TYPES: frozenset[str] = frozenset({
    "Fld", "VT", "LineNo", "ByDims",
    "BPr", "BPrPoints", "Node",
})

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

COMPANION_TABLE_TYPES: frozenset[str] = frozenset({
    "ChrcSInf",
    "IntegServiceSettings",
    "IntegServiceMsgBody",
    "IntegServiceExtMsgBody",
    "EcsBotInQueue",
})

COMPANION_TABLE_PARENT: dict[str, str] = {
    "ChrcSInf": "Chrc",
    "IntegServiceSettings": "IntegrationService",
    "IntegServiceMsgBody": "IntegrationService",
    "IntegServiceExtMsgBody": "IntegrationService",
    "EcsBotInQueue": "Bots",
}

# ── Table naming conventions ───────────────────────────────────────────────

MAIN_TABLE_TYPES: frozenset[str] = frozenset({
    "Reference", "Document", "InfoRg", "Chrc",
    "Const", "Enum", "ScheduledJobs", "ChrcSInf",
    "AccRg", "AccRgT", "CalcRg", "CalcRgT",
    "BusinessProcess", "ExchangePlan", "Sequence",
    "DocumentJournal", "Task",
    "CommonAttribute", "SessionParameter", "SettingsStorage",
})

SERVICE_TABLE_TYPES: frozenset[str] = frozenset({
    "STTSettings", "STTGrammar", "STTGrammarChecksum",
    "STTModels", "STTModelsDesc", "Descr", "Acoustic", "LangModel",
    "DbSegments", "DbSegmentsItems",
    "ExtensionsRestruct", "ExtensionsRestructNGS",
    "ExtensionsInfo", "ExtensionsInfoNGS",
    "SystemSettings", "CommonSettings",
    "RepSettings", "RepVarSettings", "FrmDtSettings",
    "DynListSettings", "ErrorProcessingSettings",
    "URLExternalData", "InternalSettings",
    "DefaultSystemSettings", "DefaultInternalSettings",
    "DbCopiesInfoBaseUse", "DbCopiesUpdateTableStat",
    "DbCopiesUpdateStat", "DbCopies", "DbCopiesSettings",
    "DbCopiesTrLogs", "DbCopiesTrTables", "DbCopiesUpdates",
    "DbCopiesTablesStates", "DbCopiesInitialLast",
    "DbCopiesTrChanges", "DbCopiesTrChObj",
    "MobileClientDataExchange", "Bots", "ODataSettings",
    "DataHistoryQueue0", "DataHistoryVersions",
    "DataHistoryLatestVersions", "DataHistoryMetadata",
    "DataHistorySettings", "DataHistoryAfterWriteQueue",
    "DataHistoryLatestVerExt", "DataHistoryMetadataExt",
    "DataHistorySettingsExt", "DataHistoryVersionsExt",
    "RefOpt", "ChrcOpt", "AccOpt", "CKindsOpt",
    "UsersWorkHistory", "UsersDmm",
    "FilesStruDmm", "IBVersionStruDmm", "YearOffset",
    "Consts", "ExtDataSrcPrms", "WebSocketClients",
})

AVAILABLE_DBS: list[str] = ["MessageCenter", "test"]

# ── 1C value type discriminator bytes (_Fld{N}_Type) ────────────────────
# These are the standard 1C value type codes used in _Type columns.
# When a typed field can hold multiple value types, _Type byte selects
# which type the actual value is.
# See: 1C:Enterprise Developer Guide, "ValueType" concept

TYPE_DISCRIMINATOR_MAP: dict[int, str] = {
    0x00: "Undefined",
    0x01: "String",
    0x02: "Number",
    0x03: "Date",
    0x04: "Boolean",
    0x05: "BinaryData",
    0x06: "ValueStorage",
    0x07: "UUID",
    0x08: "Reference (Catalog/Document/etc.)",
    0x09: "Object (any)",
    0x0A: "UniqueIdentifier",
    0x0B: "FixedArray",
    0x0C: "FixedStructure",
    0x0D: "FixedMap",
    0x0E: "Array",
    0x0F: "Structure",
    0x10: "Map",
    0x11: "List",
    0x12: "ValueTable",
    0x13: "ValueTree",
    0x14: "ValueTableRow",
    0x15: "TabularDocument",
    0x16: "SpreadsheetDocument",
    0x17: "GraphicScheme",
    0x18: "GeographicalScheme",
    0x19: "Chart",
    0x1A: "HTTPConnection",
    0x1B: "FTPConnection",
    0x1C: "MailProfile",
    0x1D: "Picture",
    0x1E: "BinData",
    0x1F: "TextDocument",
    0x20: "XDTOValueType",
}

# Type codes 0x08 refers to a "Reference" — the specific table is
# determined by the _RTRef companion column's table suffix.
