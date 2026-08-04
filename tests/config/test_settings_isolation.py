"""Settings-isolation matrix tests for the centralized configuration boundary."""
from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

import pandas as pd
import pytest

from tradex.alerts.notifier import is_alert_configured
from tradex.config import (
    TradeXSettings,
    load_runtime_settings,
    settings_from_mapping,
)
from tradex.data.fetcher import resolve_provider
from tradex.options.flow import resolve_chain_source, resolve_flow_source
from tradex.tracker import store


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
        "ALERT_EMAIL_PASS": "email-password",
    })
    summary = settings.safe_summary()
    text = str(summary) + repr(settings)
    assert "super-secret-discord-token" not in text
    assert "whales-api-key-123" not in text
    assert "tradier-api-key-456" not in text
    assert "schwab-app-secret" not in text
    assert "email-password" not in text


def _signal_results(ticker: str, score: int) -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": ticker,
        "score": score,
        "last_close": 100.0,
        "volume_ratio": 1.5,
        "rsi": 55.0,
        "days_until_earnings": None,
        "reasons": ["test"],
        "provider": "yahoo",
    }])


def test_signal_store_A_to_B_to_A_isolation(tmp_path):
    """Two explicit settings objects write to distinct signal DBs without cross-contamination."""
    from datetime import datetime

    a_db = tmp_path / "a_signals.db"
    b_db = tmp_path / "b_signals.db"
    settings_a = settings_from_mapping({"TRADEX_DB_PATH": str(a_db)})
    settings_b = settings_from_mapping({"TRADEX_DB_PATH": str(b_db)})

    store.init(settings=settings_a)
    store.init(settings=settings_b)

    now = datetime.now(UTC)
    results_a = _signal_results("AAPL", 70)
    results_b = _signal_results("MSFT", 65)

    store.record_signals(results_a, "intraday", tickers_scanned=["AAPL"], scan_time=now, settings=settings_a)
    store.record_signals(results_b, "intraday", tickers_scanned=["MSFT"], scan_time=now, settings=settings_b)
    store.record_signals(results_a, "intraday", tickers_scanned=["AAPL"], scan_time=now, settings=settings_a)

    history_a = store.get_history("AAPL", "intraday", settings=settings_a)
    history_b = store.get_history("MSFT", "intraday", settings=settings_b)

    assert len(history_a) == 2
    assert set(history_a["ticker"]) == {"AAPL"}
    assert len(history_b) == 1
    assert set(history_b["ticker"]) == {"MSFT"}


def test_watchlist_store_A_to_B_to_A_isolation(tmp_path):
    """Explicit settings objects write watchlists to distinct DBs without leakage."""
    from tradex.watchlists import store as wl_store

    a_db = tmp_path / "a_watchlists.db"
    b_db = tmp_path / "b_watchlists.db"
    settings_a = settings_from_mapping({"TRADEX_WATCHLISTS_DB_PATH": str(a_db)})
    settings_b = settings_from_mapping({"TRADEX_WATCHLISTS_DB_PATH": str(b_db)})

    wl_store.init(settings=settings_a)
    wl_store.init(settings=settings_b)

    wl_store.save("a", ["AAPL"], settings=settings_a)
    wl_store.save("b", ["MSFT"], settings=settings_b)
    wl_store.save("a2", ["NVDA"], settings=settings_a)

    all_a = wl_store.list_all(settings=settings_a)

    assert {w["name"] for w in all_a} == {"a", "a2"}
    assert wl_store.load("b", settings=settings_b) == ["MSFT"]
    assert wl_store.load("a2", settings=settings_a) == ["NVDA"]


def test_fingerprint_store_A_to_B_to_A_isolation(tmp_path):
    """Fingerprint persistence respects explicit settings DB paths."""
    import pandas as pd

    from tradex.patterns import fingerprint
    from tradex.patterns.config import PatternConfig

    a_db = tmp_path / "a_fingerprints.db"
    b_db = tmp_path / "b_fingerprints.db"
    settings_a = settings_from_mapping({"TRADEX_FP_DB": str(a_db)})
    settings_b = settings_from_mapping({"TRADEX_FP_DB": str(b_db)})

    cfg = PatternConfig(min_events=1, lookback_days=3)
    series = [0.0, 0.0, 0.0]
    events = pd.DataFrame([
        {"event_type": "runup", "event_date": "2024-01-01", "price_pct": series},
        {"event_type": "runup", "event_date": "2024-01-02", "price_pct": series},
    ])

    fp_a = fingerprint.build_fingerprint(events, "runup", cfg=cfg, source="yahoo", settings=settings_a)
    fp_b = fingerprint.build_fingerprint(events, "runup", cfg=cfg, source="yahoo", settings=settings_b)

    assert fp_a is not None
    assert fp_b is not None

    assert len(fingerprint.list_fingerprints(settings=settings_a)) == 1
    assert len(fingerprint.list_fingerprints(settings=settings_b)) == 1
    # A second write to A should not appear in B.
    fingerprint.build_fingerprint(events, "runup", cfg=cfg, source="yahoo", settings=settings_a)
    assert len(fingerprint.list_fingerprints(settings=settings_a)) == 1
    assert len(fingerprint.list_fingerprints(settings=settings_b)) == 1


def test_earnings_cache_A_to_B_to_A_isolation(tmp_path):
    """Earnings cache reads/writes are isolated by settings path."""
    from datetime import date

    from tradex.earnings import calendar as earnings

    a_db = tmp_path / "a_earnings.db"
    b_db = tmp_path / "b_earnings.db"
    settings_a = settings_from_mapping({"TRADEX_EARNINGS_CACHE_PATH": str(a_db)})
    settings_b = settings_from_mapping({"TRADEX_EARNINGS_CACHE_PATH": str(b_db)})

    date_a = date(2024, 1, 15)
    date_b = date(2024, 2, 20)

    earnings._cache_put("AAPL", "yahoo", date_a, settings=settings_a)
    earnings._cache_put("AAPL", "yahoo", date_b, settings=settings_b)

    assert earnings._cache_get("AAPL", "yahoo", settings=settings_a)[0] == date_a
    assert earnings._cache_get("AAPL", "yahoo", settings=settings_b)[0] == date_b

    # A repeat write to A must not change B.
    earnings._cache_put("AAPL", "yahoo", date_a, settings=settings_a)
    assert earnings._cache_get("AAPL", "yahoo", settings=settings_b)[0] == date_b


def test_schwab_client_cache_isolation_with_mocked_auth(tmp_path, monkeypatch):
    """Two distinct Schwab credential sets create two cached clients; identical settings reuse one."""
    import os
    import types
    from unittest.mock import MagicMock

    from tradex.data import fetcher

    # Build a minimal fake schwab package so the function under test can import
    # client_from_token_file without real credentials or network. Force these
    # entries into sys.modules so any prior real schwab import is overridden.
    fake_schwab = types.ModuleType("schwab")
    fake_auth = types.ModuleType("schwab.auth")
    mock_factory = MagicMock()
    mock_factory.side_effect = [MagicMock(), MagicMock()]
    fake_auth.client_from_token_file = mock_factory
    fake_schwab.auth = fake_auth
    monkeypatch.setitem(sys.modules, "schwab", fake_schwab)
    monkeypatch.setitem(sys.modules, "schwab.auth", fake_auth)
    fetcher._SCHWAB_CLIENTS.clear()

    token_a = tmp_path / "token_a.json"
    token_b = tmp_path / "token_b.json"
    token_a.write_text("{}")
    token_b.write_text("{}")

    # Ensure token paths are treated as existing without actually validating them.
    real_exists = os.path.exists
    def _exists(path):
        if str(path) in (str(token_a), str(token_b)):
            return True
        return real_exists(path)
    monkeypatch.setattr(os.path, "exists", _exists)

    settings_a = settings_from_mapping({
        "SCHWAB_TOKEN_PATH": str(token_a),
        "SCHWAB_APP_KEY": "key-a",
        "SCHWAB_APP_SECRET": "secret-a",
    })
    settings_b = settings_from_mapping({
        "SCHWAB_TOKEN_PATH": str(token_b),
        "SCHWAB_APP_KEY": "key-b",
        "SCHWAB_APP_SECRET": "secret-b",
    })

    client_a = fetcher._get_schwab_client(settings=settings_a)
    client_a_again = fetcher._get_schwab_client(settings=settings_a)
    client_b = fetcher._get_schwab_client(settings=settings_b)

    assert client_a is client_a_again
    assert client_a is not client_b
    assert mock_factory.call_count == 2
    keys = {mock_factory.call_args_list[i].kwargs["api_key"] for i in range(2)}
    assert keys == {"key-a", "key-b"}


def test_load_runtime_settings_precedence_and_parser_matrix(tmp_path, monkeypatch):
    """dotenv values are overridden by process env; invalid values raise without leaking secrets."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATA_PROVIDER=yahoo\n"
        "OHLCV_MAX_RETRIES=1\n"
        "ALERT_COIL_THRESHOLD=75\n"
        "ALERT_EMAIL_PASS=file-secret\n"
    )

    monkeypatch.setenv("OHLCV_MAX_RETRIES", "2")
    monkeypatch.setenv("ALERT_EMAIL_PASS", "env-secret")

    settings = load_runtime_settings(dotenv_path=env_file)

    assert settings.data.data_provider == "yahoo"
    assert settings.data.ohlcv_max_retries == 2
    assert settings.alert_thresholds.coil == 75
    assert settings.alert_channels.email_pass == "env-secret"

    summary = settings.safe_summary()
    assert "env-secret" not in str(summary)
    assert "file-secret" not in str(summary)

    monkeypatch.setenv("ALERT_COIL_THRESHOLD", "not-a-number")
    with pytest.raises(ValueError, match="ALERT_COIL_THRESHOLD"):
        load_runtime_settings()
