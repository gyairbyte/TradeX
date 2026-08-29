"""Deterministic unit tests for tradex.strategies.registry (MVP-ARCH-001-R6-IMPL-0)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tradex.strategies.registry import (
    APPROVED_PRODUCTION_STRATEGIES,
    SUPPORTED_CAPABILITIES,
    ApprovedProductionStrategy,
    has_production_strategy_capability,
)


def test_approved_production_strategies_is_tuple() -> None:
    """Requirement 1: APPROVED_PRODUCTION_STRATEGIES is a tuple."""
    assert isinstance(APPROVED_PRODUCTION_STRATEGIES, tuple)


def test_approved_production_strategies_is_empty() -> None:
    """Requirement 2: APPROVED_PRODUCTION_STRATEGIES is strictly empty in this release."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    assert len(APPROVED_PRODUCTION_STRATEGIES) == 0


def test_approved_production_strategy_is_frozen_immutable() -> None:
    """Requirement 3: ApprovedProductionStrategy is frozen and cannot be mutated."""
    strat = ApprovedProductionStrategy(
        strategy_id="strat_001",
        strategy_version="1.0.0",
        description="Test strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    with pytest.raises(FrozenInstanceError):
        strat.strategy_id = "other"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        strat.capabilities = frozenset({"journal_execution"})  # type: ignore[misc]


def test_supported_explicit_capabilities_accepted() -> None:
    """Requirement 4: Supported explicit capabilities are accepted."""
    assert SUPPORTED_CAPABILITIES == frozenset({"journal_execution", "automatic_alerts"})

    s1 = ApprovedProductionStrategy(
        strategy_id="strat_alerts",
        strategy_version="1.0.0",
        description="Alerts only strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    assert s1.capabilities == frozenset({"automatic_alerts"})

    s2 = ApprovedProductionStrategy(
        strategy_id="strat_journal",
        strategy_version="1.0.0",
        description="Journal only strategy",
        capabilities=frozenset({"journal_execution"}),
    )
    assert s2.capabilities == frozenset({"journal_execution"})

    s3 = ApprovedProductionStrategy(
        strategy_id="strat_both",
        strategy_version="1.0.0",
        description="Both capabilities strategy",
        capabilities=frozenset({"journal_execution", "automatic_alerts"}),
    )
    assert s3.capabilities == frozenset({"journal_execution", "automatic_alerts"})

    s4 = ApprovedProductionStrategy(
        strategy_id="strat_none",
        strategy_version="1.0.0",
        description="Empty capabilities strategy",
        capabilities=frozenset(),
    )
    assert s4.capabilities == frozenset()


def test_unsupported_capability_rejected() -> None:
    """Requirement 5: Unsupported capabilities or invalid capability types are rejected."""
    with pytest.raises(ValueError, match="unsupported capability"):
        ApprovedProductionStrategy(
            strategy_id="strat_bad",
            strategy_version="1.0.0",
            description="Bad capability strategy",
            capabilities=frozenset({"unsupported_cap"}),
        )

    with pytest.raises(ValueError, match="unsupported capability"):
        ApprovedProductionStrategy(
            strategy_id="strat_mixed",
            strategy_version="1.0.0",
            description="Mixed bad capability strategy",
            capabilities=frozenset({"automatic_alerts", "live_trading"}),
        )

    # Non-frozenset capability type rejected
    with pytest.raises(TypeError, match="capabilities must be a frozenset"):
        ApprovedProductionStrategy(
            strategy_id="strat_list",
            strategy_version="1.0.0",
            description="List capabilities strategy",
            capabilities=["automatic_alerts"],  # type: ignore[arg-type]
        )


def test_malformed_strategy_id_rejected() -> None:
    """Requirement 6: Malformed or empty strategy_id is rejected."""
    invalid_ids = [
        "",
        " ",
        "  leading_space",
        "trailing_space  ",
        "UPPERCASE_STRAT",
        "StratWithMixedCase",
        "-starts-with-hyphen",
        "_starts_with_underscore",
        "has spaces in id",
        "special!chars",
        "a" * 65,  # exceeds 64 chars
        None,
        123,
    ]
    for bad_id in invalid_ids:
        with pytest.raises((ValueError, TypeError)):
            ApprovedProductionStrategy(
                strategy_id=bad_id,  # type: ignore[arg-type]
                strategy_version="1.0.0",
                description="Valid description",
                capabilities=frozenset({"automatic_alerts"}),
            )


def test_malformed_strategy_version_rejected() -> None:
    """Requirement 7: Malformed or empty strategy_version is rejected."""
    invalid_versions = [
        "",
        " ",
        "  leading_space",
        "trailing_space  ",
        "-starts-with-hyphen",
        ".starts.with.dot",
        "_starts_with_underscore",
        "has spaces in version",
        "version!with!exclamation",
        "v" * 33,  # exceeds 32 chars
        None,
        1.0,
    ]
    for bad_ver in invalid_versions:
        with pytest.raises((ValueError, TypeError)):
            ApprovedProductionStrategy(
                strategy_id="valid_strat_id",
                strategy_version=bad_ver,  # type: ignore[arg-type]
                description="Valid description",
                capabilities=frozenset({"automatic_alerts"}),
            )


def test_malformed_description_rejected() -> None:
    """Requirement 8: Malformed or empty description is rejected."""
    invalid_descriptions = [
        "",
        " ",
        "   ",
        "  leading whitespace",
        "trailing whitespace  ",
        None,
        123,
    ]
    for bad_desc in invalid_descriptions:
        with pytest.raises((ValueError, TypeError)):
            ApprovedProductionStrategy(
                strategy_id="valid_strat_id",
                strategy_version="1.0.0",
                description=bad_desc,  # type: ignore[arg-type]
                capabilities=frozenset({"automatic_alerts"}),
            )


def test_exact_identity_and_capability_lookup_monkeypatched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 9: Exact identity + exact capability returns True with monkeypatched registry."""
    strat = ApprovedProductionStrategy(
        strategy_id="alpha_trend",
        strategy_version="2026.08.1",
        description="Alpha trend strategy",
        capabilities=frozenset({"automatic_alerts", "journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    assert has_production_strategy_capability("alpha_trend", "2026.08.1", "automatic_alerts") is True
    assert has_production_strategy_capability("alpha_trend", "2026.08.1", "journal_execution") is True


def test_wrong_strategy_id_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 10: Wrong strategy_id returns False."""
    strat = ApprovedProductionStrategy(
        strategy_id="alpha_trend",
        strategy_version="1.0.0",
        description="Alpha trend",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    assert has_production_strategy_capability("beta_trend", "1.0.0", "automatic_alerts") is False
    assert has_production_strategy_capability("", "1.0.0", "automatic_alerts") is False


def test_wrong_strategy_version_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 11: Wrong strategy_version returns False."""
    strat = ApprovedProductionStrategy(
        strategy_id="alpha_trend",
        strategy_version="1.0.0",
        description="Alpha trend",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    assert has_production_strategy_capability("alpha_trend", "1.0.1", "automatic_alerts") is False
    assert has_production_strategy_capability("alpha_trend", "2.0.0", "automatic_alerts") is False


def test_missing_capability_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 12: Strategy without the requested capability returns False."""
    strat = ApprovedProductionStrategy(
        strategy_id="alerts_only",
        strategy_version="1.0.0",
        description="Alerts only strategy",
        capabilities=frozenset({"automatic_alerts"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    # automatic_alerts granted -> True
    assert has_production_strategy_capability("alerts_only", "1.0.0", "automatic_alerts") is True
    # journal_execution not granted -> False
    assert has_production_strategy_capability("alerts_only", "1.0.0", "journal_execution") is False


def test_unknown_capability_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement 13: Unknown capability lookup returns False."""
    strat = ApprovedProductionStrategy(
        strategy_id="alpha_trend",
        strategy_version="1.0.0",
        description="Alpha trend",
        capabilities=frozenset({"automatic_alerts", "journal_execution"}),
    )
    monkeypatch.setattr(
        "tradex.strategies.registry.APPROVED_PRODUCTION_STRATEGIES",
        (strat,),
    )
    assert has_production_strategy_capability("alpha_trend", "1.0.0", "nonexistent_cap") is False
    assert has_production_strategy_capability("alpha_trend", "1.0.0", "") is False


def test_empty_production_registry_returns_false() -> None:
    """Requirement 14: Central registry in committed empty state returns False for any query."""
    assert has_production_strategy_capability("alpha_trend", "1.0.0", "automatic_alerts") is False
    assert has_production_strategy_capability("alpha_trend", "1.0.0", "journal_execution") is False
    assert has_production_strategy_capability("any_strat", "v1", "automatic_alerts") is False


def test_strategy_domain_independent_of_alerts_ui_providers_persistence() -> None:
    """Requirement 15: tradex.strategies does not import alerts, UI, Streamlit, providers, or persistence."""
    import tradex.strategies.registry as reg_mod

    module_file = reg_mod.__file__
    assert module_file is not None

    # Verify no disallowed module symbols in registry namespace
    disallowed = ["tradex.alerts", "tradex.ui", "streamlit", "tradex.data", "tradex.tracker.store"]
    for mod_name in disallowed:
        assert mod_name not in reg_mod.__dict__

    # Verify sys.modules clean check
    with open(module_file, encoding="utf-8") as f:
        content = f.read()

    assert "import tradex.alerts" not in content
    assert "from tradex.alerts" not in content
    assert "import tradex.ui" not in content
    assert "from tradex.ui" not in content
    assert "import streamlit" not in content
    assert "import tradex.data" not in content
    assert "from tradex.data" not in content
    assert "tradex.tracker" not in content
