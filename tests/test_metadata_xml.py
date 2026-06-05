"""Tests for metadata_xml.py — 1C XML export parser."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from py1cv8.metadata_xml import (
    AttributeInfo,
    AttributeTypeInfo,
    CommandInfo,
    EnumValueInfo,
    GeneratedTypeInfo,
    ObjectMetadata,
    TabularSectionInfo,
    TypeQualifierInfo,
    parse_object_xml,
    scan_export_directory,
)

# ── Data model construction ───────────────────────────────────────────────


def test_type_qualifier_defaults() -> None:
    q = TypeQualifierInfo()
    assert q.length is None
    assert q.digits is None


def test_attribute_type_info_empty() -> None:
    at = AttributeTypeInfo()
    assert at.display == "?"


def test_attribute_type_info_string() -> None:
    at = AttributeTypeInfo(
        types=["xs:string"],
        qualifiers=TypeQualifierInfo(length=100, allowed_length="Variable"),
    )
    assert "String(100,V)" in at.display


def test_attribute_type_info_number() -> None:
    at = AttributeTypeInfo(
        types=["xs:decimal"],
        qualifiers=TypeQualifierInfo(digits=15, fraction_digits=2),
    )
    assert at.display == "Number(15,2)"


def test_attribute_type_info_date() -> None:
    at = AttributeTypeInfo(
        types=["xs:dateTime"],
        qualifiers=TypeQualifierInfo(date_fractions="DateTime"),
    )
    assert at.display == "Date(DateTime)"


def test_attribute_type_info_boolean() -> None:
    at = AttributeTypeInfo(types=["xs:boolean"])
    assert at.display == "Boolean"


def test_attribute_type_info_multi() -> None:
    at = AttributeTypeInfo(
        types=["xs:string", "xs:decimal"],
        qualifiers=TypeQualifierInfo(length=50, digits=10, fraction_digits=2),
    )
    assert "String(50)" in at.display
    assert "Number(10,2)" in at.display


def test_attribute_type_info_cfg_ref() -> None:
    at = AttributeTypeInfo(types=["cfg:CatalogRef.Справочник1"])
    assert "CatalogRef.Справочник1" in at.display


def test_attribute_type_info_anyref() -> None:
    at = AttributeTypeInfo(types=["cfg:AnyIBRef"])
    assert "AnyRef" in at.display


def test_attribute_type_info_valuestorage() -> None:
    at = AttributeTypeInfo(types=["v8:ValueStorage"])
    assert "ValueStorage" in at.display


# ── GeneratedTypeInfo ─────────────────────────────────────────────────────


def test_generated_type_info() -> None:
    gt = GeneratedTypeInfo(
        name="CatalogObject.ирАлгоритмы",
        category="Object",
        type_id="e962bd02-...",
        value_id="3a20a2b6-...",
    )
    assert gt.name == "CatalogObject.ирАлгоритмы"
    assert gt.category == "Object"


# ── AttributeInfo ─────────────────────────────────────────────────────────


def test_attribute_info() -> None:
    attr = AttributeInfo(
        uuid="abc-123",
        name="Код",
        synonym={"ru": "Код", "en": "Code"},
        type_info=AttributeTypeInfo(
            types=["xs:string"],
            qualifiers=TypeQualifierInfo(length=20),
        ),
        indexing="Index",
    )
    assert attr.name == "Код"
    assert attr.synonym["ru"] == "Код"
    assert attr.type_info.display == "String(20)"


# ── TabularSectionInfo ────────────────────────────────────────────────────


def test_tabular_section_info() -> None:
    section = TabularSectionInfo(
        uuid="def-456",
        name="Товары",
        synonym={"ru": "Товары"},
        attributes=[
            AttributeInfo(uuid="attr-ts-1", name="Номенклатура",
                          type_info=AttributeTypeInfo(types=["cfg:CatalogRef.Товары"])),
        ],
    )
    assert section.name == "Товары"
    assert len(section.attributes) == 1
    assert section.attributes[0].type_info.display == "CatalogRef.Товары"


# ── CommandInfo ───────────────────────────────────────────────────────────


def test_command_info() -> None:
    cmd = CommandInfo(
        uuid="ghi-789",
        name="ЗаполнитьПоШаблону",
        modifies_data=True,
    )
    assert cmd.name == "ЗаполнитьПоШаблону"
    assert cmd.modifies_data is True


# ── EnumValueInfo ─────────────────────────────────────────────────────────


def test_enum_value_info() -> None:
    ev = EnumValueInfo(
        uuid="jkl-012",
        name="Значение1",
        synonym={"ru": "Значение 1"},
    )
    assert ev.name == "Значение1"


# ── ObjectMetadata ────────────────────────────────────────────────────────


def test_object_metadata_defaults() -> None:
    meta = ObjectMetadata(
        uuid="aaa-bbb",
        type_name="Catalog",
        name="Справочник1",
    )
    assert not meta.attributes
    assert meta.hierarchical is None


def test_object_metadata_full() -> None:
    meta = ObjectMetadata(
        uuid="ccc-ddd",
        type_name="Document",
        name="Документ1",
        synonym={"ru": "Документ 1"},
        hierarchical=False,
        posting="Immediate",
        attributes=[
            AttributeInfo(
                uuid="attr-doc-1",
                name="Номер",
                type_info=AttributeTypeInfo(
                    types=["xs:string"],
                    qualifiers=TypeQualifierInfo(length=20),
                ),
            ),
        ],
        tabular_sections=[
            TabularSectionInfo(
                uuid="eee-fff",
                name="Товары",
                attributes=[
                        AttributeInfo(
                            uuid="attr-ts-doc-1",
                            name="Количество",
                            type_info=AttributeTypeInfo(
                                types=["xs:decimal"],
                                qualifiers=TypeQualifierInfo(digits=15, fraction_digits=2),
                            ),
                        ),
                ],
            ),
        ],
        forms=["ФормаДокумента"],
            commands=[CommandInfo(uuid="cmd-1", name="Провести")],
    )
    assert meta.type_name == "Document"
    assert meta.posting == "Immediate"
    assert len(meta.attributes) == 1
    assert len(meta.tabular_sections) == 1
    assert meta.tabular_sections[0].attributes[0].type_info.display == "Number(15,2)"
    assert meta.forms == ["ФормаДокумента"]


# ── XML parsing helpers ────────────────────────────────────────────────────


def test_parse_object_xml_nonexistent() -> None:
    result = parse_object_xml(Path("nonexistent.xml"))
    assert result is None


def _make_xml(
    type_tag: str = "Catalog",
    uuid: str = "abc-123",
    name: str = "ТестовыйСправочник",
    props_extra: str = "",
) -> str:
    return f"""<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"
  xmlns:md="http://v8.1c.ru/8.3/MDClasses"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xr="http://v8.1c.ru/8.3/xcf/readable">
  <{type_tag} uuid="{uuid}">
    <md:Properties>
      <md:Name>{name}</md:Name>
      <md:Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Тестовый справочник</v8:content>
        </v8:item>
        <v8:item>
          <v8:lang>en</v8:lang>
          <v8:content>Test catalog</v8:content>
        </v8:item>
      </md:Synonym>
      <md:Comment>Some comment</md:Comment>
      {props_extra}
    </md:Properties>
    <md:ChildObjects>
      <md:Attribute uuid="attr-1">
        <md:Properties>
          <md:Name>Код</md:Name>
          <md:Synonym>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Код</v8:content>
            </v8:item>
          </md:Synonym>
          <md:Type>
            <v8:Type>xs:string</v8:Type>
            <v8:StringQualifiers>
              <v8:Length>20</v8:Length>
              <v8:AllowedLength>Fixed</v8:AllowedLength>
            </v8:StringQualifiers>
          </md:Type>
        </md:Properties>
      </md:Attribute>
    </md:ChildObjects>
    <md:InternalInfo>
      <xr:GeneratedType name="CatalogObject.ТестовыйСправочник" category="Object">
        <xr:TypeId>type-id-1</xr:TypeId>
        <xr:ValueId>value-id-1</xr:ValueId>
      </xr:GeneratedType>
    </md:InternalInfo>
  </{type_tag}>
</MetaDataObject>"""


def test_parse_object_xml_simple(tmp_path: Path) -> None:
    xml_content = _make_xml()
    fp = tmp_path / "test.xml"
    fp.write_text(xml_content, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert meta.uuid == "abc-123"
    assert meta.name == "ТестовыйСправочник"
    assert meta.synonym.get("ru") == "Тестовый справочник"
    assert meta.synonym.get("en") == "Test catalog"
    assert meta.comment == "Some comment"
    assert len(meta.generated_types) == 1
    assert meta.generated_types[0].name == "CatalogObject.ТестовыйСправочник"
    assert meta.generated_types[0].type_id == "type-id-1"
    assert len(meta.attributes) == 1
    assert meta.attributes[0].name == "Код"
    assert meta.attributes[0].type_info.display == "String(20)"


def test_parse_object_xml_enum(tmp_path: Path) -> None:
    xml_content = """<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"
      xmlns:md="http://v8.1c.ru/8.3/MDClasses"
      xmlns:v8="http://v8.1c.ru/8.1/data/core"
      xmlns:xr="http://v8.1c.ru/8.3/xcf/readable">
  <Enum uuid="enum-001">
    <md:Properties>
      <md:Name>СтатусыЗаказов</md:Name>
      <md:Synonym>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Статусы заказов</v8:content>
        </v8:item>
      </md:Synonym>
    </md:Properties>
    <md:ChildObjects>
      <md:EnumValue uuid="ev-1">
        <md:Properties>
          <md:Name>Новый</md:Name>
          <md:Synonym>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Новый</v8:content>
            </v8:item>
          </md:Synonym>
        </md:Properties>
      </md:EnumValue>
      <md:EnumValue uuid="ev-2">
        <md:Properties>
          <md:Name>ВРаботе</md:Name>
          <md:Synonym>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>В работе</v8:content>
            </v8:item>
          </md:Synonym>
        </md:Properties>
      </md:EnumValue>
    </md:ChildObjects>
  </Enum>
</MetaDataObject>"""
    fp = tmp_path / "enum.xml"
    fp.write_text(xml_content, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert meta.type_name == "Enum"
    assert len(meta.enum_values) == 2
    assert meta.enum_values[0].name == "Новый"
    assert meta.enum_values[1].name == "ВРаботе"


def test_parse_object_xml_document_business(tmp_path: Path) -> None:
    xml_content = _make_xml(
        type_tag="Document",
        uuid="doc-001",
        name="ПриходнаяНакладная",
        props_extra="""
      <md:Posting>Immediate</md:Posting>
      <md:WriteMode>Post</md:WriteMode>
      <md:NumberType>String</md:NumberType>
      <md:NumberLength>11</md:NumberLength>
      <md:NumberPeriodicity>Year</md:NumberPeriodicity>
      <md:CheckUnique>true</md:CheckUnique>
      <md:Autonumbering>true</md:Autonumbering>
    """,
    )
    fp = tmp_path / "doc.xml"
    fp.write_text(xml_content, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert meta.type_name == "Document"
    assert meta.posting == "Immediate"
    assert meta.write_mode == "Post"
    assert meta.number_type == "String"
    assert meta.number_length == 11
    assert meta.number_periodicity == "Year"
    assert meta.check_unique is True
    assert meta.autonumbering is True


# ── DIR_TO_TYPE mapping ────────────────────────────────────────────────────


def test_scan_export_directory_no_dir(tmp_path: Path) -> None:
    result = scan_export_directory(tmp_path / "nonexistent")
    assert result == {}


# ── Edge cases ─────────────────────────────────────────────────────────────


def test_type_info_fixed_string() -> None:
    at = AttributeTypeInfo(
        types=["v8:FixedString"],
        qualifiers=TypeQualifierInfo(length=10),
    )
    assert "String(10)" in at.display


def test_type_info_float() -> None:
    at = AttributeTypeInfo(types=["xs:float"])
    assert "Number" in at.display


def test_type_info_double() -> None:
    at = AttributeTypeInfo(types=["xs:double"])
    assert "Number" in at.display


def test_type_info_uuid() -> None:
    at = AttributeTypeInfo(types=["v8:UUID"])
    assert "UUID" in at.display
    assert at.display == "UUID"


def test_type_info_binary_data() -> None:
    at = AttributeTypeInfo(types=["v8:BinaryData"])
    assert "BinaryData" in at.display


def test_type_info_graphics() -> None:
    at = AttributeTypeInfo(types=["v8:Graphics"])
    assert "Picture" in at.display


def test_type_info_version() -> None:
    at = AttributeTypeInfo(types=["v8:Version"])
    assert "Version" in at.display


def test_type_info_text() -> None:
    at = AttributeTypeInfo(types=["v8:Text"])
    assert "Text" in at.display


def test_type_info_color() -> None:
    at = AttributeTypeInfo(types=["v8:Color"])
    assert "Color" in at.display


def test_type_info_fixed_decimal() -> None:
    at = AttributeTypeInfo(
        types=["v8:FixedDecimal"],
        qualifiers=TypeQualifierInfo(digits=5, fraction_digits=3),
    )
    assert "Number(5,3)" in at.display


def test_synonym_empty() -> None:
    from py1cv8.mx_parser import _parse_synonym

    result = _parse_synonym(None)
    assert result == {}


def test_generated_types_missing() -> None:
    from py1cv8.mx_parser import _parse_generated_types

    root = ET.fromstring("<root><irrelevant/></root>")
    assert _parse_generated_types(root) == []


# ── Remaining edge cases ────────────────────────────────────────────────────


def test_type_info_string_no_length() -> None:
    """String without length qualifiers shows as 'String'."""
    at = AttributeTypeInfo(
        types=["xs:string"],
        qualifiers=TypeQualifierInfo(),
    )
    assert at.display == "String"


def test_type_info_number_digits_only() -> None:
    """Number with only digits (no fraction) shows as Number(N)."""
    at = AttributeTypeInfo(
        types=["xs:decimal"],
        qualifiers=TypeQualifierInfo(digits=10),
    )
    assert at.display == "Number(10)"


def test_type_info_document_ref() -> None:
    at = AttributeTypeInfo(types=["cfg:DocumentRef.Заказ"])
    assert "DocumentRef.Заказ" in at.display


def test_type_info_enum_ref() -> None:
    at = AttributeTypeInfo(types=["cfg:EnumRef.Статусы"])
    assert "EnumRef.Статусы" in at.display


def test_type_info_other_cfg_ref() -> None:
    at = AttributeTypeInfo(types=["cfg:SomeRef.XYZ"])
    assert "SomeRef.XYZ" in at.display


def test_type_info_date_no_fractions() -> None:
    at = AttributeTypeInfo(
        types=["xs:dateTime"],
        qualifiers=TypeQualifierInfo(),
    )
    assert at.display == "Date"


def test_parse_type_none() -> None:
    """_parse_type returns empty AttributeTypeInfo when el is None."""
    from py1cv8.mx_parser import _parse_type
    result = _parse_type(None)
    assert isinstance(result, AttributeTypeInfo)
    assert result.types == []


def test_int_or_none_value_error() -> None:
    """_int_or_none returns None on ValueError."""
    from py1cv8.mx_parser import _int_or_none
    assert _int_or_none("not_a_number") is None


def test_int_or_none_none() -> None:
    """_int_or_none returns None on None input."""
    from py1cv8.mx_parser import _int_or_none
    assert _int_or_none(None) is None


def test_int_or_none_valid() -> None:
    """_int_or_none returns int on valid input."""
    from py1cv8.mx_parser import _int_or_none
    assert _int_or_none("42") == 42


def test_parse_properties_none() -> None:
    """_parse_properties returns empty dict when props is None."""
    from py1cv8.mx_parser import _parse_properties
    assert _parse_properties(None) == {}


def test_parse_object_xml_configuration_skipped(tmp_path: Path) -> None:
    """Configuration tag is skipped in parse_object_xml."""
    xml = """<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"
      xmlns:md="http://v8.1c.ru/8.3/MDClasses"
      xmlns:v8="http://v8.1c.ru/8.1/data/core"
      xmlns:xr="http://v8.1c.ru/8.3/xcf/readable">
    <Configuration uuid="cfg-001">
      <md:Properties>
        <md:Name>MyConfig</md:Name>
      </md:Properties>
    </Configuration>
  </MetaDataObject>"""
    fp = tmp_path / "configuration.xml"
    fp.write_text(xml)
    result = parse_object_xml(str(fp))
    assert result is None


def test_parse_object_xml_no_obj_el(tmp_path: Path) -> None:
    """No known element found returns None."""
    xml = "<root><Unknown><md:Properties><md:Name>X</md:Name></md:Properties></Unknown></root>"
    fp = tmp_path / "unknown.xml"
    fp.write_text(xml)
    result = parse_object_xml(str(fp))
    assert result is None


def test_parse_object_xml_no_properties(tmp_path: Path) -> None:
    """Missing Properties returns None."""
    xml = """<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"
      xmlns:md="http://v8.1c.ru/8.3/MDClasses">
    <Catalog uuid="cat-001">
      <md:Comment>no props here</md:Comment>
    </Catalog>
  </MetaDataObject>"""
    fp = tmp_path / "no_props.xml"
    fp.write_text(xml)
    result = parse_object_xml(str(fp))
    assert result is None


def test_parse_object_xml_empty_name(tmp_path: Path) -> None:
    """Empty Name returns None."""
    xml = """<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"
      xmlns:md="http://v8.1c.ru/8.3/MDClasses">
    <Catalog uuid="cat-001">
      <md:Properties>
        <md:Name></md:Name>
      </md:Properties>
    </Catalog>
  </MetaDataObject>"""
    fp = tmp_path / "empty_name.xml"
    fp.write_text(xml)
    result = parse_object_xml(str(fp))
    assert result is None


def _replace_child_objects(xml: str, new_block: str) -> str:
    """Replace the default ChildObjects block in _make_xml output."""
    old_block = """\
    <md:ChildObjects>
      <md:Attribute uuid="attr-1">
        <md:Properties>
          <md:Name>Код</md:Name>
          <md:Synonym>
            <v8:item>
              <v8:lang>ru</v8:lang>
              <v8:content>Код</v8:content>
            </v8:item>
          </md:Synonym>
          <md:Type>
            <v8:Type>xs:string</v8:Type>
            <v8:StringQualifiers>
              <v8:Length>20</v8:Length>
              <v8:AllowedLength>Fixed</v8:AllowedLength>
            </v8:StringQualifiers>
          </md:Type>
        </md:Properties>
      </md:Attribute>
    </md:ChildObjects>"""
    return xml.replace(old_block, new_block)


def test_parse_attribute_missing_props(tmp_path: Path) -> None:
    """Attribute without Properties is skipped."""
    xml = _make_xml()
    xml = _replace_child_objects(xml, """\
    <md:ChildObjects>
      <md:Attribute uuid="ok-attr">
        <md:Properties>
          <md:Name>Нормальный</md:Name>
        </md:Properties>
      </md:Attribute>
      <md:Attribute uuid="bad-attr">
        <md:Comment>no props</md:Comment>
      </md:Attribute>
    </md:ChildObjects>""")
    fp = tmp_path / "bad_attr.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert len(meta.attributes) == 1
    assert meta.attributes[0].name == "Нормальный"


def test_parse_tabular_section_missing_props(tmp_path: Path) -> None:
    """TabularSection without Properties is skipped."""
    xml = _make_xml()
    xml = _replace_child_objects(xml, """\
    <md:ChildObjects>
      <md:TabularSection uuid="ts-ok">
        <md:Properties>
          <md:Name>Таблица</md:Name>
        </md:Properties>
      </md:TabularSection>
      <md:TabularSection uuid="ts-bad">
        <md:Comment>no props</md:Comment>
      </md:TabularSection>
    </md:ChildObjects>""")
    fp = tmp_path / "bad_ts.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert len(meta.tabular_sections) == 1
    assert meta.tabular_sections[0].name == "Таблица"


def test_parse_command_missing_props(tmp_path: Path) -> None:
    """Command without Properties is skipped."""
    xml = _make_xml()
    xml = _replace_child_objects(xml, """\
    <md:ChildObjects>
      <md:Command uuid="cmd-ok">
        <md:Properties>
          <md:Name>Команда1</md:Name>
        </md:Properties>
      </md:Command>
      <md:Command uuid="cmd-bad">
        <md:Comment>no props</md:Comment>
      </md:Command>
    </md:ChildObjects>""")
    fp = tmp_path / "bad_cmd.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert len(meta.commands) == 1
    assert meta.commands[0].name == "Команда1"


def test_parse_enum_value_missing_props(tmp_path: Path) -> None:
    """EnumValue without Properties is skipped."""
    xml = _make_xml(type_tag="Enum")
    xml = _replace_child_objects(xml, """\
    <md:ChildObjects>
      <md:EnumValue uuid="ev-ok">
        <md:Properties>
          <md:Name>Новый</md:Name>
        </md:Properties>
      </md:EnumValue>
      <md:EnumValue uuid="ev-bad">
        <md:Comment>no props</md:Comment>
      </md:EnumValue>
    </md:ChildObjects>""")
    fp = tmp_path / "bad_ev.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert len(meta.enum_values) == 1
    assert meta.enum_values[0].name == "Новый"


def test_scan_export_directory_parse_error(tmp_path: Path) -> None:
    """scan_export_directory handles ParseError gracefully."""
    subdir = tmp_path / "Catalogs"
    subdir.mkdir()
    bad = subdir / "bad.xml"
    bad.write_text("not valid xml")
    result = scan_export_directory(tmp_path)
    assert isinstance(result, dict)


def test_parse_object_xml_input_by_string(tmp_path: Path) -> None:
    """InputByString parsing in child objects."""
    xml = _make_xml(props_extra="""
      <md:InputByString>
        <xr:Field>Наименование</xr:Field>
        <xr:Field>Код</xr:Field>
      </md:InputByString>
    """)
    fp = tmp_path / "input_by_string.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert meta.input_by_string == ["Наименование", "Код"]


def test_parse_object_xml_presentations(tmp_path: Path) -> None:
    """ObjectPresentation and ListPresentation are parsed."""
    xml = _make_xml(props_extra="""
      <md:ObjectPresentation>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Объект</v8:content>
        </v8:item>
      </md:ObjectPresentation>
      <md:ListPresentation>
        <v8:item>
          <v8:lang>ru</v8:lang>
          <v8:content>Список</v8:content>
        </v8:item>
      </md:ListPresentation>
    """)
    fp = tmp_path / "presentations.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = parse_object_xml(str(fp))
    assert meta is not None
    assert meta.object_presentation.get("ru") == "Объект"
    assert meta.list_presentation.get("ru") == "Список"


def test_xml_metadata_provider_parse_object_xml(tmp_path: Path) -> None:
    """XmlMetadataProviderImpl delegates to module-level parse."""
    from py1cv8.metadata_xml import XmlMetadataProviderImpl
    xml = _make_xml()
    fp = tmp_path / "provider_test.xml"
    fp.write_text(xml, encoding="utf-8")
    meta = XmlMetadataProviderImpl.parse_object_xml(fp)
    assert meta is not None
    assert meta.name == "ТестовыйСправочник"
