"""Reference enum of ALL 1C metadata types from v8unpack MetaDataTypes.

Provides:
- MetaDataType enum: all 1C types with their MDClasses UUIDs
- TYPE_GROUP: logical grouping of types
- TYPE_NUM_MAP: known type_num assignments (per-DB, not global!)

NOTE: type_num (0-99) is NOT globally consistent across configurations.
It is assigned by the 1C platform per-serialization-format and can vary
between databases. The TYPE_NUM_MAP is for reference only.
"""

from __future__ import annotations

from enum import StrEnum


class MetaDataType(StrEnum):
    """All 1C metadata types from MDClasses UUIDs (v8unpack source)."""

    AccountingRegister = "2deed9b8-0056-4ffe-a473-c20a6c32a0bc"
    AccountingRegisterCommand = "7162da60-f7fe-4d78-ad5d-e31700f9af18"
    AccountingRegisterForm = "d3b5d6eb-4ea2-4610-a3e2-624d4e815934"
    AccumulationRegister = "b64d9a40-1642-11d6-a3c7-0050bae0a776"
    AccumulationRegisterCommand = "99f328af-a77f-4572-a2d8-80ed20c81890"
    AccumulationRegisterForm = "b64d9a44-1642-11d6-a3c7-0050bae0a776"
    Bot = "6e6dc072-b7ac-41e7-8f88-278d25b6da2a"
    BusinessProcess = "fcd3404e-1523-48ce-9bc0-ecdb822684a1"
    BusinessProcessCommand = "7a3e533c-f232-40d5-a932-6a311d2480bf"
    BusinessProcessForm = "3f7a8120-b71a-4265-98bf-4d9bc09b7719"
    CalculationRegister = "f2de87a8-64e5-45eb-a22d-b3aedab050e7"
    CalculationRegisterCommand = "acdf0f11-2d59-4e37-9945-c6721871a8fe"
    CalculationRegisterForm = "a2cb086c-db98-43e4-a1a9-0760ab048f8d"
    CalculationRegisterRecalculations = "274bf899-db0e-4df6-8ab5-67bf6371ec0b"
    Catalog = "cf4abea6-37b2-11d4-940f-008048da11f9"
    CatalogCommand = "4fe87c89-9ad4-43f6-9fdb-9dc83b3879c6"
    CatalogForm = "fdf816d2-1ead-11d5-b975-0050bae0a95d"
    ChartOfAccounts = "238e7e88-3c5f-48b2-8a3b-81ebbecb20ed"
    ChartOfAccountsCommand = "0df30176-6865-4787-9fc8-609eb144174f"
    ChartOfAccountsForm = "5372e285-03db-4f8c-8565-fe56f1aea40e"
    ChartOfCalculationTypes = "30b100d6-b29f-47ac-aec7-cb8ca8a54767"
    ChartOfCalculationTypesCommand = "2e90c75b-2f0c-4899-a7d4-5426eaefc96e"
    ChartOfCalculationTypesForm = "a7f8f92a-7a4b-484b-937e-42d242e64144"
    ChartOfCharacteristicType = "82a1b659-b220-4d94-a9bd-14d757b95a48"
    ChartOfCharacteristicTypeCommand = "95b5e1d4-abfa-4a16-818d-a5b07b7d3f73"
    ChartOfCharacteristicTypeForm = "eb2b78a8-40a6-4b7e-b1b3-6ca9966cbc94"
    CommandGroup = "1c57eabe-7349-44b3-b1de-ebfeab67b47d"
    CommonAttribute = "15794563-ccec-41f6-a83c-ec5f7b9a5bc1"
    CommonCommand = "2f1a5187-fb0e-4b05-9489-dc5dd6412348"
    CommonForm = "07ee8426-87f1-11d5-b99c-0050bae0a95d"
    CommonModule = "0fe48980-252d-11d6-a3c7-0050bae0a776"
    CommonPicture = "7dcd43d9-aca5-4926-b549-1842e6a4e8cf"
    CommonTemplate = "0c89c792-16c3-11d5-b96b-0050bae0a95d"
    Configuration = "9cd510cd-abfc-11d4-9434-004095e12fc7"
    Constant = "0195e80c-b157-11d4-9435-004095e12fc7"
    DataProcessor = "bf845118-327b-4682-b5c6-285d2a0eb296"
    DataProcessorCommand = "45556acb-826a-4f73-898a-6025fc9536e1"
    DefinedType = "c045099e-13b9-4fb6-9d50-fca00202971e"
    Document = "061d872a-5787-460e-95ac-ed74ea3a3e84"
    DocumentCommand = "b544fc6a-2ba3-4885-8fb2-cb289fb6d65e"
    DocumentForm = "fb880e93-47d7-4127-9357-a20e69c17545"
    DocumentJournal = "4612bd75-71b7-4a5c-8cc5-2b0b65f9fa0d"
    DocumentJournalCommand = "a49a35ce-120a-4c80-8eea-b0618479cd70"
    DocumentJournalForm = "ec81ad10-ca07-11d5-b9a5-0050bae0a95d"
    DocumentNumerators = "36a8e346-9aaa-4af9-bdbd-83be3c177977"
    Enum = "f6a80749-5ad7-400b-8519-39dc5dff2542"
    EnumCommand = "6d8d73a7-ba29-401d-9032-3872ec2d6433"
    EnumForm = "33f2e54b-37ce-4a7a-a569-b648d7aa4634"
    EventSubscription = "4e828da6-0f44-4b5b-b1c0-a2b3cfe7bdcc"
    ExchangePlan = "857c4a91-e5f4-4fac-86ec-787626f1c108"
    ExchangePlanCommand = "d5207c64-11d5-4d46-bba2-55b7b07ff4eb"
    ExchangePlanForm = "87c509ab-3d38-4d67-b379-aca796298578"
    ExternalDataProcessor = "c3831ec8-d8d5-4f93-8a22-f9bfae07327f"
    ExternalDataSource = "5274d9fc-9c3a-4a71-8f5e-a0db8ab23de5"
    ExternalDataSourceCube = "2bb208ca-e441-4023-9ab9-32a7807a85d0"
    ExternalDataSourceCubeForm = "3448e506-5add-4fce-a604-7305466b2d8e"
    ExternalDataSourceCubeCommand = "4ee40ec7-3469-439f-adb4-aa26ce2d3ec3"
    ExternalDataSourceTable = "e3403acd-1c95-421b-87e4-4dfa29d38b52"
    ExternalDataSourceTableForm = "17816ebc-4068-496e-adc4-8879945a832f"
    ExternalDataSourceTableCommand = "5bb6f09e-5d80-41f6-8070-9faa4d15b69b"
    FilterCriterion = "3e7bfcc0-067d-11d6-a3c7-0050bae0a776"
    FilterCriterionCommand = "23fa3b84-220a-40e9-8331-e588bed87f7d"
    FilterCriterionForm = "00867c40-06b1-11d6-a3c7-0050bae0a776"
    Form = "d5b0e5ed-256d-401c-9c36-f630cafd8a62"
    FormAttribute = "ec6bb5e5-b7a8-4d75-bec9-658107a699cf"
    FunctionalOption = "af547940-3268-434f-a3e7-e47d6d2638c3"
    FunctionalOptionsParameter = "30d554db-541e-4f62-8970-a1c6dcfeb2bc"
    HTTPService = "0fffc09c-8f4c-47cc-b41c-8d5c5a221d79"
    InformationRegister = "13134201-f60b-11d5-a3c7-0050bae0a776"
    InformationRegisterCommand = "b44ba719-945c-445c-8aab-1088fa4df16e"
    InformationRegisterForm = "13134204-f60b-11d5-a3c7-0050bae0a776"
    IntegrationService = "bf3420b0-f6f9-41a0-b83a-fe9d4ab0b65d"
    Interface = "39bddf6a-0c3c-452b-921c-d99cfa1c2f1b"
    Language = "9cd510ce-abfc-11d4-9434-004095e12fc7"
    Report = "631b75a0-29e2-11d6-a3c7-0050bae0a776"
    ReportCommand = "e7ff38c0-ec3c-47a0-ae90-20c73ca72246"
    ReportForm = "a3b368c0-29e2-11d6-a3c7-0050bae0a776"
    Role = "09736b02-9cac-4e3f-b4f7-d3e9576ab948"
    ScheduledJob = "11bdaf85-d5ad-4d91-bb24-aa0eee139052"
    Sequences = "bc587f20-35d9-11d6-a3c7-0050bae0a776"
    SessionParameter = "24c43748-c938-45d0-8d14-01424a72b11e"
    SettingsStorage = "46b4cd97-fd13-4eaa-aba2-3bddd7699218"
    SettingsStorageForm = "b8533c0c-2342-4db3-91a2-c2b08cbf6b23"
    Style = "3e5404af-6ef8-4c73-ad11-91bd2dfac4c8"
    StyleItem = "58848766-36ea-4076-8800-e91eb49590d7"
    Subsystem = "37f2fa9a-b276-11d4-9435-004095e12fc7"
    TabularSectionAttribute = "2bcef0d1-0981-11d6-b9b8-0050bae0a95d"
    Task = "3e63355c-1378-4953-be9b-1deb5fb6bec5"
    TaskCommand = "f27c2152-a2c9-4c30-adb1-130f5eb2590f"
    TaskForm = "3f58cbfb-4172-4e54-be49-561a579bb38b"
    Template = "3daea016-69b7-4ed4-9453-127911372fe6"
    WebService = "8657032e-7740-4e1d-a3ba-5dd6e8afb78f"
    WSReference = "d26096fb-7a5d-4df9-af63-47d04771fa9b"
    XDTOPackage = "cc9df798-7c94-4616-97d2-7aa0b7bc515e"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    @property
    def is_top_level(self) -> bool:
        """Whether this type is a top-level configuration object (not sub-object)."""
        return not self.name.endswith(("Command", "Form", "Attribute"))


# ── Logical grouping ─────────────────────────────────────────────────────────

TYPE_GROUP: dict[str, list[str]] = {
    "Constants": ["Constant"],
    "Catalogs": ["Catalog"],
    "Documents": ["Document"],
    "DocumentJournals": ["DocumentJournal"],
    "Enums": ["Enum"],
    "InformationRegisters": ["InformationRegister"],
    "AccumulationRegisters": ["AccumulationRegister"],
    "AccountingRegisters": ["AccountingRegister", "ChartOfAccounts"],
    "CalculationRegisters": ["CalculationRegister", "ChartOfCalculationTypes"],
    "ChartsOfCharacteristicTypes": ["ChartOfCharacteristicType"],
    "BusinessProcesses": ["BusinessProcess"],
    "Tasks": ["Task"],
    "ExchangePlans": ["ExchangePlan"],
    "Sequences": ["Sequences"],
    "Reports": ["Report"],
    "DataProcessors": ["DataProcessor"],
    "CommonModules": ["CommonModule"],
    "CommonForms": ["CommonForm"],
    "CommonTemplates": ["CommonTemplate"],
    "CommonPictures": ["CommonPicture"],
    "CommonCommands": ["CommonCommand"],
    "CommonAttributes": ["CommonAttribute"],
    "Roles": ["Role"],
    "Subsystems": ["Subsystem"],
    "ScheduledJobs": ["ScheduledJob"],
    "Bots": ["Bot"],
    "CommandGroups": ["CommandGroup"],
    "DefinedTypes": ["DefinedType"],
    "DocumentNumerators": ["DocumentNumerator"],
    "EventSubscriptions": ["EventSubscription"],
    "FilterCriteria": ["FilterCriterion"],
    "FunctionalOptions": ["FunctionalOption"],
    "FunctionalOptionsParameters": ["FunctionalOptionsParameter"],
    "HTTPServices": ["HTTPService"],
    "IntegrationServices": ["IntegrationService"],
    "Interfaces": ["Interface"],
    "Languages": ["Language"],
    "SessionParameters": ["SessionParameter"],
    "SettingsStorages": ["SettingsStorage"],
    "Styles": ["Style", "StyleItem"],
    "WebServices": ["WebService"],
    "WSReferences": ["WSReference"],
    "XDTOPackages": ["XDTOPackage"],
    "ExternalDataProcessors": ["ExternalDataProcessor"],
    "ExternalDataSources": [
        "ExternalDataSource", "ExternalDataSourceCube", "ExternalDataSourceTable",
    ],
    "Ext": ["Configuration"],
}



# ── TYPE_NUM reference (per-DB, NOT globally consistent!) ────────────────────

# These are confirmed for the test DB based on blob auto-generated names.
# Different 1C configurations may assign different type_nums.
# type_num=13 is a sub-type (Form), not a top-level type.
TYPE_NUM_REFERENCE: dict[int, str] = {
    0: "DefinedType",            # test: tech="ОпределяемыйТип1"
    1: "Bot",                     # test: tech="Бот1"
    2: "ScheduledJob",            # test: tech="РегламентноеЗадание1"
    3: "DocumentNumerator",       # test: tech="НумераторДокументов1"
    4: "WebService",              # test: tech="WebСервис1"
    5: "CommonAttribute",         # test: tech="ОбщийРеквизит1"
    6: "Role",                    # test: tech="Роль1" (confirmed cross-DB)
    7: "Role",                    # MessageCenter only, type 7
    12: "CommonModule",           # test: tech="ОбщийМодуль1"
    13: "TaskForm|BusinessProcessForm",  # sub-type (Form)
    14: "FilterCriterion",        # test: tech="КритерийОтбора1"
    16: "Constant",               # test: tech="Константа1" (confirmed cross-DB)
    17: "DataProcessor",          # test: tech="Обработка1"
    19: "Report",                 # test: tech="Отчет1"
    20: "Enum",                   # test: tech="Перечисление1"
    22: "Subsystem",              # test: tech="Подсистема1"
    26: "DocumentJournal",        # test: tech="ЖурналДокументов1"
    30: "BusinessProcess",        # test: tech="БизнесПроцесс1"
    33: "InformationRegister",    # confirmed cross-DB (no tech name)
    34: "ChartOfCharacteristicType", # test: tech="ПланВидовХарактеристик1"
    37: "ExchangePlan",           # test: tech="ПланОбмена1"
    40: "Document",               # test: tech="Документ1"
    57: "Catalog",                # test: tech="Справочник1"
    68: "Configuration",          # test: tech="ПараметрыБлокировки" (Ext)
}

# Total known type_nums: 23 out of ~50 possible
# Unknown type_nums: 8, 9, 10, 11, 15, 18, 21, 23, 24, 25, 27, 28, 29, 31, 32,
#                     35, 36, 38, 39, 41-56, 58-67, 69-99
# These require a DB with objects of those types (AccountingRegisters,
# AccumulationRegisters, CalculationRegisters, ExchangePlans, Sequences,
# CommonCommands, CommonPictures, EventSubscriptions, FunctionalOptions, etc.)


def get_type_name_from_type_num(type_num: int) -> str | None:
    """Lookup type_name from type_num reference (test DB mapping)."""
    return TYPE_NUM_REFERENCE.get(type_num)
