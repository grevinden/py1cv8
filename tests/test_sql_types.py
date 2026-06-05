"""Tests for py1cv8.sql.types — URL validation and database name extraction."""

import pytest

from py1cv8.sql.types import get_db_name, validate_db_url


class TestValidateDbUrl:
    def test_postgresql_canonical(self):
        result = validate_db_url("postgresql://user:pass@host:5432/MyDB")
        assert "postgresql://" in result

    def test_postgres_alias_normalized(self):
        result = validate_db_url("postgres://user:pass@host:5432/MyDB")
        assert result.startswith("postgresql://")
        assert "postgres://" not in result

    def test_mssql_pyodbc_allowed(self):
        result = validate_db_url(
            "mssql+pyodbc://SA:password123@localhost:1433/TestDb?driver=ODBC+Driver+17"
        )
        assert "mssql+pyodbc://" in result

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_db_url("sqlite:///local.db")

    def test_mysql_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_db_url("mysql://root@localhost/db")

    def test_no_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_db_url("just-a-string")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            validate_db_url("")

    def test_missing_database_name_raises(self):
        with pytest.raises(ValueError, match="must include a path"):
            validate_db_url("postgresql://user:pass@host:5432")

    def test_only_host_no_db_raises(self):
        with pytest.raises(ValueError, match="must include a path"):
            validate_db_url("postgresql://localhost/")


class TestGetDbName:
    def test_postgresql_single_segment(self):
        assert get_db_name("postgresql://u:p@h/MyDB") == "MyDB"

    def test_multi_level_path_takes_last(self):
        # 1С sometimes uses nested paths; we take the last segment
        assert get_db_name("postgresql://u:p@h/a/b/c/TargetDb") == "TargetDb"

    def test_mssql_with_query_params(self):
        url = "mssql+pyodbc://SA:pw@host/TestDb?driver=ODBC+Driver+17&charset=UTF8"
        assert get_db_name(url) == "TestDb"

    def test_no_scheme_raises(self):
        with pytest.raises(ValueError, match="Cannot extract"):
            get_db_name("just-text")
