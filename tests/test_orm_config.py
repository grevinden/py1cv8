"""Tests for py1cv8.sql.orm.config_queries — model resolution and type safety."""

from typing import cast

import pytest

from py1cv8.sql.orm import ConfigTable
from py1cv8.sql.orm.config_queries import _resolve_model
from py1cv8.sql.orm.models import Config, ConfigCas


class TestResolveModel:
    def test_config_returns_config_model(self):
        result = _resolve_model("config")
        assert result is Config

    def test_configcas_returns_configcas_model(self):
        result = _resolve_model("configcas")
        assert result is ConfigCas

    def test_unknown_table_raises(self):
        with pytest.raises(ValueError, match="Unknown table"):
            # Literal not enforced at runtime — test the ValueError path
            _resolve_model(cast(ConfigTable, "params"))

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unknown table"):
            _resolve_model(cast(ConfigTable, ""))


class TestConfigQueriesValidateUrlIntegration:
    """Test that select_config_rows validates URL before querying."""

    @pytest.mark.asyncio
    async def test_invalid_url_raises_before_session(self):
        from py1cv8.sql.orm.config_queries import select_config_rows

        with pytest.raises(ValueError, match="Unsupported"):
            await select_config_rows("sqlite:///test.db")
