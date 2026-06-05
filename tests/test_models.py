"""Tests for models.py — SQLAlchemy ORM models."""

from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String

from py1cv8.sql.orm.models import (
    Base,
    Config,
    ConfigCas,
    InformationSchemaColumn,
    InformationSchemaKeyColumnUsage,
    InformationSchemaTableConstraint,
    Params,
)


def test_base_is_declarative() -> None:
    """Base is a DeclarativeBase."""
    assert hasattr(Base, "metadata")
    assert hasattr(Base, "registry")


def test_config_model() -> None:
    """Config model has correct tablename and columns."""
    assert Config.__tablename__ == "config"
    cols = {c.name: c for c in Config.__table__.columns}
    assert "filename" in cols
    assert "partno" in cols
    assert "binarydata" in cols
    assert cols["filename"].primary_key
    assert cols["partno"].primary_key


def test_configcas_model() -> None:
    """ConfigCas model has correct tablename and columns."""
    assert ConfigCas.__tablename__ == "configcas"
    cols = {c.name: c for c in ConfigCas.__table__.columns}
    assert "filename" in cols
    assert "partno" in cols
    assert "binarydata" in cols
    assert cols["filename"].primary_key
    assert cols["partno"].primary_key


def test_params_model() -> None:
    """Params model has correct tablename and columns."""
    assert Params.__tablename__ == "params"
    cols = {c.name: c for c in Params.__table__.columns}
    assert "filename" in cols
    assert "binarydata" in cols
    assert cols["filename"].primary_key


def test_information_schema_column_model() -> None:
    """InformationSchemaColumn has correct schema and columns."""
    assert InformationSchemaColumn.__tablename__ == "columns"
    assert InformationSchemaColumn.__table_args__ == {"schema": "information_schema"}
    cols = {c.name: c for c in InformationSchemaColumn.__table__.columns}
    assert "table_name" in cols
    assert "column_name" in cols
    assert "data_type" in cols
    assert "is_nullable" in cols
    assert "ordinal_position" in cols
    assert cols["table_name"].primary_key
    assert cols["column_name"].primary_key


def test_information_schema_table_constraint_model() -> None:
    """InformationSchemaTableConstraint has correct schema."""
    assert InformationSchemaTableConstraint.__tablename__ == "table_constraints"
    assert InformationSchemaTableConstraint.__table_args__ == {"schema": "information_schema"}
    cols = {c.name: c for c in InformationSchemaTableConstraint.__table__.columns}
    assert "constraint_name" in cols
    assert "constraint_type" in cols
    assert "table_name" in cols


def test_information_schema_key_column_usage_model() -> None:
    """InformationSchemaKeyColumnUsage has correct columns."""
    assert InformationSchemaKeyColumnUsage.__tablename__ == "key_column_usage"
    assert InformationSchemaKeyColumnUsage.__table_args__ == {"schema": "information_schema"}
    cols = {c.name: c for c in InformationSchemaKeyColumnUsage.__table__.columns}
    assert "column_name" in cols
    assert "constraint_name" in cols
    assert "table_name" in cols


def test_model_column_types() -> None:
    """Model columns use correct SA types."""
    config_fname = Config.__table__.columns["filename"]
    assert isinstance(config_fname.type, String)

    config_partno = Config.__table__.columns["partno"]
    assert isinstance(config_partno.type, Integer)

    config_data = Config.__table__.columns["binarydata"]
    assert isinstance(config_data.type, LargeBinary)


def test_config_instantiation() -> None:
    """Config model can be instantiated."""
    c = Config(filename="test.txt", partno=1, binarydata=b"hello")
    assert c.filename == "test.txt"
    assert c.partno == 1
    assert c.binarydata == b"hello"


def test_params_instantiation() -> None:
    """Params model can be instantiated with nullable binarydata."""
    p = Params(filename="params.bin")
    assert p.filename == "params.bin"
    assert p.binarydata is None

    p2 = Params(filename="params.bin", binarydata=b"\x00\x01")
    assert p2.binarydata == b"\x00\x01"
