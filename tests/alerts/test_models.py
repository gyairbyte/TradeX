"""Tests for alert models and configuration."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradex.alerts.models import (
    AlertCooldownConfig,
    AlertDecision,
    AlertDispatchResult,
    AlertKey,
    ensure_aware_utc,
)


class TestAlertKey:
    def test_normalization(self):
        key = AlertKey(ticker="  aapl  ", alert_type=" Coil ", timeframe=" Intraday ")
        assert key.ticker == "AAPL"
        assert key.alert_type == "coil"
        assert key.timeframe == "intraday"
        assert str(key) == "AAPL | coil | intraday"

    def test_empty_ticker_rejected(self):
        with pytest.raises(ValueError, match="ticker must not be empty"):
            AlertKey(ticker="", alert_type="coil", timeframe="intraday")

    def test_empty_alert_type_rejected(self):
        with pytest.raises(ValueError, match="alert_type must not be empty"):
            AlertKey(ticker="AAPL", alert_type="", timeframe="intraday")

    def test_empty_timeframe_rejected(self):
        with pytest.raises(ValueError, match="timeframe must not be empty"):
            AlertKey(ticker="AAPL", alert_type="coil", timeframe="  ")

    def test_control_character_rejected(self):
        with pytest.raises(ValueError, match="control characters"):
            AlertKey(ticker="AAPL\x00", alert_type="coil", timeframe="intraday")

    def test_bounded_length(self):
        with pytest.raises(ValueError, match="exceeds max length"):
            AlertKey(ticker="A" * 81, alert_type="coil", timeframe="intraday")

    def test_coil_timeframe_independence(self):
        k1 = AlertKey("AAPL", "coil", "intraday")
        k2 = AlertKey("AAPL", "coil", "short")
        assert k1 != k2

    def test_pattern_variant_independence(self):
        up = AlertKey("NVDA", "pattern:runup:standard", "pattern")
        down = AlertKey("NVDA", "pattern:decline:standard", "pattern")
        assert up != down

    def test_gap_direction_independence(self):
        up = AlertKey("TSLA", "gap:up", "premarket")
        down = AlertKey("TSLA", "gap:down", "premarket")
        assert up != down

    def test_immutable(self):
        key = AlertKey("AAPL", "coil", "intraday")
        with pytest.raises(FrozenInstanceError):
            key.ticker = "MSFT"


class TestAlertCooldownConfig:
    def test_defaults(self):
        cfg = AlertCooldownConfig()
        assert cfg.enabled is True
        assert cfg.default_minutes == 60
        assert cfg.coil_minutes is None
        assert cfg.confluence_minutes is None
        assert cfg.pattern_minutes is None
        assert cfg.gap_minutes is None
        assert str(cfg.state_path) == "~/.tradex/alerts.db"

    def test_per_type_override(self):
        cfg = AlertCooldownConfig(coil_minutes=120, gap_minutes=15)
        assert cfg.cooldown_minutes_for(AlertKey("X", "coil", "x")) == 120
        assert cfg.cooldown_minutes_for(AlertKey("X", "gap:up", "premarket")) == 15
        assert cfg.cooldown_minutes_for(AlertKey("X", "confluence", "multi")) == 60

    def test_disabled_returns_none(self):
        cfg = AlertCooldownConfig(enabled=False)
        assert cfg.cooldown_minutes_for(AlertKey("X", "coil", "x")) is None

    def test_reject_bool_for_minutes(self):
        with pytest.raises((TypeError, ValueError)):
            AlertCooldownConfig(default_minutes=True)

    def test_reject_numeric_string_constructor(self):
        with pytest.raises(TypeError):
            AlertCooldownConfig(default_minutes="60")

    def test_reject_negative(self):
        with pytest.raises(ValueError, match="positive"):
            AlertCooldownConfig(default_minutes=-1)

    def test_reject_zero(self):
        with pytest.raises(ValueError, match="positive"):
            AlertCooldownConfig(default_minutes=0)

    def test_reject_float(self):
        with pytest.raises(TypeError):
            AlertCooldownConfig(default_minutes=60.5)

    def test_reject_excessive(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            AlertCooldownConfig(default_minutes=8 * 24 * 60)

    def test_env_parsing(self, monkeypatch):
        monkeypatch.setenv("ALERT_COOLDOWN_ENABLED", "false")
        monkeypatch.setenv("ALERT_COOLDOWN_MINUTES", "90")
        monkeypatch.setenv("ALERT_COIL_COOLDOWN_MINUTES", "30")
        monkeypatch.setenv("ALERT_STATE_PATH", "~/.tradex/test_alerts.db")
        cfg = AlertCooldownConfig.from_env()
        assert cfg.enabled is False
        assert cfg.default_minutes == 90
        assert cfg.coil_minutes == 30
        assert str(cfg.state_path) == "~/.tradex/test_alerts.db"

    def test_env_rejects_empty_override(self, monkeypatch):
        monkeypatch.setenv("ALERT_COIL_COOLDOWN_MINUTES", "")
        with pytest.raises(ValueError, match="empty"):
            AlertCooldownConfig.from_env()

    def test_env_rejects_boolean_string_for_minutes(self, monkeypatch):
        monkeypatch.setenv("ALERT_COOLDOWN_MINUTES", "true")
        with pytest.raises(ValueError):
            AlertCooldownConfig.from_env()

    def test_env_rejects_fraction(self, monkeypatch):
        monkeypatch.setenv("ALERT_COOLDOWN_MINUTES", "60.5")
        with pytest.raises(ValueError):
            AlertCooldownConfig.from_env()

    def test_path_expansion_deferred(self):
        cfg = AlertCooldownConfig(state_path=Path("~/.tradex/alerts.db"))
        assert "~" in str(cfg.state_path)
        assert "~" not in str(cfg.resolved_state_path)

    def test_state_path_default_is_path(self):
        cfg = AlertCooldownConfig()
        assert isinstance(cfg.state_path, Path)


class TestAlertDispatchResult:
    def test_json_safe(self):
        key = AlertKey("AAPL", "coil", "intraday")
        result = AlertDispatchResult(
            key=key,
            decision=AlertDecision.SENT,
            observed_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            cooldown_minutes=60,
            last_success_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            next_eligible_at=datetime(2024, 1, 1, 13, 0, tzinfo=UTC),
            reason="sent",
            channel_results={"discord": True, "email": False},
        )
        d = result.to_dict()
        assert d["decision"] == "sent"
        assert d["channel_results"] == {"discord": True, "email": False}
        assert "NaN" not in result.to_json()

    def test_channel_results_sorted(self):
        result = AlertDispatchResult(
            key=AlertKey("A", "coil", "x"),
            decision=AlertDecision.SENT,
            observed_at=datetime.now(UTC),
            cooldown_minutes=60,
            last_success_at=None,
            next_eligible_at=None,
            reason="",
            channel_results={"email": True, "discord": True},
        )
        assert list(result.channel_results.keys()) == ["discord", "email"]


class TestEnsureAwareUtc:
    def test_rejects_naive(self):
        with pytest.raises(ValueError, match="naive"):
            ensure_aware_utc(datetime(2024, 1, 1, 12, 0))  # noqa: DTZ001

    def test_defaults_to_now(self):
        dt = ensure_aware_utc(None)
        assert dt.tzinfo is UTC

    def test_converts_to_utc(self):
        from zoneinfo import ZoneInfo
        dt = ensure_aware_utc(datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("America/New_York")))
        assert dt.tzinfo is UTC
