"""Data models for 1C metadata XML export."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """Generated 1C type for a metadata object."""

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
    type_name: str
    name: str
    synonym: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    generated_types: list[GeneratedTypeInfo] = field(default_factory=list)

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

    attributes: list[AttributeInfo] = field(default_factory=list)
    tabular_sections: list[TabularSectionInfo] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    commands: list[CommandInfo] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    enum_values: list[EnumValueInfo] = field(default_factory=list)

    object_presentation: dict[str, str] = field(default_factory=dict)
    list_presentation: dict[str, str] = field(default_factory=dict)
    explanation: str = ""
