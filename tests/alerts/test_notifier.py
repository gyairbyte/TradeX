"""Tests for the typed alert helpers, fail-closed gating, and raw send_alert transport."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tradex.alerts.eligibility import ApprovedActionableStrategy
from tradex.alerts.models import AlertDecision, AlertKey
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
from tradex.config import TradeXSettings, settings_from_mapping


def _empty_settings() -> TradeXSettings:
    """Return a runtime settings object with no alert channels configured."""
    return TradeXSettings()


def _discord_settings() -> TradeXSettings:
    """Return a runtime settings object with a Discord channel configured."""
    return settings_from_mapping(
        {
            "ALERT_DISCORD_TOKEN": "token",
            "ALERT_DISCORD_CHANNEL_ID": "123",
        }
    )


@pytest.fixture
def authorized_strategy(monkeypatch):
    """Register an approved strategy for testing authorized alert pathways."""
    strat = ApprovedActionableStrategy(
        strategy_id="TEST-001",
        strategy_version="1.0.0",
        description="Authorized test strategy",
    )
    monkeypatch.setattr(
        "tradex.alerts.eligibility.APPROVED_ACTIONABLE_STRATEGIES",
        (strat,),
    )
    return strat


class TestSendAlert:
    def test_returns_channel_map(self):
        """Manual test alert helper calls underlying transports directly."""
        with (
            patch("tradex.alerts.notifier._send_discord", return_value=False),
            patch("tradex.alerts.notifier._send_email", return_value=False),
        ):
            results = send_alert("subj", "body")
        assert isinstance(results, dict)
        assert "discord" in results
        assert "email" in results

    def test_is_alert_configured_false_without_channels(self, monkeypatch):
        monkeypatch.setattr(
            "tradex.alerts.notifier.load_runtime_settings", _empty_settings
        )
        assert is_alert_configured() is False

    def test_is_alert_configured_true_with_discord(self, monkeypatch):
        monkeypatch.setattr(
            "tradex.alerts.notifier.load_runtime_settings", _discord_settings
        )
        assert is_alert_configured() is True


class TestAlertCoil:
    def test_below_threshold(self):
        result = alert_coil("AAPL", COIL_ALERT_THRESHOLD - 1, 50, "up", "intraday")
        assert result.decision == AlertDecision.BELOW_THRESHOLD

    def test_exact_threshold_dispatches(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SUPPRESSED_EVIDENCE_GATE)
        result = alert_coil("AAPL", COIL_ALERT_THRESHOLD, 50, "up", "intraday", policy=mock_policy)
        mock_policy.dispatch.assert_called_once()
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_above_threshold_dispatches(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SUPPRESSED_EVIDENCE_GATE)
        result = alert_coil("AAPL", COIL_ALERT_THRESHOLD + 5, 50, "up", "intraday", policy=mock_policy)
        mock_policy.dispatch.assert_called_once()
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_unapproved_strategy_gated_when_policy_provided(self, tmp_path):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            clock=lambda: now,
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = alert_coil("AAPL", 70, 50, "up", "intraday", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_authorized_strategy_dispatches(self, tmp_path, authorized_strategy):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            clock=lambda: now,
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        key = AlertKey("AAPL", "coil", "intraday")
        r1 = policy.dispatch(
            key,
            "subject",
            "body",
            observed_at=now,
            strategy_id="TEST-001",
            strategy_version="1.0.0",
            evidence_state="production_approved",
        )
        assert r1.decision == AlertDecision.SENT

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

    def test_exact_threshold_dispatches(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SUPPRESSED_EVIDENCE_GATE)
        alert_confluence(
            "AAPL", CONFLUENCE_ALERT_THRESHOLD, ["intraday", "short"], 100.0, policy=mock_policy
        )
        mock_policy.dispatch.assert_called_once()

    def test_unapproved_strategy_gated(self, tmp_path):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            clock=lambda: now,
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = alert_confluence("AAPL", 75, ["intraday"], 100.0, policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE


class TestAlertPattern:
    def test_below_threshold(self):
        result = alert_pattern_match("NVDA", PATTERN_ALERT_THRESHOLD - 1, "runup", "standard", 5, "")
        assert result.decision == AlertDecision.BELOW_THRESHOLD

    def test_exact_threshold_dispatches(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        mock_policy.dispatch.return_value = MagicMock(decision=AlertDecision.SUPPRESSED_EVIDENCE_GATE)
        alert_pattern_match(
            "NVDA", PATTERN_ALERT_THRESHOLD, "runup", "standard", 5, "", policy=mock_policy
        )
        mock_policy.dispatch.assert_called_once()

    def test_unapproved_pattern_gated(self, tmp_path):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            clock=lambda: now,
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = alert_pattern_match("NVDA", 80, "runup", "standard", 5, "", policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE


class TestAlertGap:
    def test_unapproved_gap_gated(self, tmp_path):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store = AlertStore(tmp_path / "alerts.db")
        policy = AlertPolicy(
            clock=lambda: now,
            store=store,
            transport=lambda s, b, c: {"discord": True},
            is_configured=lambda: True,
        )
        r1 = alert_gap("TSLA", 5.0, "up", 100.0, 105.0, policy=policy, observed_at=now)
        assert r1.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_payload_contains_direction(self):
        mock_policy = MagicMock(spec=AlertPolicy)
        alert_gap("TSLA", 5.0, "up", 100.0, 105.0, policy=mock_policy)
        args = mock_policy.dispatch.call_args
        assert "UP" in args.args[1].upper()
        assert "Direction:   up" in args.args[2]


class TestNoPolicyAutomaticGating:
    """When policy is omitted, helpers must lazily instantiate AlertPolicy and gate fail-closed."""

    def test_alert_coil_no_policy_gates_fail_closed(self, tmp_path, monkeypatch):
        db_path = tmp_path / "alerts.db"
        settings = settings_from_mapping({"ALERT_STATE_PATH": str(db_path)})
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        result = alert_coil(
            "AAPL", 70, 50, "up", "intraday", settings=settings, observed_at=now
        )
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_alert_confluence_no_policy_gates_fail_closed(self, tmp_path):
        db_path = tmp_path / "alerts.db"
        settings = settings_from_mapping({"ALERT_STATE_PATH": str(db_path)})
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        result = alert_confluence(
            "AAPL", 75, ["intraday"], 100.0, settings=settings, observed_at=now
        )
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_alert_gap_no_policy_gates_fail_closed(self, tmp_path):
        db_path = tmp_path / "alerts.db"
        settings = settings_from_mapping({"ALERT_STATE_PATH": str(db_path)})
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        result = alert_gap(
            "TSLA", 5.0, "up", 100.0, 105.0, settings=settings, observed_at=now
        )
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE

    def test_alert_pattern_match_no_policy_gates_fail_closed(self, tmp_path):
        db_path = tmp_path / "alerts.db"
        settings = settings_from_mapping({"ALERT_STATE_PATH": str(db_path)})
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        result = alert_pattern_match(
            "NVDA", 80, "runup", "standard", 5, "", settings=settings, observed_at=now
        )
        assert result.decision == AlertDecision.SUPPRESSED_EVIDENCE_GATE
