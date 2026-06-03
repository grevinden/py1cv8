"""Tests for config version parsing from ConfigDumpInfo.xml."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from py1cv8.config_versions import (
    _collect_versions,
    parse_config_dump_info,
    resolve_config_dump_path,
)


def test_parse_config_dump_info(tmp_path) -> None:
    xml_file = tmp_path / "ConfigDumpInfo.xml"
    xml_file.write_text(
        '<?xml version="1.0"?>'
        '<Metadata xmlns="http://v8.1c.ru/8.3/xcf/dumpinfo">'
        '<Metadata configVersion="abc1230000000000000000000000000000000000" id="obj1"/>'
        '<Metadata configVersion="def4560000000000000000000000000000000000" id="obj2.0"/>'
        '<Metadata id="no_version"/>'
        '<Metadata configVersion="ghi7890000000000000000000000000000000000" id="obj3"/>'
        '</Metadata>',
        encoding="utf-8",
    )
    versions = parse_config_dump_info(xml_file)
    assert versions == {
        "obj1": "abc1230000000000000000000000000000000000",
        "obj2.0": "def4560000000000000000000000000000000000",
        "obj3": "ghi7890000000000000000000000000000000000",
    }
    assert "no_version" not in versions


def test_parse_config_dump_info_nested(tmp_path) -> None:
    xml_file = tmp_path / "ConfigDumpInfo.xml"
    xml_file.write_text(
        '<?xml version="1.0"?>'
        '<Metadata xmlns="http://v8.1c.ru/8.3/xcf/dumpinfo">'
        '<Metadata configVersion="aaa0000000000000000000000000000000000000" id="parent">'
        '<Metadata configVersion="bbb0000000000000000000000000000000000000" id="child"/>'
        '</Metadata>'
        '</Metadata>',
        encoding="utf-8",
    )
    versions = parse_config_dump_info(xml_file)
    assert versions == {
        "parent": "aaa0000000000000000000000000000000000000",
        "child": "bbb0000000000000000000000000000000000000",
    }


def test_parse_config_dump_info_empty(tmp_path) -> None:
    xml_file = tmp_path / "ConfigDumpInfo.xml"
    xml_file.write_text(
        '<?xml version="1.0"?>'
        '<Metadata xmlns="http://v8.1c.ru/8.3/xcf/dumpinfo">'
        '</Metadata>',
        encoding="utf-8",
    )
    versions = parse_config_dump_info(xml_file)
    assert versions == {}


def test_collect_versions_other_namespace_skipped() -> None:
    versions: dict[str, str] = {}
    root = ET.fromstring(
        '<root><Other configVersion="xxx0000000000000000000000000000000000000" id="other"/></root>',
    )
    _collect_versions(root, versions)
    assert versions == {}


def test_resolve_config_dump_path_first_exists(tmp_path) -> None:
    (tmp_path / "ConfigDumpInfo.xml").write_text("<root/>", encoding="utf-8")
    result = resolve_config_dump_path(tmp_path)
    assert result == tmp_path / "ConfigDumpInfo.xml"


def test_resolve_config_dump_path_second_exists(tmp_path) -> None:
    sub = tmp_path / "test_database"
    sub.mkdir(parents=True)
    (sub / "ConfigDumpInfo.xml").write_text("<root/>", encoding="utf-8")
    result = resolve_config_dump_path(tmp_path)
    assert result == sub / "ConfigDumpInfo.xml"


def test_resolve_config_dump_path_neither_exists(tmp_path) -> None:
    result = resolve_config_dump_path(tmp_path)
    assert result is None
