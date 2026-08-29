"""Deterministic unit tests for tradex.alerts.eligibility (MVP-ARCH-001-R6-IMPL-0)."""
from __future__ import annotations

import sys

import pytest

from tradex.alerts.eligibility import (
    AlertEligibilityResult,
    check_automatic_alert_eligibility,
)
from tradex.alerts.models import AlertKey
from tradex.strategies.registry import (
    APPROVED_PRODUCTION_STRATEGIES,
    ApprovedProductionStrategy,
)


def test_central_production_strategies_registry_is_empty() -> None:
    """In R6-IMPL-0, the central approved production strategy registry is strictly empty."""
    assert isinstance(APPROVED_PRODUCTION_STRATEGIES, tuple)
    assert len(APPROVED_PRODUCTION_STRATEGIES) == 0


def test_runtime_eligibility_does_not_import_ui_or_streamlit() -> None:
    """The runtime safety boundary must not depend on or import UI modules."""
    import tradex.alerts.eligibility as eligibility_mod

    module_source = eligibility_mod.__file__
    assert module_source is not None
    assert "streamlit" not in sys.modules or "tradex.ui" not in str(eligibility_mod.__dict__)


def test_non_alert_key_rejected() -> None:
    """Passing a non-AlertKey object returns ineligible."""
    result = check_automatic_alert_eligibility("not-a-key")  # type: ignore[arg-type]
    assert isinstance(result, AlertEligibilityResult)
    assert result.eligible is False
    assert "invalid or non-AlertKey" in result.reason


def test_missing_strategy_identity_fails_closed() -> None:
    """Any market alert missing strategy_id or strategy_version fails closed."""
    key = AlertKey("AAPL", "coil", "intraday")
    r1 = check_automatic_alert_eligibility(key)
    r2 = check_automatic_alert_eligibility(key, strategy_id="strat_001")
    r3 = check_automatic_alert_eligibility(key, strategy_version="1.0.0")

    assert r1.eligible is False
    assert r2.eligible is False
    assert r3.eligible is False
    assert "no approved actionable strategy identity" in r1.reason


def test_unapproved_evidence_states_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any evidence state other than production_approved fails closed, even if strategy is authorized."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="strat_001",
        strategy_version="1.0.0",
        description="Test strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )

    key = AlertKey("AAPL", "confluence", "multi")
    unapproved_states = [
        None,
        "legacy_heuristic",
        "exploratory",
        "rejected",
        "research_only",
        "inconclusive",
        "not_supported",
        "archived",
        "unknown",
    ]
    for state in unapproved_states:
        res = check_automatic_alert_eligibility(
            key,
            strategy_id="strat_001",
            strategy_version="1.0.0",
            evidence_state=state,
        )
        assert res.eligible is False, f"State {state} should be ineligible"
        assert "not production_approved" in res.reason


def test_production_approved_state_alone_insufficient_without_registry_entry() -> None:
    """evidence_state == 'production_approved' is NOT sufficient without registry match."""
    key = AlertKey("TSLA", "gap:up", "premarket")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="unapproved_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is False
    assert "lacks 'automatic_alerts' capability in central production strategy registry" in res.reason


def test_existing_heuristic_and_exploratory_outputs_fail_closed() -> None:
    """All existing heuristic, exploratory, and research alert keys fail closed."""
    keys = [
        AlertKey("AAPL", "coil", "intraday"),
        AlertKey("MSFT", "coil", "short"),
        AlertKey("NVDA", "confluence", "multi"),
        AlertKey("TSLA", "gap:up", "premarket"),
        AlertKey("AMZN", "gap:down", "premarket"),
        AlertKey("PLTR", "pattern:runup:standard", "pattern"),
    ]
    for key in keys:
        res = check_automatic_alert_eligibility(key)
        assert res.eligible is False
        assert "fail-closed" in res.reason


def test_capability_separation_journal_execution_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy with only 'journal_execution' capability remains INELIGIBLE for alerts."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="journal_strat",
        strategy_version="1.0.0",
        description="Journal only strategy",
        capabilities=frozenset({"journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )
    key = AlertKey("AAPL", "signal", "intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="journal_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is False
    assert "lacks 'automatic_alerts' capability" in res.reason


def test_capability_separation_automatic_alerts_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy with 'automatic_alerts' capability and 'production_approved' evidence is ELIGIBLE."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="alert_strat",
        strategy_version="1.0.0",
        description="Alerts only strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )
    key = AlertKey("AAPL", "signal", "intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="alert_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is True
    assert "authorized for automatic market alert delivery" in res.reason


def test_capability_separation_both_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strategy with both capabilities and 'production_approved' evidence is ELIGIBLE."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="multi_strat",
        strategy_version="1.0.0",
        description="Both capabilities strategy",
        capabilities=frozenset({"journal_execution", "automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )
    key = AlertKey("AAPL", "signal", "intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="multi_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is True
    assert "authorized for automatic market alert delivery" in res.reason


def test_wrong_strategy_version_ineligible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrong strategy version is INELIGIBLE even with automatic_alerts granted on another version."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="alert_strat",
        strategy_version="1.0.0",
        description="Alerts strategy v1",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )
    key = AlertKey("AAPL", "signal", "intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="alert_strat",
        strategy_version="2.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is False
    assert "lacks 'automatic_alerts' capability" in res.reason


def test_unknown_strategy_ineligible(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown strategy identity is INELIGIBLE."""
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="alert_strat",
        strategy_version="1.0.0",
        description="Alerts strategy v1",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )
    key = AlertKey("AAPL", "signal", "intraday")
    res = check_automatic_alert_eligibility(
        key,
        strategy_id="other_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    )
    assert res.eligible is False
    assert "lacks 'automatic_alerts' capability" in res.reason


def test_call_time_central_registry_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Demonstrates eligibility consults the central registry dynamically at call time."""
    key = AlertKey("AAPL", "signal", "intraday")

    # Initial state: empty registry -> ineligible
    assert check_automatic_alert_eligibility(
        key,
        strategy_id="dynamic_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    ).eligible is False

    # Dynamically authorize at runtime
    mock_strategy = ApprovedProductionStrategy(
        strategy_id="dynamic_strat",
        strategy_version="1.0.0",
        description="Dynamically registered strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (mock_strategy,),
    )

    # Immediately eligible
    assert check_automatic_alert_eligibility(
        key,
        strategy_id="dynamic_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    ).eligible is True

    # Dynamically revoke
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (),
    )

    # Immediately ineligible again
    assert check_automatic_alert_eligibility(
        key,
        strategy_id="dynamic_strat",
        strategy_version="1.0.0",
        evidence_state="production_approved",
    ).eligible is False
