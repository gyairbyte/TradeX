"""Tests for provider lifecycle defaults and premarket routing decoupling."""

import pytest

from tradex.config import (
    DEFAULT_OHLCV_PROVIDER,
    DEFAULT_PROVIDER,
    DataProviderSettings,
    TradeXSettings,
    load_runtime_settings,
    settings_from_mapping,
)
from tradex.data import fetcher
from tradex.data.fetcher import ProviderCapabilityError, resolve_provider
from tradex.premarket.sources import resolve_premarket_provider


def test_central_default_provider_constants():
    """DEFAULT_OHLCV_PROVIDER and DEFAULT_PROVIDER must be 'schwab'."""
    assert DEFAULT_OHLCV_PROVIDER == "schwab"
    assert DEFAULT_PROVIDER == "schwab"
    assert fetcher.DEFAULT_PROVIDER == "schwab"


def test_settings_models_default_to_schwab():
    """Settings models default data_provider to schwab."""
    data_settings = DataProviderSettings()
    assert data_settings.data_provider == "schwab"

    settings = TradeXSettings()
    assert settings.data.data_provider == "schwab"


def test_settings_from_mapping_defaults_to_schwab():
    """settings_from_mapping defaults data_provider to schwab when unset."""
    settings = settings_from_mapping({})
    assert settings.data.data_provider == "schwab"

    # Explicit override honored
    yahoo_settings = settings_from_mapping({"DATA_PROVIDER": "yahoo"})
    assert yahoo_settings.data.data_provider == "yahoo"


def test_load_runtime_settings_defaults_to_schwab(monkeypatch):
    """load_runtime_settings defaults data_provider to schwab when DATA_PROVIDER unset."""
    monkeypatch.delenv("DATA_PROVIDER", raising=False)
    settings = load_runtime_settings(dotenv_path=None)
    assert settings.data.data_provider == "schwab"


def test_resolve_provider_defaults_to_schwab(monkeypatch):
    """resolve_provider defaults to schwab when unset."""
    monkeypatch.delenv("DATA_PROVIDER", raising=False)
    assert resolve_provider() == "schwab"
    assert resolve_provider(None) == "schwab"


def test_resolve_premarket_provider_decoupled_to_yahoo(monkeypatch):
    """resolve_premarket_provider defaults to 'yahoo' even when central default is 'schwab'."""
    monkeypatch.delenv("DATA_PROVIDER", raising=False)
    assert resolve_premarket_provider() == "yahoo"
    assert resolve_premarket_provider(None) == "yahoo"
    assert resolve_premarket_provider("yahoo") == "yahoo"


def test_resolve_premarket_provider_rejects_unsupported():
    """resolve_premarket_provider rejects schwab, alpaca, and ibkr with ProviderCapabilityError."""
    with pytest.raises(ProviderCapabilityError):
        resolve_premarket_provider("schwab")

    with pytest.raises(ProviderCapabilityError):
        resolve_premarket_provider("alpaca")

    with pytest.raises(ProviderCapabilityError):
        resolve_premarket_provider("ibkr")
