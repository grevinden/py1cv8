"""DBNames parsing and table name generation.

Responsibilities:
  - Parse DBNames blob text into DBNamesEntry records
  - Generate database table names from DBNames entries
  - Classify entries as main/sub/service/companion

Satisfies: contracts.dbnames.DBNamesProvider
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
    uuid: str
    type_name: str
    number: int

    @property
    def category(self) -> str:
        """Classify this entry as 'main', 'sub', 'companion', or 'service'."""
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
    """Parse decompressed DBNames text into entries."""
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
    """Generate the expected database table name from a DBNames entry."""
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
    """Resolve parent DBNames type_name for sub/companion tables."""
    if tname in SUB_TABLE_PARENT:
        return SUB_TABLE_PARENT[tname]
    if tname in COMPANION_TABLE_PARENT:
        return COMPANION_TABLE_PARENT[tname]
    return None


# ── Class implementation (satisfies DBNamesProvider contract) ─────────────


class DBNamesProviderImpl:
    """Parses _DBNames__ system table and generates SQL table names.

    Satisfies: contracts.dbnames.DBNamesProvider
    """

    @staticmethod
    def parse_dbnames_text(text: str) -> list[dict]:
        """Parse raw _DBNames__ table content into structured entries.

        Returns list of dicts with keys: uuid, type_name, number, category, db_name.
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
        """Generate SQL table name for a DBNames entry dict."""
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
