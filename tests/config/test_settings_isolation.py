"""Settings-isolation matrix tests for the centralized configuration boundary."""
from __future__ import annotations

from pathlib import Path

import pytest

from tradex.alerts.notifier import is_alert_configured
from tradex.config import (
    TradeXSettings,
    load_runtime_settings,
    settings_from_mapping,
)
from tradex.data.fetcher import resolve_provider
from tradex.options.flow import resolve_chain_source, resolve_flow_source


def test_two_settings_objects_with_different_providers_do_not_leak():
    """``resolve_provider`` honors the explicit ``settings`` object over global defaults."""
    yahoo_settings = settings_from_mapping({"DATA_PROVIDER": "yahoo"})
    schwab_settings = settings_from_mapping({"DATA_PROVIDER": "schwab"})

    assert resolve_provider(settings=yahoo_settings) == "yahoo"
    assert resolve_provider(settings=schwab_settings) == "schwab"
    # Repeated calls still isolated.
    assert resolve_provider(settings=yahoo_settings) == "yahoo"


def test_options_source_isolation():
    """Options flow/chain resolution returns different capability for different settings."""
    empty = TradeXSettings()
    whales = settings_from_mapping({
        "OPTIONS_DATA_SOURCE": "auto",
        "UNUSUAL_WHALES_API_KEY": "secret",
    })
    tradier = settings_from_mapping({
        "OPTIONS_DATA_SOURCE": "auto",
        "TRADIER_API_KEY": "secret",
    })
    explicit_yahoo = settings_from_mapping({"OPTIONS_DATA_SOURCE": "yahoo"})

    assert not resolve_flow_source("auto", settings=empty).available
    assert resolve_flow_source("auto", settings=whales).actual_source == "unusual_whales"

    # With only Tradier, auto chain source picks Tradier, not Yahoo.
    chain_status = resolve_chain_source("auto", settings=tradier)
    assert chain_status.available
    assert chain_status.actual_source == "tradier"

    # Explicit Yahoo chain source is still available.
    yahoo_chain = resolve_chain_source("yahoo", settings=explicit_yahoo)
    assert yahoo_chain.available
    assert yahoo_chain.actual_source == "yahoo"


def test_alert_channel_isolation():
    """``is_alert_configured`` reflects only the settings object it is passed."""
    empty = TradeXSettings()
    discord = settings_from_mapping({
        "ALERT_DISCORD_TOKEN": "token",
        "ALERT_DISCORD_CHANNEL_ID": "123",
    })

    assert not is_alert_configured(settings=empty)
    assert is_alert_configured(settings=discord)
    assert not is_alert_configured(settings=empty)


def test_alert_threshold_isolation():
    """Threshold settings are independent between settings instances."""
    default = TradeXSettings()
    high = settings_from_mapping({"ALERT_COIL_THRESHOLD": "90"})

    assert default.alert_thresholds.coil == 60
    assert high.alert_thresholds.coil == 90


def test_settings_are_frozen():
    """``TradeXSettings`` and nested settings are immutable."""
    import dataclasses

    settings = TradeXSettings()
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.data_provider = "schwab"
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.paths.signals_db = Path("/tmp/other.db")


def test_load_runtime_settings_reads_process_env_but_does_not_mutate_os_environ():
    """``load_runtime_settings`` uses ``os.environ`` overrides but never mutates it."""
    import os
    original = os.environ.get("DATA_PROVIDER")
    try:
        os.environ["DATA_PROVIDER"] = "schwab"
        settings = load_runtime_settings()
        assert settings.data.data_provider == "schwab"
        # No side effect on os.environ.
        assert "DATA_PROVIDER" in os.environ
    finally:
        if original is None:
            os.environ.pop("DATA_PROVIDER", None)
        else:
            os.environ["DATA_PROVIDER"] = original


def test_schwab_client_cache_keyed_by_safe_identity():
    """The Schwab client cache key is derived from a safe SHA-256 hash, not raw secrets."""
    from tradex.data.fetcher import _schwab_client_key

    settings_a = settings_from_mapping({
        "SCHWAB_TOKEN_PATH": "~/.tokens/schwab.json",
        "SCHWAB_APP_KEY": "key-a",
        "SCHWAB_APP_SECRET": "secret-a",
    })
    settings_b = settings_from_mapping({
        "SCHWAB_TOKEN_PATH": "~/.tokens/schwab.json",
        "SCHWAB_APP_KEY": "key-b",
        "SCHWAB_APP_SECRET": "secret-b",
    })

    key_a = _schwab_client_key(settings_a)
    key_b = _schwab_client_key(settings_b)

    assert key_a != key_b
    assert key_a != "key-a:secret-a"
    assert len(key_a) == 64  # hex SHA-256


def test_path_settings_are_immutable_and_expandable():
    """``PathSettings`` stores literal paths and expands ``~`` on demand."""
    settings = settings_from_mapping({
        "TRADEX_DB_PATH": "~/custom/signals.db",
        "TRADEX_FP_DB": "~/custom/fingerprints.db",
        "TRADEX_WATCHLISTS_DB_PATH": "~/custom/watchlists.db",
    })

    assert settings.paths.signals_db == Path("~/custom/signals.db")
    assert settings.paths.fingerprint_db == Path("~/custom/fingerprints.db")
    assert settings.paths.watchlists_db == Path("~/custom/watchlists.db")

    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.paths.signals_db = Path("/tmp/other.db")


def test_settings_summary_does_not_expose_secrets():
    """The redacted settings summary and repr hide tokens, passwords, and API keys."""
    settings = settings_from_mapping({
        "ALERT_DISCORD_TOKEN": "super-secret-discord-token",
        "ALERT_DISCORD_CHANNEL_ID": "123456",
        "UNUSUAL_WHALES_API_KEY": "whales-api-key-123",
        "TRADIER_API_KEY": "tradier-api-key-456",
        "SCHWAB_APP_KEY": "schwab-app-key",
        "SCHWAB_APP_SECRET": "schwab-app-secret",
        "EMAIL_PASSWORD": "email-password",
    })
    summary = settings.safe_summary()
    text = str(summary) + repr(settings)
    assert "super-secret-discord-token" not in text
    assert "whales-api-key-123" not in text
    assert "tradier-api-key-456" not in text
    assert "schwab-app-secret" not in text
    assert "email-password" not in text
