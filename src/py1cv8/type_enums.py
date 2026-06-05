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


# ── 1C metadata object type UUIDs (from v8unpack MetaDataTypes) ─────────

METADATA_TYPES: dict[str, str] = {
    "00867c40-06b1-11d6-a3c7-0050bae0a776": "FilterCriterionForm",
    "0195e80c-b157-11d4-9435-004095e12fc7": "Constant",
    "061d872a-5787-460e-95ac-ed74ea3a3e84": "Document",
    "07ee8426-87f1-11d5-b99c-0050bae0a95d": "CommonForm",
    "09736b02-9cac-4e3f-b4f7-d3e9576ab948": "Role",
    "0c89c792-16c3-11d5-b96b-0050bae0a95d": "CommonTemplate",
    "0df30176-6865-4787-9fc8-609eb144174f": "ChartOfAccountsCommand",
    "0fe48980-252d-11d6-a3c7-0050bae0a776": "CommonModule",
    "0fffc09c-8f4c-47cc-b41c-8d5c5a221d79": "HTTPService",
    "11bdaf85-d5ad-4d91-bb24-aa0eee139052": "ScheduledJob",
    "13134201-f60b-11d5-a3c7-0050bae0a776": "InformationRegister",
    "13134204-f60b-11d5-a3c7-0050bae0a776": "InformationRegisterForm",
    "15794563-ccec-41f6-a83c-ec5f7b9a5bc1": "CommonAttribute",
    "17816ebc-4068-496e-adc4-8879945a832f": "ExternalDataSourceTableForm",
    "1c57eabe-7349-44b3-b1de-ebfeab67b47d": "CommandGroup",
    "238e7e88-3c5f-48b2-8a3b-81ebbecb20ed": "ChartOfAccounts",
    "23fa3b84-220a-40e9-8331-e588bed87f7d": "FilterCriterionCommand",
    "24c43748-c938-45d0-8d14-01424a72b11e": "SessionParameter",
    "274bf899-db0e-4df6-8ab5-67bf6371ec0b": "CalculationRegisterRecalculations",
    "2bb208ca-e441-4023-9ab9-32a7807a85d0": "ExternalDataSourceCube",
    "2bcef0d1-0981-11d6-b9b8-0050bae0a95d": "TabularSectionAttribute",
    "2deed9b8-0056-4ffe-a473-c20a6c32a0bc": "AccountingRegister",
    "2e90c75b-2f0c-4899-a7d4-5426eaefc96e": "ChartOfCalculationTypesCommand",
    "2f1a5187-fb0e-4b05-9489-dc5dd6412348": "CommonCommand",
    "30b100d6-b29f-47ac-aec7-cb8ca8a54767": "ChartOfCalculationTypes",
    "30d554db-541e-4f62-8970-a1c6dcfeb2bc": "FunctionalOptionsParameter",
    "33f2e54b-37ce-4a7a-a569-b648d7aa4634": "EnumForm",
    "3448e506-5add-4fce-a604-7305466b2d8e": "ExternalDataSourceCubeForm",
    "36a8e346-9aaa-4af9-bdbd-83be3c177977": "DocumentNumerators",
    "37f2fa9a-b276-11d4-9435-004095e12fc7": "Subsystem",
    "39bddf6a-0c3c-452b-921c-d99cfa1c2f1b": "Interface",
    "3daea016-69b7-4ed4-9453-127911372fe6": "Template",
    "3e5404af-6ef8-4c73-ad11-91bd2dfac4c8": "Style",
    "3e63355c-1378-4953-be9b-1deb5fb6bec5": "Task",
    "3e7bfcc0-067d-11d6-a3c7-0050bae0a776": "FilterCriterion",
    "3f58cbfb-4172-4e54-be49-561a579bb38b": "TaskForm",
    "3f7a8120-b71a-4265-98bf-4d9bc09b7719": "BusinessProcessForm",
    "45556acb-826a-4f73-898a-6025fc9536e1": "DataProcessorCommand",
    "4612bd75-71b7-4a5c-8cc5-2b0b65f9fa0d": "DocumentJournal",
    "46b4cd97-fd13-4eaa-aba2-3bddd7699218": "SettingsStorage",
    "4e828da6-0f44-4b5b-b1c0-a2b3cfe7bdcc": "EventSubscription",
    "4ee40ec7-3469-439f-adb4-aa26ce2d3ec3": "ExternalDataSourceCubeCommand",
    "4fe87c89-9ad4-43f6-9fdb-9dc83b3879c6": "CatalogCommand",
    "5274d9fc-9c3a-4a71-8f5e-a0db8ab23de5": "ExternalDataSource",
    "5372e285-03db-4f8c-8565-fe56f1aea40e": "ChartOfAccountsForm",
    "58848766-36ea-4076-8800-e91eb49590d7": "StyleItem",
    "5bb6f09e-5d80-41f6-8070-9faa4d15b69b": "ExternalDataSourceTableCommand",
    "631b75a0-29e2-11d6-a3c7-0050bae0a776": "Report",
    "6d8d73a7-ba29-401d-9032-3872ec2d6433": "EnumCommand",
    "6e6dc072-b7ac-41e7-8f88-278d25b6da2a": "Bot",
    "7162da60-f7fe-4d78-ad5d-e31700f9af18": "AccountingRegisterCommand",
    "7a3e533c-f232-40d5-a932-6a311d2480bf": "BusinessProcessCommand",
    "7dcd43d9-aca5-4926-b549-1842e6a4e8cf": "CommonPicture",
    "82a1b659-b220-4d94-a9bd-14d757b95a48": "ChartOfCharacteristicType",
    "857c4a91-e5f4-4fac-86ec-787626f1c108": "ExchangePlan",
    "8657032e-7740-4e1d-a3ba-5dd6e8afb78f": "WebService",
    "87c509ab-3d38-4d67-b379-aca796298578": "ExchangePlanForm",
    "95b5e1d4-abfa-4a16-818d-a5b07b7d3f73": "ChartOfCharacteristicTypeCommand",
    "99f328af-a77f-4572-a2d8-80ed20c81890": "AccumulationRegisterCommand",
    "9cd510cd-abfc-11d4-9434-004095e12fc7": "Configuration",
    "9cd510ce-abfc-11d4-9434-004095e12fc7": "Language",
    "a2cb086c-db98-43e4-a1a9-0760ab048f8d": "CalculationRegisterForm",
    "a3b368c0-29e2-11d6-a3c7-0050bae0a776": "ReportForm",
    "a49a35ce-120a-4c80-8eea-b0618479cd70": "DocumentJournalCommand",
    "a7f8f92a-7a4b-484b-937e-42d242e64144": "ChartOfCalculationTypesForm",
    "acdf0f11-2d59-4e37-9945-c6721871a8fe": "CalculationRegisterCommand",
    "af547940-3268-434f-a3e7-e47d6d2638c3": "FunctionalOption",
    "b44ba719-945c-445c-8aab-1088fa4df16e": "InformationRegisterCommand",
    "b544fc6a-2ba3-4885-8fb2-cb289fb6d65e": "DocumentCommand",
    "b64d9a40-1642-11d6-a3c7-0050bae0a776": "AccumulationRegister",
    "b64d9a44-1642-11d6-a3c7-0050bae0a776": "AccumulationRegisterForm",
    "b8533c0c-2342-4db3-91a2-c2b08cbf6b23": "SettingsStorageForm",
    "bc587f20-35d9-11d6-a3c7-0050bae0a776": "Sequences",
    "bf3420b0-f6f9-41a0-b83a-fe9d4ab0b65d": "IntegrationService",
    "bf845118-327b-4682-b5c6-285d2a0eb296": "DataProcessor",
    "c045099e-13b9-4fb6-9d50-fca00202971e": "DefinedType",
    "c3831ec8-d8d5-4f93-8a22-f9bfae07327f": "ExternalDataProcessor",
    "cc9df798-7c94-4616-97d2-7aa0b7bc515e": "XDTOPackage",
    "cf4abea6-37b2-11d4-940f-008048da11f9": "Catalog",
    "d26096fb-7a5d-4df9-af63-47d04771fa9b": "WSReference",
    "d3b5d6eb-4ea2-4610-a3e2-624d4e815934": "AccountingRegisterForm",
    "d5207c64-11d5-4d46-bba2-55b7b07ff4eb": "ExchangePlanCommand",
    "d5b0e5ed-256d-401c-9c36-f630cafd8a62": "Form",
    "e3403acd-1c95-421b-87e4-4dfa29d38b52": "ExternalDataSourceTable",
    "e7ff38c0-ec3c-47a0-ae90-20c73ca72246": "ReportCommand",
    "eb2b78a8-40a6-4b7e-b1b3-6ca9966cbc94": "ChartOfCharacteristicTypeForm",
    "ec6bb5e5-b7a8-4d75-bec9-658107a699cf": "FormAttribute",
    "ec81ad10-ca07-11d5-b9a5-0050bae0a95d": "DocumentJournalForm",
    "f27c2152-a2c9-4c30-adb1-130f5eb2590f": "TaskCommand",
    "f2de87a8-64e5-45eb-a22d-b3aedab050e7": "CalculationRegister",
    "f6a80749-5ad7-400b-8519-39dc5dff2542": "Enum",
    "fb880e93-47d7-4127-9357-a20e69c17545": "DocumentForm",
    "fcd3404e-1523-48ce-9bc0-ecdb822684a1": "BusinessProcess",
    "fdf816d2-1ead-11d5-b975-0050bae0a95d": "CatalogForm",
}

# ── Reverse: name → UUID ────────────────────────────────────────────────

METADATA_TYPE_UUIDS: dict[str, str] = {v: k for k, v in METADATA_TYPES.items()}
