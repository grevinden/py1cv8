# ruff: noqa: E501
"""Parse helpers for 1C metadata XML export files.

Single responsibility: low-level XML parsing functions.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from py1cv8.mx_models import (
    AttributeInfo,
    AttributeTypeInfo,
    CommandInfo,
    EnumValueInfo,
    GeneratedTypeInfo,
    TabularSectionInfo,
    TypeQualifierInfo,
)

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


def _parse_synonym(el: ET.Element | None) -> dict[str, str]:
    if el is None:
        return {}
    result: dict[str, str] = {}
    for item in el.findall("v8:item", NS):
        lang = item.findtext("v8:lang", "", NS)
        content = item.findtext("v8:content", "", NS)
        if lang:
            result[lang] = content
    return result


def _int_or_none(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _bool_or_none(v: str | None) -> bool | None:
    if v is None:
        return None
    return v.lower() in ("true", "1")


def _parse_type(el: ET.Element | None) -> AttributeTypeInfo:
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


def _parse_generated_types(root: ET.Element) -> list[GeneratedTypeInfo]:
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
    for tag in ["Hierarchical", "LimitLevelCount", "FoldersOnTop",
                 "CheckUnique", "Autonumbering", "UseStandardCommands",
                 "IncludeHelpInContents", "QuickChoice"]:
        val = props.findtext(f"md:{tag}", "", NS)
        if val:
            result[tag] = val
    ibs = props.find("md:InputByString", NS)
    if ibs is not None:
        result["InputByString"] = [
            f.text for f in ibs.findall("xr:Field", NS) if f.text
        ]
    return result
