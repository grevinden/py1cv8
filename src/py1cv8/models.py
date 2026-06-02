"""SQLAlchemy ORM models for 1C PostgreSQL database tables.

All models use the SQLAlchemy 2.0 Mapped annotation style.
"""

from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Config(Base):
    """1C config table — stores compressed metadata blobs."""

    __tablename__ = "config"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    partno: Mapped[int] = mapped_column(Integer, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class ConfigCas(Base):
    """1C configcas table — cached metadata with SHA-1 filenames."""

    __tablename__ = "configcas"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    partno: Mapped[int] = mapped_column(Integer, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Params(Base):
    """1C params table — stores DBNames and configuration parameters."""

    __tablename__ = "params"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


# ── PostgreSQL system information_schema views (read-only) ──────────────


class InformationSchemaColumn(Base):
    """PostgreSQL information_schema.columns — column metadata."""

    __tablename__ = "columns"
    __table_args__ = {"schema": "information_schema"}

    table_catalog: Mapped[str | None] = mapped_column(String, nullable=True)
    table_schema: Mapped[str | None] = mapped_column(String, nullable=True)
    table_name: Mapped[str] = mapped_column(String, primary_key=True)
    column_name: Mapped[str] = mapped_column(String, primary_key=True)
    ordinal_position: Mapped[int] = mapped_column(Integer)
    is_nullable: Mapped[str | None] = mapped_column(String, nullable=True)
    data_type: Mapped[str | None] = mapped_column(String, nullable=True)
    character_maximum_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numeric_precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numeric_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    udt_name: Mapped[str | None] = mapped_column(String, nullable=True)


class InformationSchemaTableConstraint(Base):
    """PostgreSQL information_schema.table_constraints."""

    __tablename__ = "table_constraints"
    __table_args__ = {"schema": "information_schema"}

    constraint_catalog: Mapped[str] = mapped_column(String, primary_key=True)
    constraint_schema: Mapped[str] = mapped_column(String, primary_key=True)
    constraint_name: Mapped[str] = mapped_column(String, primary_key=True)
    table_catalog: Mapped[str | None] = mapped_column(String, nullable=True)
    table_schema: Mapped[str | None] = mapped_column(String, nullable=True)
    table_name: Mapped[str] = mapped_column(String)
    constraint_type: Mapped[str] = mapped_column(String)


class InformationSchemaKeyColumnUsage(Base):
    """PostgreSQL information_schema.key_column_usage."""

    __tablename__ = "key_column_usage"
    __table_args__ = {"schema": "information_schema"}

    constraint_catalog: Mapped[str] = mapped_column(String, primary_key=True)
    constraint_schema: Mapped[str] = mapped_column(String, primary_key=True)
    constraint_name: Mapped[str] = mapped_column(String, primary_key=True)
    table_catalog: Mapped[str | None] = mapped_column(String, nullable=True)
    table_schema: Mapped[str | None] = mapped_column(String, nullable=True)
    table_name: Mapped[str] = mapped_column(String, primary_key=True)
    column_name: Mapped[str] = mapped_column(String, primary_key=True)
    ordinal_position: Mapped[int] = mapped_column(Integer, primary_key=True)
