"""Parse 1C metadata XML export (.staff/.export_from_1c/) into structured models.

Reads the XML files produced by 1C:Enterprise config dump (ConfigDumpInfo format),
extracts Properties, ChildObjects (attributes, tabular sections, forms, commands, etc.),
and links by UUID to SchemaRegistry objects.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from py1cv8.config import EXPORT_DIR

# Directory name -> 1C type_name (as used in DBNames)
DIR_TO_TYPE: dict[str, str] = {
    "Catalogs": "Reference",
    "Documents": "Document",
    "Constants": "Const",
    "Enums": "Enum",
    "InformationRegisters": "InfoRg",
    "ChartsOfCharacteristicTypes": "Chrc",
    "DataProcessors": "DataProcessor",
    "Reports": "Report",
    "CommonModules": "CommonModule",
    "CommonForms": "CommonForm",
    "CommonTemplates": "CommonTemplate",
    "CommonPictures": "CommonPicture",
    "Roles": "Role",
    "Subsystems": "Subsystem",
    "ScheduledJobs": "ScheduledJob",
    "CommandGroups": "CommandGroup",
    "CommonCommands": "CommonCommand",
    "DefinedTypes": "DefinedType",
    "DocumentNumerators": "DocumentNumerator",
    "EventSubscriptions": "EventSubscription",
    "Interfaces": "Interface",
    "Languages": "Language",
    "SessionParameters": "SessionParameter",
    "Styles": "Style",
    "WebSocketClients": "WebSocketClient",
    "Ext": "Ext",
    "AccumulationRegisters": "AccumulationRegister",
    "AccountingRegisters": "AccountingRegister",
    "CalculationRegisters": "CalculationRegister",
    "ExternalDataProcessors": "ExternalDataProcessor",
    "ExternalDataSources": "ExternalDataSource",
    "Sequences": "Sequence",
    "WSReferences": "WSReference",
}

NS = {
    "md": "http://v8.1c.ru/8.3/MDClasses",
    "v8": "http://v8.1c.ru/8.1/data/core",
    "xr": "http://v8.1c.ru/8.3/xcf/readable",
}


@dataclass
class TypeQualifierInfo:
    """Qualifiers for a 1C type."""

    length: int | None = None
    allowed_length: str | None = None
    digits: int | None = None
    fraction_digits: int | None = None
    allowed_sign: str | None = None
    date_fractions: str | None = None


@dataclass
class AttributeTypeInfo:
    """Full 1C type description for an attribute."""

    types: list[str] = field(default_factory=list)
    qualifiers: TypeQualifierInfo = field(default_factory=TypeQualifierInfo)

    @property
    def display(self) -> str:
        """Readable: 'String(100)', 'Number(15,2)', 'Date(DateTime)', 'Boolean, String(1024)'."""
        parts: list[str] = []
        for t in self.types:
            q = self.qualifiers
            if t in ("xs:string", "v8:FixedString"):
                if q.length and q.length > 0:
                    t = f"String({q.length}"
                    if q.allowed_length == "Variable":
                        t += ",V"
                    t += ")"
                else:
                    t = "String"
            elif t in ("xs:decimal", "v8:FixedDecimal", "xs:float", "xs:double"):
                if q.digits is not None and q.fraction_digits is not None:
                    t = f"Number({q.digits},{q.fraction_digits})"
                elif q.digits is not None:
                    t = f"Number({q.digits})"
                else:
                    t = "Number"
            elif t in ("xs:dateTime", "xs:date", "xs:time"):
                t = f"Date({q.date_fractions})" if q.date_fractions else "Date"
            elif t == "xs:boolean":
                t = "Boolean"
            elif t == "v8:ValueStorage":
                t = "ValueStorage"
            elif t == "v8:UUID":
                t = "UUID"
            elif t == "v8:BinaryData":
                t = "BinaryData"
            elif t == "v8:Graphics":
                t = "Picture"
            elif t == "v8:Version":
                t = "Version"
            elif t == "v8:Text":
                t = "Text"
            elif t == "v8:Color":
                t = "Color"
            elif t == "cfg:AnyIBRef":
                t = "AnyRef"
            elif t.startswith("cfg:CatalogRef."):
                t = t.replace("cfg:CatalogRef.", "CatalogRef.")
            elif t.startswith("cfg:DocumentRef."):
                t = t.replace("cfg:DocumentRef.", "DocumentRef.")
            elif t.startswith("cfg:EnumRef."):
                t = t.replace("cfg:EnumRef.", "EnumRef.")
            elif t.startswith("cfg:"):
                t = t[4:]
            parts.append(t)
        return ", ".join(parts) if parts else "?"


@dataclass
class GeneratedTypeInfo:
    """Generated 1C type for a metadata object (Object, Ref, Manager, etc.)."""

    name: str
    category: str
    type_id: str
    value_id: str


@dataclass
class AttributeInfo:
    """A metadata attribute (реквизит)."""

    uuid: str
    name: str
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    type_info: AttributeTypeInfo = field(default_factory=AttributeTypeInfo)
    indexing: str = "DontIndex"
    full_text_search: str = "DontUse"
    data_history: str = "DontUse"
    password_mode: bool = False
    multiline: bool = False
    extended_edit: bool = False
    fill_checking: str = "DontCheck"
    use: str = "ForItem"
    format: str = ""
    mask: str = ""


@dataclass
class TabularSectionInfo:
    """A tabular section (табличная часть)."""

    uuid: str
    name: str
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    attributes: list[AttributeInfo] = field(default_factory=list)
    generated_types: list[GeneratedTypeInfo] = field(default_factory=list)
    use: str = "ForItem"


@dataclass
class CommandInfo:
    """A metadata command (команда)."""

    uuid: str
    name: str
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    group: str = ""
    command_parameter_type: str = ""
    parameter_use_mode: str = "Single"
    modifies_data: bool = False
    representation: str = "Auto"
    tooltip: dict[str, str] = field(default_factory=dict)
    picture: str = ""
    shortcut: str = ""


@dataclass
class EnumValueInfo:
    """A value in an enum (значение перечисления)."""

    uuid: str | None
    name: str
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""


@dataclass
class ObjectMetadata:
    """Full metadata for a 1C object, parsed from XML export."""

    uuid: str
    type_name: str  # Catalog, Document, Constant, etc.
    name: str       # Tech name like 'ирАлгоритмы'
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    generated_types: list[GeneratedTypeInfo] = field(default_factory=list)

    # Business logic (varies by type)
    hierarchical: bool | None = None
    hierarchy_type: str | None = None
    owners: list[str] = field(default_factory=list)
    subordination_use: str | None = None
    code_length: int | None = None
    description_length: int | None = None
    code_type: str | None = None
    check_unique: bool | None = None
    autonumbering: bool | None = None
    default_presentation: str | None = None
    posting: str | None = None
    numerator: str | None = None
    number_type: str | None = None
    number_length: int | None = None
    number_periodicity: str | None = None
    periodicity: str | None = None
    write_mode: str | None = None
    edit_type: str | None = None
    quick_choice: bool | None = None
    choice_mode: str | None = None
    data_lock_control_mode: str | None = None
    full_text_search: str | None = None
    data_history: str | None = None
    create_on_input: str | None = None
    input_by_string: list[str] = field(default_factory=list)

    # Children
    attributes: list[AttributeInfo] = field(default_factory=list)
    tabular_sections: list[TabularSectionInfo] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    commands: list[CommandInfo] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    enum_values: list[EnumValueInfo] = field(default_factory=list)

    # Presentations
    object_presentation: dict[str, str] = field(default_factory=dict)
    list_presentation: dict[str, str] = field(default_factory=dict)
    explanation: str = ""


def _parse_synonym(el: ET.Element | None) -> dict[str, str]:
    """Parse <Synonym> with <v8:item> children into {lang: text}."""
    if el is None:
        return {}
    result: dict[str, str] = {}
    for item in el.findall("v8:item", NS):
        lang = item.findtext("v8:lang", "", NS)
        content = item.findtext("v8:content", "", NS)
        if lang:
            result[lang] = content
    return result


def _parse_type(el: ET.Element | None) -> AttributeTypeInfo:
    """Parse <Type> element with v8:Type children and qualifiers."""
    if el is None:
        return AttributeTypeInfo()
    types: list[str] = []
    q = TypeQualifierInfo()
    for child in el:
        tag = child.tag
        if tag.endswith("}Type") or tag == "Type":
            types.append(child.text or "")
        elif tag.endswith("}StringQualifiers"):
            q.length = _int_or_none(child.findtext("v8:Length", "", NS))
            q.allowed_length = child.findtext("v8:AllowedLength", "", NS) or None
        elif tag.endswith("}NumberQualifiers"):
            q.digits = _int_or_none(child.findtext("v8:Digits", "", NS))
            q.fraction_digits = _int_or_none(child.findtext("v8:FractionDigits", "", NS))
            q.allowed_sign = child.findtext("v8:AllowedSign", "", NS) or None
        elif tag.endswith("}DateQualifiers"):
            q.date_fractions = child.findtext("v8:DateFractions", "", NS) or None
        elif tag.endswith("}TypeSet"):
            types.append(child.text or "")
    return AttributeTypeInfo(types=types, qualifiers=q)


def _int_or_none(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _parse_generated_types(root: ET.Element) -> list[GeneratedTypeInfo]:
    """Parse <xr:GeneratedType> entries from <InternalInfo>."""
    types: list[GeneratedTypeInfo] = []
    for gt in root.findall(".//xr:GeneratedType", NS):
        name = gt.get("name", "")
        category = gt.get("category", "")
        type_id = gt.findtext("xr:TypeId", "", NS)
        value_id = gt.findtext("xr:ValueId", "", NS)
        if name:
            types.append(GeneratedTypeInfo(
                name=name, category=category,
                type_id=type_id, value_id=value_id,
            ))
    return types


def _parse_attributes(parent: ET.Element) -> list[AttributeInfo]:
    """Parse <Attribute> elements from <ChildObjects>."""
    attrs: list[AttributeInfo] = []
    for el in parent.findall("md:Attribute", NS):
        uuid = el.get("uuid", "")
        props = el.find("md:Properties", NS)
        if props is None:
            continue
        attr = AttributeInfo(
            uuid=uuid,
            name=props.findtext("md:Name", "", NS),
            synonym=_parse_synonym(props.find("md:Synonym", NS)),
            comment=props.findtext("md:Comment", "", NS),
            type_info=_parse_type(props.find("md:Type", NS)),
            indexing=props.findtext("md:Indexing", "DontIndex", NS),
            full_text_search=props.findtext("md:FullTextSearch", "DontUse", NS),
            data_history=props.findtext("md:DataHistory", "DontUse", NS),
            password_mode=props.findtext("md:PasswordMode", "false", NS) == "true",
            multiline=props.findtext("md:MultiLine", "false", NS) == "true",
            extended_edit=props.findtext("md:ExtendedEdit", "false", NS) == "true",
            fill_checking=props.findtext("md:FillChecking", "DontCheck", NS),
            use=props.findtext("md:Use", "ForItem", NS),
            format=props.findtext("md:Format", "", NS),
            mask=props.findtext("md:Mask", "", NS),
        )
        attrs.append(attr)
    return attrs


def _parse_tabular_sections(parent: ET.Element) -> list[TabularSectionInfo]:
    """Parse <TabularSection> elements from <ChildObjects>."""
    sections: list[TabularSectionInfo] = []
    for el in parent.findall("md:TabularSection", NS):
        uuid = el.get("uuid", "")
        props = el.find("md:Properties", NS)
        if props is None:
            continue
        section = TabularSectionInfo(
            uuid=uuid,
            name=props.findtext("md:Name", "", NS),
            synonym=_parse_synonym(props.find("md:Synonym", NS)),
            comment=props.findtext("md:Comment", "", NS),
            attributes=_parse_attributes(el),
            use=props.findtext("md:Use", "ForItem", NS),
        )
        section.generated_types = _parse_generated_types(el)
        sections.append(section)
    return sections


def _parse_commands(parent: ET.Element) -> list[CommandInfo]:
    """Parse <Command> elements from <ChildObjects>."""
    cmds: list[CommandInfo] = []
    for el in parent.findall("md:Command", NS):
        uuid = el.get("uuid", "")
        props = el.find("md:Properties", NS)
        if props is None:
            continue
        cmd = CommandInfo(
            uuid=uuid,
            name=props.findtext("md:Name", "", NS),
            synonym=_parse_synonym(props.find("md:Synonym", NS)),
            comment=props.findtext("md:Comment", "", NS),
            group=props.findtext("md:Group", "", NS),
            command_parameter_type=props.findtext("md:CommandParameterType", "", NS),
            parameter_use_mode=props.findtext("md:ParameterUseMode", "Single", NS),
            modifies_data=props.findtext("md:ModifiesData", "false", NS) == "true",
            representation=props.findtext("md:Representation", "Auto", NS),
            tooltip=_parse_synonym(props.find("md:ToolTip", NS)),
            picture=props.findtext("md:Picture", "", NS),
            shortcut=props.findtext("md:Shortcut", "", NS),
        )
        cmds.append(cmd)
    return cmds


def _parse_enum_values(parent: ET.Element) -> list[EnumValueInfo]:
    """Parse <EnumValue> elements from <ChildObjects>."""
    values: list[EnumValueInfo] = []
    for el in parent.findall("md:EnumValue", NS):
        uuid = el.get("uuid")
        props = el.find("md:Properties", NS)
        if props is None:
            continue
        values.append(EnumValueInfo(
            uuid=uuid,
            name=props.findtext("md:Name", "", NS),
            synonym=_parse_synonym(props.find("md:Synonym", NS)),
            comment=props.findtext("md:Comment", "", NS),
        ))
    return values


def _parse_properties(props: ET.Element | None) -> dict:
    """Parse common properties into a flat dict."""
    if props is None:
        return {}
    result: dict = {}
    text_tags = [
        "Name", "Comment", "Hierarchical", "HierarchyType", "LimitLevelCount",
        "LevelCount", "FoldersOnTop", "UseStandardCommands", "CodeLength",
        "DescriptionLength", "CodeType", "CodeAllowedLength", "CodeSeries",
        "CheckUnique", "Autonumbering", "DefaultPresentation", "EditType",
        "QuickChoice", "ChoiceMode", "IncludeHelpInContents",
        "DataLockControlMode", "FullTextSearch", "ObjectPresentation",
        "ExtendedObjectPresentation", "ListPresentation", "ExtendedListPresentation",
        "Explanation", "CreateOnInput", "ChoiceHistoryOnInput",
        "DataHistory", "Posting", "RealTimePosting", "Numerator",
        "NumberType", "NumberLength", "NumberAllowedLength",
        "NumberPeriodicity", "Periodicity", "WriteMode",
        "SubordinationUse", "PredefinedDataUpdate",
        "SearchStringModeOnInputByString",
    ]
    for tag in text_tags:
        val = props.findtext(f"md:{tag}", "", NS)
        if val:
            result[tag] = val
    # Boolean tags
    for tag in ["Hierarchical", "LimitLevelCount", "FoldersOnTop",
                 "CheckUnique", "Autonumbering", "UseStandardCommands",
                 "IncludeHelpInContents", "QuickChoice"]:
        val = props.findtext(f"md:{tag}", "", NS)
        if val:
            result[tag] = val
    # InputByString
    ibs = props.find("md:InputByString", NS)
    if ibs is not None:
        result["InputByString"] = [
            f.text for f in ibs.findall("xr:Field", NS) if f.text
        ]
    return result


def parse_object_xml(filepath: str | os.PathLike) -> ObjectMetadata | None:
    """Parse a single 1C metadata object XML file into ObjectMetadata."""
    try:
        tree = ET.parse(filepath)
    except (ET.ParseError, FileNotFoundError, OSError):
        return None
    root = tree.getroot()

    # Find the first child element (e.g., <Catalog>, <Document>, etc.)
    obj_el = None
    type_name = ""
    for child in root:
        tag = child.tag
        if "}" in tag:
            local = tag.split("}", 1)[1]
            if local in ("Configuration",):
                continue
            type_name = local
            obj_el = child
            break

    if obj_el is None:
        return None

    uuid = obj_el.get("uuid", "")
    props = obj_el.find("md:Properties", NS)
    if props is None:
        return None

    name = props.findtext("md:Name", "", NS)
    if not name:
        return None

    meta = ObjectMetadata(
        uuid=uuid.lower(),
        type_name=type_name,
        name=name,
        synonym=_parse_synonym(props.find("md:Synonym", NS)),
        comment=props.findtext("md:Comment", "", NS),
        generated_types=_parse_generated_types(obj_el),
    )

    # Business logic
    raw = _parse_properties(props)
    meta.hierarchical = _bool_or_none(raw.get("Hierarchical"))
    meta.hierarchy_type = raw.get("HierarchyType")
    meta.subordination_use = raw.get("SubordinationUse")
    meta.code_length = _int_or_none(raw.get("CodeLength"))
    meta.description_length = _int_or_none(raw.get("DescriptionLength"))
    meta.code_type = raw.get("CodeType")
    meta.check_unique = _bool_or_none(raw.get("CheckUnique"))
    meta.autonumbering = _bool_or_none(raw.get("Autonumbering"))
    meta.default_presentation = raw.get("DefaultPresentation")
    meta.posting = raw.get("Posting")
    meta.numerator = raw.get("Numerator")
    meta.number_type = raw.get("NumberType")
    meta.number_length = _int_or_none(raw.get("NumberLength"))
    meta.number_periodicity = raw.get("NumberPeriodicity")
    meta.periodicity = raw.get("Periodicity")
    meta.write_mode = raw.get("WriteMode")
    meta.edit_type = raw.get("EditType")
    meta.quick_choice = _bool_or_none(raw.get("QuickChoice"))
    meta.choice_mode = raw.get("ChoiceMode")
    meta.data_lock_control_mode = raw.get("DataLockControlMode")
    meta.full_text_search = raw.get("FullTextSearch")
    meta.data_history = raw.get("DataHistory")
    meta.create_on_input = raw.get("CreateOnInput")
    meta.input_by_string = raw.get("InputByString", [])
    meta.object_presentation = _parse_synonym(props.find("md:ObjectPresentation", NS))
    meta.list_presentation = _parse_synonym(props.find("md:ListPresentation", NS))
    meta.explanation = props.findtext("md:Explanation", "", NS)

    # Children
    child_objects = obj_el.find("md:ChildObjects", NS)
    if child_objects is not None:
        meta.attributes = _parse_attributes(child_objects)
        meta.tabular_sections = _parse_tabular_sections(child_objects)
        meta.commands = _parse_commands(child_objects)
        meta.enum_values = _parse_enum_values(child_objects)
        # Forms: <Form>Name</Form>
        meta.forms = [
            f.text for f in child_objects.findall("md:Form", NS) if f.text
        ]
        # Templates: <Template>Name</Template>
        meta.templates = [
            t.text for t in child_objects.findall("md:Template", NS) if t.text
        ]

    return meta


def _bool_or_none(v: str | None) -> bool | None:
    if v is None:
        return None
    return v.lower() in ("true", "1")


def scan_export_directory(export_dir: str | os.PathLike = EXPORT_DIR) -> dict[str, ObjectMetadata]:
    """Scan the export directory and return UUID -> ObjectMetadata mapping.

    Also populates a 'by_path' lookup and returns by UUID.
    """
    meta_by_uuid: dict[str, ObjectMetadata] = {}
    export_path = Path(export_dir)
    if not export_path.is_dir():
        return meta_by_uuid

    # Scan each type subdirectory
    for subdir in export_path.iterdir():
        if not subdir.is_dir() or subdir.name == "test_database":
            continue
        type_name = DIR_TO_TYPE.get(subdir.name, subdir.name)
        for xml_file in sorted(subdir.glob("*.xml")):
            try:
                meta = parse_object_xml(str(xml_file))
                if meta is not None and meta.uuid:
                    meta.type_name = type_name
                    meta_by_uuid[meta.uuid] = meta
            except ET.ParseError:
                continue

    # Scan test_database subdirectory (supplements, not overrides)
    test_dir = export_path / "test_database"
    if test_dir.is_dir():
        for subdir in test_dir.iterdir():
            if not subdir.is_dir():
                continue
            type_name = DIR_TO_TYPE.get(subdir.name, subdir.name)
            for xml_file in sorted(subdir.glob("*.xml")):
                try:
                    meta = parse_object_xml(str(xml_file))
                    if meta is not None and meta.uuid and meta.uuid not in meta_by_uuid:
                        meta.type_name = type_name
                        meta_by_uuid[meta.uuid] = meta
                except ET.ParseError:
                    continue

    return meta_by_uuid


# ── Class implementation (satisfies XmlMetadataProvider contract) ─────────


class XmlMetadataProviderImpl:
    """Scans .staff/.export_from_1c/ directories and parses XML metadata.

    Satisfies: contracts.xml_metadata.XmlMetadataProvider
    """

    def __init__(self, export_dir: str | Path | None = None) -> None:
        self._export_dir = Path(export_dir) if export_dir else EXPORT_DIR

    def scan_export_directory(
        self,
        export_dir: str | Path | None = None,
    ) -> dict[str, ObjectMetadata]:
        base = Path(export_dir) if export_dir else self._export_dir
        return scan_export_directory(str(base))

    @staticmethod
    def parse_object_xml(filepath: str | Path) -> ObjectMetadata | None:
        return parse_object_xml(str(filepath))
