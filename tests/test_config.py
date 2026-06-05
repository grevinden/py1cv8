"""Tests for config.py — constants and type maps."""

from __future__ import annotations

from py1cv8.dbnames import (
    COMPANION_TABLE_PARENT,
    COMPANION_TABLE_TYPES,
    MAIN_TABLE_TYPES,
    SERVICE_TABLE_TYPES,
    SUB_TABLE_PARENT,
    SUB_TABLE_TYPES,
)
from py1cv8.metadata_binary import TYPE_MAP


def test_type_map_has_known_types() -> None:
    """TYPE_MAP contains critical type mappings."""
    assert TYPE_MAP[0] == "CommonForms"
    assert TYPE_MAP[2] == "CommonModules"
    assert TYPE_MAP[5] == "CommonAttributes"
    assert TYPE_MAP[16] == "Constants"
    assert TYPE_MAP[20] == "Enums"
    assert TYPE_MAP[22] == "Documents"
    assert TYPE_MAP[26] == "DocumentJournals"
    assert TYPE_MAP[33] == "InformationRegisters"
    assert TYPE_MAP[34] == "ChartsOfCharacteristicTypes"
    assert TYPE_MAP[57] == "Catalogs"


def test_type_map_documents() -> None:
    """Documents has multiple type_nums."""
    assert TYPE_MAP[22] == "Documents"
    assert TYPE_MAP[40] == "Documents"


def test_type_map_data_processors() -> None:
    """DataProcessors has multiple type_nums."""
    assert TYPE_MAP[1] == "DataProcessors"
    assert TYPE_MAP[4] == "DataProcessors"
    assert TYPE_MAP[17] == "DataProcessors"
    assert TYPE_MAP[19] == "DataProcessors"


def test_type_map_roles() -> None:
    """Roles has multiple type_nums."""
    assert TYPE_MAP[6] == "Roles"
    assert TYPE_MAP[7] == "Roles"


def test_type_map_other_types() -> None:
    """Remaining OtherTypes placeholders."""
    assert TYPE_MAP[13] == "OtherTypes"
    assert TYPE_MAP[14] == "OtherTypes"
    assert TYPE_MAP[30] == "OtherTypes"
    assert TYPE_MAP[37] == "OtherTypes"


def test_sub_table_types() -> None:
    """SUB_TABLE_TYPES contains expected types."""
    assert "VT" in SUB_TABLE_TYPES
    assert "Fld" in SUB_TABLE_TYPES
    assert "BPrPoints" in SUB_TABLE_TYPES
    assert "Node" in SUB_TABLE_TYPES


def test_sub_table_parent() -> None:
    """SUB_TABLE_PARENT maps sub-types to parents."""
    assert SUB_TABLE_PARENT["VT"] == "Reference"
    assert SUB_TABLE_PARENT["Fld"] == "Reference"
    assert SUB_TABLE_PARENT["BPr"] == "BusinessProcess"
    assert SUB_TABLE_PARENT["Node"] == "ExchangePlan"


def test_companion_table_types() -> None:
    """COMPANION_TABLE_TYPES contains expected types."""
    assert "ChrcSInf" in COMPANION_TABLE_TYPES
    assert "IntegServiceSettings" in COMPANION_TABLE_TYPES


def test_companion_table_parent() -> None:
    """COMPANION_TABLE_PARENT maps types to parents."""
    assert COMPANION_TABLE_PARENT["ChrcSInf"] == "Chrc"
    assert COMPANION_TABLE_PARENT["IntegServiceSettings"] == "IntegrationService"


def test_main_table_types() -> None:
    """MAIN_TABLE_TYPES contains core table types."""
    assert "Reference" in MAIN_TABLE_TYPES
    assert "Document" in MAIN_TABLE_TYPES
    assert "InfoRg" in MAIN_TABLE_TYPES
    assert "Enum" in MAIN_TABLE_TYPES
    assert "Const" in MAIN_TABLE_TYPES


def test_service_table_types() -> None:
    """SERVICE_TABLE_TYPES contains expected types."""
    assert "SystemSettings" in SERVICE_TABLE_TYPES
    assert "YearOffset" in SERVICE_TABLE_TYPES
    assert "Consts" in SERVICE_TABLE_TYPES
    assert "ExtDataSrcPrms" in SERVICE_TABLE_TYPES
    assert "WebSocketClients" in SERVICE_TABLE_TYPES
    assert "DataHistoryLatestVerExt" in SERVICE_TABLE_TYPES
    assert "DataHistoryMetadataExt" in SERVICE_TABLE_TYPES
    assert "DataHistorySettingsExt" in SERVICE_TABLE_TYPES
    assert "DataHistoryVersionsExt" in SERVICE_TABLE_TYPES


def test_sub_table_types_is_frozenset() -> None:
    """SUB_TABLE_TYPES is a frozenset (immutable)."""
    assert isinstance(SUB_TABLE_TYPES, frozenset)


def test_main_table_types_is_frozenset() -> None:
    """MAIN_TABLE_TYPES is a frozenset."""
    assert isinstance(MAIN_TABLE_TYPES, frozenset)
