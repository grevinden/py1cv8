# ruff: noqa: E501
"""Parse 1C metadata XML export files into ObjectMetadata models.

Public API: parse_object_xml(), scan_export_directory().
Delegates low-level XML parsing to mx_parse_helpers.
"""

from __future__ import annotations

import os
from pathlib import Path

from py1cv8.config import EXPORT_DIR
from py1cv8.mx_models import ObjectMetadata
from py1cv8.mx_parse_helpers import (  # noqa: F401
    DIR_TO_TYPE,
    NS,
    _bool_or_none,
    _int_or_none,
    _parse_attributes,
    _parse_commands,
    _parse_enum_values,
    _parse_generated_types,
    _parse_properties,
    _parse_synonym,
    _parse_tabular_sections,
    _parse_type,
)


def parse_object_xml(filepath: str | os.PathLike) -> ObjectMetadata | None:
    """Parse a single 1C metadata object XML file into ObjectMetadata."""
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(filepath)
    except (ET.ParseError, FileNotFoundError, OSError):
        return None
    root = tree.getroot()

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

    child_objects = obj_el.find("md:ChildObjects", NS)
    if child_objects is not None:
        meta.attributes = _parse_attributes(child_objects)
        meta.tabular_sections = _parse_tabular_sections(child_objects)
        meta.commands = _parse_commands(child_objects)
        meta.enum_values = _parse_enum_values(child_objects)
        meta.forms = [
            f.text for f in child_objects.findall("md:Form", NS) if f.text
        ]
        meta.templates = [
            t.text for t in child_objects.findall("md:Template", NS) if t.text
        ]

    return meta


def scan_export_directory(export_dir: str | os.PathLike = EXPORT_DIR) -> dict[str, ObjectMetadata]:
    """Scan the export directory and return UUID -> ObjectMetadata mapping."""
    import xml.etree.ElementTree as ET
    meta_by_uuid: dict[str, ObjectMetadata] = {}
    export_path = Path(export_dir)
    if not export_path.is_dir():
        return meta_by_uuid

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
