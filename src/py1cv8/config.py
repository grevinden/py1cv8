"""Central configuration — credentials, paths, type maps."""

from __future__ import annotations

from pathlib import Path

# ── DB credentials (read-only) ─────────────────────────────────────────────

DB_HOST: str = "localhost"
DB_PORT: int = 5433
DB_USER: str = "postgres"
DB_PASS: str = "qwaseD12"

# ── Output paths ───────────────────────────────────────────────────────────

OUT_DIR: str = r"B:\py1cv8\modules_prod_clean"
CHECKPOINT_PATH: str = r"B:\py1cv8\.extraction_checkpoint.json"
EXPORT_DIR: Path = Path(r"B:\py1cv8\.export_from_1c")

# ── Type map: type_num → category (from 1C binary config blobs) ────────────

TYPE_MAP: dict[int, str] = {
    0: "CommonForms",
    1: "DataProcessors",
    2: "CommonModules",
    3: "Subsystems",
    4: "DataProcessors",
    5: "OtherTypes",
    6: "Roles",
    7: "Roles",
    8: "Ext",
    9: "Reports",
    12: "CommonTemplates",
    16: "Constants",
    17: "DataProcessors",
    19: "DataProcessors",
    20: "Enums",
    22: "Documents",
    33: "InformationRegisters",
    34: "ChartsOfCharacteristicTypes",
    40: "Documents",
    57: "OtherTypes",
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
}

# ── Table naming conventions ───────────────────────────────────────────────

MAIN_TABLE_TYPES: frozenset[str] = frozenset({
    "Reference", "Document", "InfoRg", "Chrc",
    "Const", "Enum", "ScheduledJobs", "ChrcSInf",
})

SUB_TABLE_TYPES: frozenset[str] = frozenset({"Fld", "VT", "LineNo", "ByDims"})

SERVICE_TABLE_TYPES: frozenset[str] = frozenset({
    "STTSettings", "STTGrammar", "STTGrammarChecksum",
    "STTModels", "STTModelsDesc", "Descr", "Acoustic", "LangModel",
    "DbSegments", "DbSegmentsItems", "WebSocketClients",
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
    "RefOpt", "ChrcOpt", "AccOpt", "CKindsOpt",
    "UsersWorkHistory", "UsersDmm",
    "FilesStruDmm", "IBVersionStruDmm", "YearOffset",
})

AVAILABLE_DBS: list[str] = ["MessageCenter", "test"]
