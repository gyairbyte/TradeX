"""Tests for the typed alert helpers and raw send_alert transport."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from tradex.alerts.models import AlertDecision
from tradex.alerts.notifier import (
    COIL_ALERT_THRESHOLD,
    CONFLUENCE_ALERT_THRESHOLD,
    PATTERN_ALERT_THRESHOLD,
    alert_coil,
    alert_confluence,
    alert_gap,
    alert_pattern_match,
    is_alert_configured,
    send_alert,
)
from tradex.alerts.policy import AlertPolicy
from tradex.alerts.store import AlertStore


class TestSendAlert:
    def test_returns_channel_map(self):
        with (
            patch("tradex.alerts.notifier._send_discord", return_value=False),
            patch("tradex.alerts.notifier._send_email", return_value=False),
        ):
            results = send_alert("subj", "body")
        assert isinstance(results, dict)
        assert "discord" in results
        assert "email" in results

    def test_is_alert_configured_false_without_env(self, monkeypatch):
        from tradex import alerts as alerts_module

        monkeypatch.setattr(alerts_module.notifier, "DISCORD_TOKEN", "")
        monkeypatch.setattr(alerts_module.notifier, "DISCORD_CHANNEL_ID", "")
        monkeypatch.setattr(alerts_module.notifier, "EMAIL_TO", "")
        monkeypatch.setattr(alerts_module.notifier, "EMAIL_FROM", "")
        monkeypatch.setattr(alerts_module.notifier, "EMAIL_HOST", "")
        monkeypatch.setattr(alerts_module.notifier, "EMAIL_USER", "")
        monkeypatch.setattr(alerts_module.notifier, "EMAIL_PASS", "")
        assert is_alert_configured() is False

    def test_is_alert_configured_true_with_discord(self, monkeypatch):
        from tradex import alerts as alerts_module

        monkeypatch.setattr(alerts_module.notifier, "DISCORD_TOKEN", "token")
        monkeypatch.setattr(alerts_module.notifier, "DISCORD_CHANNEL_ID", "123")
        assert is_alert_configured() is True


class TestAlertCoil:
    def test_below_threshold(self):
        result = alert_coil("AAPL", COIL_ALERT_THRESHOLD - 1, 50, "up", "intraday")
        assert result.decision == AlertDecision.BELOW_THRESHOLD

    def test_exact_threshold_sends(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SENT)
        alert_coil("AAPL", COIL_ALERT_THRESHOLD, 50, "up", "intraday", policy=mock_policy)
        mock_policy.dispatch.assert_called_once()

    def test_above_threshold_sends(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SENT)
        alert_coil("AAPL", COIL_ALERT_THRESHOLD + 5, 50, "up", "intraday", policy=mock_policy)
        mock_policy.dispatch.assert_called_once()

    def test_same_ticker_timeframe_suppresses(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_coil("AAPL", 70, 50, "up", "intraday", policy=policy, observed_at=now)
        r2 = alert_coil("AAPL", 70, 50, "up", "intraday", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SUPPRESSED_COOLDOWN

    def test_different_timeframe_does_not_collide(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_coil("AAPL", 70, 50, "up", "intraday", policy=policy, observed_at=now)
        r2 = alert_coil("AAPL", 70, 50, "up", "short", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_subject_body_compatible(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        alert_coil("AAPL", 70, 50, "up", "intraday", policy=mock_policy)
        args = mock_policy.dispatch.call_args
        assert "AAPL" in args.args[1]
        assert "Coil strength: 70" in args.args[2]


class TestAlertConfluence:
    def test_below_threshold(self):
        result = alert_confluence("AAPL", CONFLUENCE_ALERT_THRESHOLD - 1, ["intraday"], 100.0)
        assert result.decision == AlertDecision.BELOW_THRESHOLD

    def test_exact_threshold_sends(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SENT)
        alert_confluence(
            "AAPL", CONFLUENCE_ALERT_THRESHOLD, ["intraday", "short"], 100.0, policy=mock_policy
        )
        mock_policy.dispatch.assert_called_once()

    def test_uses_multi_timeframe_identity(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_confluence("AAPL", 75, ["intraday"], 100.0, policy=policy, observed_at=now)
        r2 = alert_confluence("AAPL", 75, ["intraday", "short"], 100.0, policy=policy, observed_at=now)
        # Same confluence key; second should be suppressed.
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SUPPRESSED_COOLDOWN


class TestAlertPattern:
    def test_below_threshold(self):
        result = alert_pattern_match("NVDA", PATTERN_ALERT_THRESHOLD - 1, "runup", "standard", 5, "")
        assert result.decision == AlertDecision.BELOW_THRESHOLD

    def test_exact_threshold_sends(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SENT)
        alert_pattern_match(
            "NVDA", PATTERN_ALERT_THRESHOLD, "runup", "standard", 5, "", policy=mock_policy
        )
        mock_policy.dispatch.assert_called_once()

    def test_runup_decline_do_not_collide(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_pattern_match("NVDA", 80, "runup", "standard", 5, "", policy=policy, observed_at=now)
        r2 = alert_pattern_match("NVDA", 80, "decline", "standard", 5, "", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_different_profiles_do_not_collide(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_pattern_match("NVDA", 80, "runup", "standard", 5, "", policy=policy, observed_at=now)
        r2 = alert_pattern_match("NVDA", 80, "runup", "volatile", 5, "", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT


class TestAlertGap:
    def test_gap_up_down_do_not_collide(self, tmp_path):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_gap("TSLA", 5.0, "up", 100.0, 105.0, policy=policy, observed_at=now)
        r2 = alert_gap("TSLA", -5.0, "down", 100.0, 95.0, policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.SENT

    def test_payload_contains_direction(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        alert_gap("TSLA", 5.0, "up", 100.0, 105.0, policy=mock_policy)
        args = mock_policy.dispatch.call_args
        assert "UP" in args.args[1].upper()
        assert "Direction:   up" in args.args[2]


class TestRawSendBypass:
    def test_no_policy_uses_raw_send(self, tmp_path, monkeypatch):
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        r1 = alert_coil("AAPL", 70, 50, "up", "intraday", policy=policy, observed_at=now)

        monkeypatch.setattr(
            "tradex.alerts.notifier._send_discord",
            lambda s, b, color_key="test": True,
        )
        monkeypatch.setattr("tradex.alerts.notifier._send_email", lambda s, b: True)
        monkeypatch.setattr("tradex.alerts.notifier.is_alert_configured", lambda: True)

        r2 = alert_coil("AAPL", 70, 50, "up", "intraday", observed_at=now)
        assert r1.decision == AlertDecision.SENT
        assert r2.decision == AlertDecision.COOLDOWN_DISABLED

    def test_no_policy_no_channels_configured(self, tmp_path, monkeypatch):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        monkeypatch.setattr("tradex.alerts.notifier.is_alert_configured", lambda: False)
        result = alert_coil("AAPL", 70, 50, "up", "intraday", observed_at=now)
        assert result.decision == AlertDecision.NO_CHANNELS_CONFIGURED

    def test_no_policy_all_channels_fail(self, tmp_path, monkeypatch):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "tradex.alerts.notifier._send_discord", lambda s, b, color_key="test": False
        )
        monkeypatch.setattr("tradex.alerts.notifier._send_email", lambda s, b: False)
        monkeypatch.setattr("tradex.alerts.notifier.is_alert_configured", lambda: True)
        result = alert_coil("AAPL", 70, 50, "up", "intraday", observed_at=now)
        assert result.decision == AlertDecision.DELIVERY_FAILED

    def test_no_policy_malformed_result_is_delivery_failed(self, tmp_path, monkeypatch):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        monkeypatch.setattr(
            "tradex.alerts.notifier._send_discord",
            lambda s, b, color_key="test": "true",
        )
        monkeypatch.setattr("tradex.alerts.notifier._send_email", lambda s, b: False)
        monkeypatch.setattr("tradex.alerts.notifier.is_alert_configured", lambda: True)
        result = alert_coil("AAPL", 70, 50, "up", "intraday", observed_at=now)
        assert result.decision == AlertDecision.DELIVERY_FAILED
        assert result.channel_results == {}
