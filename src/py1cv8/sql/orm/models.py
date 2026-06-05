"""SQLAlchemy ORM models for 1C PostgreSQL database tables.

Все модели используют стиль аннотаций SQLAlchemy 2.0 (Mapped).
"""

from __future__ import annotations

from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей 1С."""

    pass


class Config(Base):
    """Таблица ``config`` — хранит сжатые блобы метаданных."""

    __tablename__ = "config"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    partno: Mapped[int] = mapped_column(Integer, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class ConfigCas(Base):
    """Таблица ``configcas`` — кэш метаданных с SHA-1 именами файлов."""

    __tablename__ = "configcas"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    partno: Mapped[int] = mapped_column(Integer, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class Params(Base):
    """Таблица ``params`` — хранит DBNames и параметры конфигурации."""

    __tablename__ = "params"

    filename: Mapped[str] = mapped_column(String, primary_key=True)
    binarydata: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


# ── PostgreSQL system information_schema views (read-only) ──────────────


class InformationSchemaColumn(Base):
    """PostgreSQL ``information_schema.columns`` — метаданные колонок."""

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
    """PostgreSQL ``information_schema.table_constraints``."""

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
    """PostgreSQL ``information_schema.key_column_usage``."""

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
