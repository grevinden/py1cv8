"""1C XSD type enums — embedded from platform XSD schemas.

Single responsibility: provide all 1C simpleType enumerations as Python
``StrEnum`` classes + a text description registry for LLM (Type Bridge).

All enum data is embedded (extracted from 1C 8.3.27 XSD files) —
zero external file dependencies.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Embedded enum data ─────────────────────────────────────────────────

_ENUM_DATA: dict[str, list[str]] = {
    # scheme[36] — xcf/enums (metadata config)
    "AccountMainPresentation": ["AsCode", "AsDescription"],
    "AccumulationRegisterType": ["Balance", "Turnovers"],
    "AttributeUse": ["ForItem", "ForFolder", "ForFolderAndItem"],
    "BusinessProcessNumberPeriodicity": ["Nonperiodical", "Year", "Quarter", "Month", "Day"],
    "BusinessProcessNumberType": ["Number", "String"],
    "CalculationRegisterPeriodicity": ["Year", "Quarter", "Month", "Day"],
    "CalculationTypeMainPresentation": ["AsCode", "AsDescription"],
    "CatalogCodeType": ["Number", "String"],
    "CatalogCodesSeries": ["WithinFolder", "WithinParentAndFolder", "WithinEntireDirectory"],
    "CatalogMainPresentation": ["AsDescription", "AsCode"],
    "CharOfAccountCodeSeries": ["WithinFolder", "WithinEntireChartOfAccounts"],
    "CharacteristicKindCodesSeries": ["WithinFolder", "WithinEntireChartOfCharacteristicTypes"],
    "CharacteristicTypeMainPresentation": ["AsDescription", "AsCode"],
    "ChartOfCalculationTypesBaseUse": ["Independent", "OnItem", "OnList"],
    "ChartOfCalculationTypesCodeType": ["Number", "String"],
    "ChoiceDataGetModeOnInputByString": ["Direct", "Background"],
    "ChoiceMode": ["Both", "FromListOnly", "EnterFieldOnly"],
    "CommonAttributeAuthenticationSeparation": ["DontUse", "Use"],
    "CommonAttributeAutoUse": ["DontUse", "Use"],
    "CommonAttributeConfigurationExtensionsSeparation": ["DontUse", "Use"],
    "CommonAttributeDataSeparation": ["DontUse", "Use"],
    "CommonAttributeSeparatedDataUse": ["DontUse", "Use"],
    "CommonAttributeUse": ["AllObjects", "SelectedObjects", "Auto"],
    "CommonAttributeUsersSeparation": ["DontUse", "Use"],
    "CompatibilityMode": [
        "Version8_1_0", "Version8_2_0", "Version8_3_0", "Version8_3_1",
        "Version8_3_2", "Version8_3_3", "Version8_3_4", "Version8_3_5",
        "Version8_3_6", "Version8_3_7", "Version8_3_8", "Version8_3_9",
        "Version8_3_10", "Version8_3_11", "Version8_3_12", "DontUse",
    ],
    "ConfigurationExtensionPurpose": ["Adaptation", "Addon", "Correction", "ExtensionOfExtension"],
    "CreateOnInput": ["Auto", "DontUse", "Use"],
    "DataExchangeMainPresentation": ["AsDescription", "AsCode"],
    "DataHistoryUse": ["DontUse", "Use"],
    "DefaultDataLockControlMode": ["Manual", "Automatic", "AutomatedAndManual"],
    "DocumentNumberPeriodicity": ["Nonperiodical", "Year", "Quarter", "Month", "Day"],
    "DocumentNumberType": ["Number", "String"],
    "EditType": ["Editable", "Noneditable", "EditableIfDetails"],
    "ExternalDataSourceTableDataType": ["Table", "Query"],
    "ExternalDataSourceTableType": ["Table", "View"],
    "FormType": ["OrdinaryForm", "ManagedForm"],
    "FormatVersion": [
        "Version8_0_0", "Version8_0_1", "Version8_0_2", "Version8_1_0",
        "Version8_1_1", "Version8_2_0", "Version8_3_0", "Version8_3_1",
        "Version8_3_2", "Version8_3_3", "Version8_3_4", "Version8_3_5",
        "Version8_3_6", "Version8_3_7", "Version8_3_8", "Blank",
    ],
    "FullTextSearchOnInputByString": ["DontUse", "Use"],
    "FullTextSearchUsing": ["DontUse", "Use"],
    "HTTPMethod": [
        "Get", "Post", "Put", "Delete", "Options", "Patch", "Head",
        "Connect", "Trace", "GetAndPost", "GetAndPut", "GetAndDelete",
        "PostAndPut", "PostAndDelete", "PutAndDelete", "All", "Lock",
    ],
    "HierarchyType": ["HierarchyFoldersAndItems", "HierarchyOfItems"],
    "Indexing": ["DontIndex", "Index", "IndexWithAdditionalOrder"],
    "InformationRegisterPeriodicity": [
        "Nonperiodical", "RecorderPosition", "Second", "Day", "Month", "Quarter", "Year",
    ],
    "IntegrationServiceChannelMessageDirection": ["Inbox", "Outbox"],
    "InterfaceCompatibilityMode": ["Version8_0", "Version8_1", "Version8_2", "Taxi"],
    "ModalityUseMode": ["DontUse", "UseAlarms", "UseAlarmsAndModalWindows"],
    "MoveBoundaryOnPosting": ["Move", "DontMove"],
    "ObjectAutonumerationMode": ["DontUse", "Use"],
    "ObjectBelonging": ["WithCapacity", "Shared", "WithOrganization"],
    "Posting": ["Post", "Write"],
    "PredefinedDataUpdate": ["DontUpdate", "AutoUpdate", "UpdateByVersion"],
    "PropertyState": [
        "Active", "Inactive", "ActiveWithLimitation", "Hidden", "ReadOnly",
    ],
    "RealTimePosting": ["DontUse", "Use"],
    "RegisterRecordsDeletion": ["DontDelete", "DeleteAutomatically", "DeleteByVersion"],
    "RegisterRecordsWritingOnPost": ["Write", "WriteAndCalculateTotals"],
    "RegisterWriteMode": ["Independent", "RecorderSubordinate"],
    "ReturnValuesReuse": [
        "DontUse", "WhileProcessingSameProcedureCall", "WhileCallingProcedureOrFunction",
    ],
    "ScriptVariant": ["English", "Russian"],
    "SearchStringModeOnInputByString": ["DontUse", "Use"],
    "SequenceFilling": ["DontUse", "Use"],
    "SessionReuseMode": ["DontUse", "UseAutomatically", "UseAlways"],
    "StyleElementType": ["ItemColor", "ItemFont", "ItemPicture"],
    "SubordinationUse": ["DontUse", "Use"],
    "SynchronousPlatformExtensionAndAddInCallUseMode": ["Use", "DontUse", "UseAlarms"],
    "TaskMainPresentation": ["AsDescription", "AsCode"],
    "TaskNumberAutoPrefix": ["DontUse", "Use"],
    "TaskNumberType": ["Number", "String"],
    "TemplateType": [
        "SpreadsheetDocument", "TextDocument", "ActiveDocument", "HTMLDocument",
        "GeographicalSchema", "GraphicalScheme", "TabularList", "Fragment",
        "BinaryData", "XSLTTransformation",
    ],
    "TransferDirection": ["Direct", "Reverse", "Mirror"],
    "TypeCategories": [
        "TabularSectionRow", "Object", "Ref", "Selection", "List", "Manager",
        "ValueManager", "RecordManager", "RecordSet", "RecordKey",
        "Characteristic", "ExtDimensions", "ExtDimensionTypesRow",
        "DisplacingCalculationTypes", "DisplacingCalculationTypesRow",
        "BaseCalculationTypes", "BaseCalculationTypesRow",
        "LeadingCalculationTypes", "LeadingCalculationTypesRow", "Recalcs",
        "RoutePointRef", "TablesManager", "Record", "TabularSection",
        "ExtDimensionTypes", "CubesManager", "DimensionTables", "DefinedType",
        "ValueKey",
    ],
    "UseQuickChoice": ["Auto", "Use", "DontUse"],
    "XCFFormat": ["Hierarchical", "Plain"],
    # scheme[18] — data/enterprise
    "AccountType": ["Active", "Passive", "ActivePassive"],
    "AccountingRecordType": ["Debit", "Credit"],
    "AccumulationRecordType": ["Receipt", "Expense"],
    "AccumulationRegisterAggregatePeriodicity": [
        "Nonperiodical", "Auto", "Day", "Month", "Quarter", "HalfYear", "Year",
    ],
    "AccumulationRegisterAggregateUse": ["Auto", "Always"],
    "AutoShowStateMode": ["Auto", "DontShow", "Show", "ShowOnComposition"],
    "AutoTimeMode": ["DontUse", "Last", "First", "CurrentOrLast", "CurrentOrFirst"],
    "ClientApplicationBaseFontVariant": ["Normal", "Large"],
    "ClientApplicationFormScaleVariant": ["Normal", "Large", "ExtraLarge"],
    "ClientApplicationInterfaceVariant": ["Standard", "Taxi"],
    "ClientApplicationType": [
        "ThickClient", "ThinClient", "WebClient", "MobileClient",
        "MobileStandaloneClient", "ExternalConnection",
    ],
    "ClientConnectionSpeed": ["Normal", "Low"],
    "ComparisonType": [
        "Equal", "NotEqual", "Less", "LessOrEqual", "Greater", "GreaterOrEqual",
        "In", "NotIn", "InHierarchy", "NotInHierarchy",
        "HasNull", "NotNull", "Like", "NotLike", "TRef", "TRefNull",
        "FillCheck", "NotFillCheck", "HasValue", "NotHasValue",
        "Similar", "NotSimilar",
    ],
    "DataChangeType": ["Create", "Update", "Delete"],
    "DataLineChangeType": ["Addition", "Update", "Deletion", "AddAndDelete"],
    "DatabaseCopiesUse": ["DontUse", "UseSeparate", "UseGeneral", "MainSlave"],
    "DocumentPostingMode": ["Regular", "RealTime"],
    "DocumentWriteMode": ["Write", "Posting", "UndoPosting"],
    "FoldersAndItemsUse": ["DontUse", "Use", "UseByItem"],
    "LinkedValueChangeMode": ["DontUse", "Use"],
    "MessageStatus": ["NoStatus", "Ready", "Delivered", "Error", "Deleted", "Read"],
    "PostingModeUse": ["Post", "Write", "DontWrite", "Both"],
    "ReportResultViewMode": ["InheritFromParent", "UnsplitRows", "SplitRows"],
    "RequiredDataRelevance": ["DontUse", "Use"],
    "ResultCompositionMode": ["None", "CompositionInReportBuilder", "Compose"],
    "TransactionsIsolationLevel": [
        "ReadUncommitted", "ReadCommitted", "RepeatableRead", "Serializable", "SNAPSHOT",
    ],
    "UpdateOnDataChange": ["DontUse", "Use"],
    "ViewModeApplicationOnSetReportResult": ["DontUse", "Use"],
    # scheme[3] — data/core
    "AllowedLength": ["Fixed", "Variable"],
    "AllowedSign": ["Any", "Nonnegative"],
    "DateFractions": ["Date", "Time", "DateTime"],
    "ErrorCategory": [
        "Data", "DataSize", "DataValue", "DataLock",
        "DataIntegrityViolation", "DataBase", "System", "Network",
        "FileSystem", "User", "Report", "Server", "Client",
        "ExternalConnection", "XML", "Stream", "Text", "ValueStorage",
        "Profile", "DateTime", "EventLog",
    ],
    "FileDragMode": ["Drag", "Selection"],
    "FillCheckErrorStatus": ["Warning", "Error"],
    "FillChecking": ["DontCheck", "Check"],
    "MainClientApplicationWindowMode": [
        "Normal", "Maximized", "FullScreen", "Workstation", "Keyboard",
    ],
    "StandardBeginningDateVariant": [
        "January_1", "April_1", "July_1", "October_1",
        "NearestSunday", "NearestMonday", "NearestTuesday",
        "NearestWednesday", "NearestThursday", "NearestFriday",
        "NearestSaturday", "January_1_2000", "April_1_2000", "July_1_2000", "October_1_2000",
        "CustomDate", "YearBeginning", "HalfYearBeginning", "QuarterBeginning",
        "MonthBeginning", "WeekBeginning", "DayBeginning",
    ],
    "StandardPeriodVariant": [  # 49 values — abbreviated
        "Day", "Week", "Month", "Quarter", "HalfYear", "Year", "Decade",
        "TwoWeeks", "ThreeMonths", "SixMonths", "NineMonths",
        "MonthFromBeginning", "QuarterFromBeginning", "HalfYearFromBeginning",
        "YearFromBeginning", "MonthToEnd", "QuarterToEnd", "HalfYearToEnd",
        "YearToEnd", "Today", "Tomorrow", "Yesterday", "ThisWeek",
        "ThisMonth", "ThisQuarter", "ThisHalfYear", "ThisYear", "NextWeek",
        "NextMonth", "NextQuarter", "NextHalfYear", "NextYear", "LastWeek",
        "LastMonth", "LastQuarter", "LastHalfYear", "LastYear",
        "Last30Days", "Last60Days", "Last90Days",
        "Next3Days", "Next7Days", "Next14Days", "Next30Days", "Next60Days", "Next90Days",
        "CurrentPeriod", "PreviousPeriod", "NextPeriod",
    ],
    # scheme[47] — data-composition-system/common
    "DataCompositionAccountingBalanceType": ["Debit", "Credit", "None"],
    "DataCompositionAreaTemplateType": [
        "Header", "Footer", "GroupHeader", "GroupFooter", "Detail", "Resource",
    ],
    "DataCompositionBalanceType": ["OpeningBalance", "ClosingBalance", "Turnovers"],
    "DataCompositionPeriodType": ["Month", "Quarter", "Year"],
}

# ── Lazy-loaded registry ───────────────────────────────────────────────

_ENUM_REGISTRY: dict[str, type[enum.StrEnum]] = {}


def _make_enum(name: str, values: Sequence[str]) -> type[enum.StrEnum]:
    members: dict[str, str] = {v: v for v in values}
    return enum.StrEnum(name, members)  # type: ignore[return-value]


def _load_all() -> None:
    if _ENUM_REGISTRY:
        return
    for name, values in _ENUM_DATA.items():
        _ENUM_REGISTRY[name] = _make_enum(name, values)


# ── Public API ─────────────────────────────────────────────────────────


def get_enum(name: str) -> type[enum.StrEnum] | None:
    _load_all()
    return _ENUM_REGISTRY.get(name)


def get_enum_values(name: str) -> list[str] | None:
    _load_all()
    return _ENUM_DATA.get(name)


def get_all_enum_names() -> list[str]:
    _load_all()
    return sorted(_ENUM_REGISTRY)


def describe_enum(name: str, indent: str = "") -> str:
    values = get_enum_values(name)
    if values is None:
        return f"{indent}{name}: (unknown)"
    return f"{indent}{name}: {', '.join(values)}"


def describe_all_enums(indent: str = "") -> str:
    _load_all()
    return "\n".join(describe_enum(name, indent) for name in sorted(_ENUM_REGISTRY))


def enum_summary() -> dict[str, int]:
    return {n: len(v) for n, v in _ENUM_DATA.items()}


# ── Well-known type aliases ────────────────────────────────────────────

TypeCategories: type[enum.StrEnum] | None = None
AccountType: type[enum.StrEnum] | None = None
AccumulationRecordType: type[enum.StrEnum] | None = None
AccumulationRegisterType: type[enum.StrEnum] | None = None
InformationRegisterPeriodicity: type[enum.StrEnum] | None = None
DocumentNumberPeriodicity: type[enum.StrEnum] | None = None
DocumentPostingMode: type[enum.StrEnum] | None = None
HierarchyType: type[enum.StrEnum] | None = None
CatalogCodeType: type[enum.StrEnum] | None = None
DateFractions: type[enum.StrEnum] | None = None
AllowedLength: type[enum.StrEnum] | None = None
AllowedSign: type[enum.StrEnum] | None = None
ComparisonType: type[enum.StrEnum] | None = None
DataChangeType: type[enum.StrEnum] | None = None
RegisterWriteMode: type[enum.StrEnum] | None = None
TemplateType: type[enum.StrEnum] | None = None

_WELL_KNOWN = [
    "TypeCategories", "AccountType", "AccumulationRecordType",
    "AccumulationRegisterType", "InformationRegisterPeriodicity",
    "DocumentNumberPeriodicity", "DocumentPostingMode", "HierarchyType",
    "CatalogCodeType", "DateFractions", "AllowedLength", "AllowedSign",
    "ComparisonType", "DataChangeType", "RegisterWriteMode", "TemplateType",
]


def _init_aliases() -> None:
    _load_all()
    g = globals()
    for name in _WELL_KNOWN:
        g[name] = _ENUM_REGISTRY.get(name)


_init_aliases()
