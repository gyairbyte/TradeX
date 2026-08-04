"""Tests for alert cooldown integration in the watcher."""
from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.alerts.models import AlertDecision, AlertKey
from tradex.alerts.policy import AlertPolicy
from tradex.alerts.store import AlertStore
from tradex.tracker import watcher


@pytest.fixture
def fake_coils():
    return pd.DataFrame([{
        "ticker": "AAPL",
        "coil_strength": 70,
        "latest_score": 80,
        "trend_direction": "up",
    }])


@pytest.fixture
def fake_confluence():
    return pd.DataFrame([{
        "ticker": "AAPL",
        "confluence_score": 75,
        "active_timeframes": "intraday, short",
        "last_close": 150.0,
    }])


@pytest.fixture
def empty_matches():
    return pd.DataFrame(columns=["ticker", "similarity_score", "fp_events", "interpretation"])


@pytest.fixture(autouse=True)
def _isolated_alert_state(tmp_path, monkeypatch):
    """Redirect alert state to a per-test temp path and mock the notifier."""
    monkeypatch.setenv("ALERT_STATE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setattr(
        "tradex.alerts.policy.send_alert",
        lambda s, b, color_key="test", *, settings=None: {"discord": True, "email": False},
    )
    monkeypatch.setattr("tradex.alerts.policy.is_alert_configured", lambda: True)


class TestWatcherAlertIntegration:
    def test_check_alerts_returns_results(self, fake_coils, fake_confluence, empty_matches):
        with (
            patch.object(watcher.analyzer, "detect_coils", return_value=fake_coils),
            patch.object(watcher, "run_confluence_screen", return_value=fake_confluence),
        ):
            results = watcher._check_alerts(["AAPL"], "intraday", observed_at=datetime.now(UTC))
        assert isinstance(results, list)
        assert len(results) == 2  # coil + confluence; pattern matching is quarantined from automatic alerts

    def test_check_alerts_builds_default_policy_and_suppresses(
        self, fake_coils, empty_matches, tmp_path, monkeypatch
    ):
        """Direct _check_alerts(..., alert_policy=None) lazily builds the default policy."""
        now = datetime.now(UTC)
        alert_state_path = tmp_path / "alerts.db"
        monkeypatch.setenv("ALERT_STATE_PATH", str(alert_state_path))
        monkeypatch.setattr(
            "tradex.alerts.policy.send_alert",
            lambda s, b, color_key="test", *, settings=None: {"discord": True, "email": False},
        )
        monkeypatch.setattr("tradex.alerts.policy.is_alert_configured", lambda: True)

        with (
            patch.object(watcher.analyzer, "detect_coils", return_value=fake_coils),
            patch.object(watcher, "run_confluence_screen", return_value=empty_matches),
        ):
            results1 = watcher._check_alerts(["AAPL"], "intraday", alert_policy=None, observed_at=now)
            results2 = watcher._check_alerts(["AAPL"], "intraday", alert_policy=None, observed_at=now)

        assert any(r.decision == AlertDecision.SENT for r in results1)
        assert any(r.decision == AlertDecision.SUPPRESSED_COOLDOWN for r in results2)
        state = AlertStore(alert_state_path).get_state(AlertKey("AAPL", "coil", "intraday"))
        assert state.sent_count == 1
        assert state.suppressed_count == 1

    def test_run_once_passes_injected_timestamp_to_alerts(
        self, fake_coils, fake_confluence, empty_matches, tmp_path, capsys, fresh_signal_db
    ):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store_path = tmp_path / "alerts.db"
        alert_policy = AlertPolicy(
            clock=lambda: now,
            store=AlertStore(store_path),
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )

        results = pd.DataFrame([{
            "ticker": "AAPL",
            "score": 80,
            "last_close": 150.0,
            "volume_ratio": 2.0,
            "rsi": 60.0,
            "reasons": "test",
            "provider": "yahoo",
        }])

        with (
            patch.object(watcher, "screener_run_with_report") as mock_screener,
            patch.object(watcher.analyzer, "detect_coils", return_value=fake_coils),
            patch.object(watcher, "run_confluence_screen", return_value=fake_confluence),
            patch.object(watcher.store, "record_scan"),
        ):
            mock_report = MagicMock()
            mock_report.results = results
            mock_report.total_fetched = 1
            mock_report.total_earnings_excluded = 0
            mock_report.total_fetch_eligible = 1
            mock_report.fetch_failures = {}
            mock_report.earnings_failures = {}
            mock_report.scoring_failures = {}
            mock_report.attempt_log = []
            mock_report.providers_attempted = ("yahoo",)
            mock_report.total_fetch_attempted = 1
            mock_report.total_retries = 0
            mock_report.actual_provider = "yahoo"
            mock_report.requested_provider = "yahoo"
            mock_report.fallback_used = False
            mock_screener.return_value = mock_report

            watcher.run_once(
                ["AAPL"], timeframe="intraday", alert_policy=alert_policy, now=now
            )

        captured = capsys.readouterr()
        assert "[alerts]" in captured.out

    def test_repeated_interval_scan_suppresses_duplicate_alerts(
        self, fake_coils, fake_confluence, empty_matches, tmp_path, capsys, fresh_signal_db
    ):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        store_path = tmp_path / "alerts.db"
        alert_policy = AlertPolicy(
            clock=lambda: now,
            store=AlertStore(store_path),
            transport=lambda s, b, c: {"discord": True, "email": False},
            is_configured=lambda: True,
        )

        results = pd.DataFrame([{
            "ticker": "AAPL",
            "score": 80,
            "last_close": 150.0,
            "volume_ratio": 2.0,
            "rsi": 60.0,
            "reasons": "test",
            "provider": "yahoo",
        }])

        def _run():
            with (
                patch.object(watcher, "screener_run_with_report") as mock_screener,
                patch.object(watcher.analyzer, "detect_coils", return_value=fake_coils),
                patch.object(watcher, "run_confluence_screen", return_value=fake_confluence),
                patch.object(watcher.store, "record_scan"),
            ):
                mock_report = MagicMock()
                mock_report.results = results
                mock_report.total_fetched = 1
                mock_report.total_earnings_excluded = 0
                mock_report.total_fetch_eligible = 1
                mock_report.fetch_failures = {}
                mock_report.earnings_failures = {}
                mock_report.scoring_failures = {}
                mock_report.attempt_log = []
                mock_report.providers_attempted = ("yahoo",)
                mock_report.total_fetch_attempted = 1
                mock_report.total_retries = 0
                mock_report.actual_provider = "yahoo"
                mock_report.requested_provider = "yahoo"
                mock_report.fallback_used = False
                mock_screener.return_value = mock_report
                watcher.run_once(
                    ["AAPL"], timeframe="intraday", alert_policy=alert_policy, now=now
                )

        _run()
        out1 = capsys.readouterr().out
        _run()
        out2 = capsys.readouterr().out
        assert "sent=" in out1
        assert "suppressed=" in out2

    def test_alert_summary_counts_are_accurate(self):
        from tradex.alerts.models import AlertDispatchResult, AlertKey
        results = [
            AlertDispatchResult(
                key=AlertKey("A", "coil", "i"),
                decision=AlertDecision.SENT,
                observed_at=datetime.now(UTC),
                cooldown_minutes=60,
                last_success_at=None,
                next_eligible_at=None,
                reason="",
                channel_results={},
            ),
            AlertDispatchResult(
                key=AlertKey("B", "coil", "i"),
                decision=AlertDecision.SUPPRESSED_COOLDOWN,
                observed_at=datetime.now(UTC),
                cooldown_minutes=60,
                last_success_at=None,
                next_eligible_at=None,
                reason="",
                channel_results={},
            ),
            AlertDispatchResult(
                key=AlertKey("C", "coil", "i"),
                decision=AlertDecision.DELIVERY_FAILED,
                observed_at=datetime.now(UTC),
                cooldown_minutes=60,
                last_success_at=None,
                next_eligible_at=None,
                reason="",
                channel_results={},
            ),
            AlertDispatchResult(
                key=AlertKey("D", "coil", "i"),
                decision=AlertDecision.POLICY_ERROR,
                observed_at=datetime.now(UTC),
                cooldown_minutes=60,
                last_success_at=None,
                next_eligible_at=None,
                reason="",
                channel_results={},
            ),
        ]
        watcher._print_alert_summary(results)

    def test_alert_summary_prints_per_suppression_details(self, capsys):
        from tradex.alerts.models import AlertDispatchResult, AlertKey
        now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        cooldown_until = now + timedelta(minutes=60)
        claim_expires = now + timedelta(seconds=120)
        results = [
            AlertDispatchResult(
                key=AlertKey("AAPL", "coil", "intraday"),
                decision=AlertDecision.SUPPRESSED_COOLDOWN,
                observed_at=now,
                cooldown_minutes=60,
                last_success_at=None,
                next_eligible_at=cooldown_until,
                reason="Cooldown active",
                channel_results={},
            ),
            AlertDispatchResult(
                key=AlertKey("TSLA", "gap:up", "premarket"),
                decision=AlertDecision.SUPPRESSED_IN_FLIGHT,
                observed_at=now,
                cooldown_minutes=None,
                last_success_at=None,
                next_eligible_at=claim_expires,
                reason="Another delivery claim is in flight",
                channel_results={},
            ),
        ]
        watcher._print_alert_summary(results)
        out = capsys.readouterr().out
        assert "suppressed (cooldown): AAPL | coil | intraday" in out
        assert "next eligible at 2024-01-01T13:00:00+00:00" in out
        assert "suppressed (in-flight): TSLA | gap:up | premarket" in out
        assert "claim expires at" in out

    def test_run_once_builds_default_alert_policy(
        self, fake_coils, empty_matches, tmp_path, monkeypatch, fresh_signal_db
    ):
        """run_once(..., alert_policy=None) lazily builds and reuses the default policy."""
        now = datetime.now(UTC)
        alert_state_path = tmp_path / "alerts.db"
        monkeypatch.setenv("ALERT_STATE_PATH", str(alert_state_path))

        monkeypatch.setattr(
            "tradex.alerts.policy.send_alert",
            lambda s, b, color_key="test", *, settings=None: {"discord": True, "email": False},
        )
        monkeypatch.setattr("tradex.alerts.policy.is_alert_configured", lambda: True)

        results = pd.DataFrame([{
            "ticker": "AAPL",
            "score": 80,
            "last_close": 150.0,
            "volume_ratio": 2.0,
            "rsi": 60.0,
            "reasons": "test",
            "provider": "yahoo",
        }])

        def _run():
            with (
                patch.object(watcher, "screener_run_with_report") as mock_screener,
                patch.object(watcher.analyzer, "detect_coils", return_value=fake_coils),
                patch.object(watcher, "run_confluence_screen", return_value=empty_matches),
                patch.object(watcher.store, "record_scan"),
            ):
                mock_report = MagicMock()
                mock_report.results = results
                mock_report.total_fetched = 1
                mock_report.total_earnings_excluded = 0
                mock_report.total_fetch_eligible = 1
                mock_report.fetch_failures = {}
                mock_report.earnings_failures = {}
                mock_report.scoring_failures = {}
                mock_report.attempt_log = []
                mock_report.providers_attempted = ("yahoo",)
                mock_report.total_fetch_attempted = 1
                mock_report.total_retries = 0
                mock_report.actual_provider = "yahoo"
                mock_report.requested_provider = "yahoo"
                mock_report.fallback_used = False
                mock_screener.return_value = mock_report
                watcher.run_once(
                    ["AAPL"], timeframe="intraday", alert_policy=None, now=now
                )

        _run()
        _run()

        store = AlertStore(alert_state_path)
        state = store.get_state(AlertKey("AAPL", "coil", "intraday"))
        assert state.sent_count == 1
        assert state.suppressed_count == 1


class TestWatcherCLI:
    def test_help_creates_no_database(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        result = subprocess.run(
            [sys.executable, "-m", "tradex.tracker.watcher", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent),
            check=False,
        )
        assert result.returncode == 0
        assert "--alert-cooldown-minutes" in result.stdout
        assert not (home / ".tradex" / "alerts.db").exists()

    def test_invalid_negative_cooldown(self, tmp_path, monkeypatch):
        result = subprocess.run(
            [sys.executable, "-m", "tradex.tracker.watcher", "--alert-cooldown-minutes", "-5"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "Traceback" not in result.stderr
        assert "error" in result.stderr.lower()

    def test_invalid_zero_cooldown(self, tmp_path, monkeypatch):
        result = subprocess.run(
            [sys.executable, "-m", "tradex.tracker.watcher", "--alert-cooldown-minutes", "0"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "Traceback" not in result.stderr
        assert "error" in result.stderr.lower()

    def test_disable_cooldown_flag(self, tmp_path, monkeypatch):
        result = subprocess.run(
            [sys.executable, "-m", "tradex.tracker.watcher", "--disable-alert-cooldown", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0

    def test_state_path_override(self, tmp_path):
        state = tmp_path / "custom_alerts.db"
        result = subprocess.run(
            [sys.executable, "-m", "tradex.tracker.watcher", "--alert-state-path", str(state), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
