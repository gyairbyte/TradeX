"""Tests for outcome calculations, algebraic equivalence, and execution friction models."""
from __future__ import annotations

import pytest

from tradex.research.daytrade_momentum.outcomes import (
    apply_friction_to_gross_return,
    calculate_gross_signed_return,
    calculate_gross_win_rate,
)
from tradex.research.daytrade_momentum.spec import DaytradeSpec


def test_gross_signed_return_long_and_short() -> None:
    """Verify gross return formulas for LONG and SHORT directions."""
    entry = 100.0
    exit_higher = 102.0
    exit_lower = 98.0

    # LONG when price increases (+2%)
    assert pytest.approx(calculate_gross_signed_return("LONG", entry, exit_higher)) == 0.02
    # LONG when price decreases (-2%)
    assert pytest.approx(calculate_gross_signed_return("LONG", entry, exit_lower)) == -0.02

    # SHORT when price increases (-2% return)
    # 1.0 - 102.0/100.0 = -0.02
    assert pytest.approx(calculate_gross_signed_return("SHORT", entry, exit_higher)) == -0.02
    # SHORT when price decreases (+2% return)
    # 1.0 - 98.0/100.0 = +0.02
    assert pytest.approx(calculate_gross_signed_return("SHORT", entry, exit_lower)) == 0.02


def test_algebraic_equivalence_short_formula() -> None:
    """Verify algebraic equivalence: 1 - exit/entry == -(exit/entry - 1)."""
    pairs = [(100.0, 95.0), (100.0, 105.0), (50.0, 49.5), (200.0, 202.0)]
    for entry, exit_px in pairs:
        form1 = 1.0 - (exit_px / entry)
        form2 = -1.0 * ((exit_px / entry) - 1.0)
        assert pytest.approx(form1, abs=1e-12) == form2
        assert pytest.approx(calculate_gross_signed_return("SHORT", entry, exit_px), abs=1e-12) == form1


def test_execution_friction_models() -> None:
    """Verify friction levels: 0 bps, 2 bps (4 bps round-trip), 5 bps (10 bps round-trip)."""
    gross = 0.0100  # 100 bps

    net_0bps = apply_friction_to_gross_return(gross, bps_per_side=0.0)
    assert pytest.approx(net_0bps) == 0.0100

    net_2bps = apply_friction_to_gross_return(gross, bps_per_side=2.0)
    assert pytest.approx(net_2bps) == 0.0096  # 100 - 4 = 96 bps

    net_5bps = apply_friction_to_gross_return(gross, bps_per_side=5.0)
    assert pytest.approx(net_5bps) == 0.0090  # 100 - 10 = 90 bps


def test_gross_win_rate_calculation() -> None:
    """Verify gross win rate is fraction of strictly positive gross returns."""
    # 3 positive, 1 negative, 1 zero -> 3 / 5 = 60.0%
    returns = [0.01, 0.02, -0.005, 0.003, 0.0]
    win_rate = calculate_gross_win_rate(returns)
    assert pytest.approx(win_rate) == 0.60

    # Empty list returns 0.0
    assert calculate_gross_win_rate([]) == 0.0


def test_no_auction_price_lock(locked_spec: DaytradeSpec) -> None:
    """Verify spec explicitly locks official_closing_auction_price_used == False."""
    assert locked_spec.raw_dict["session_semantics"]["official_closing_auction_price_used"] is False
    assert locked_spec.raw_dict["signal_definition"]["official_closing_auction_price_used"] is False
    timing = locked_spec.raw_dict["execution_and_outcomes"]["timing"]
    assert "not assumed to equal the official closing-auction" in timing["exit_semantics_notes"]
