"""Tests confirming production isolation and empty strategy registry."""
from __future__ import annotations

from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


def test_approved_production_strategies_is_empty() -> None:
    """Verify that APPROVED_PRODUCTION_STRATEGIES remains strictly empty ()."""
    assert isinstance(APPROVED_PRODUCTION_STRATEGIES, tuple)
    assert APPROVED_PRODUCTION_STRATEGIES == ()
    assert len(APPROVED_PRODUCTION_STRATEGIES) == 0
