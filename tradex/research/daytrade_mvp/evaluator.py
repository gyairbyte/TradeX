"""Deterministic evaluator and orchestrator for day-trading setups (DAYTRADE-001A)."""
from __future__ import annotations

from datetime import datetime

from .models import (
    MultiResolutionSeries,
    SetupEvaluationResult,
    SetupEvaluationStatus,
)
from .setup import DaytradeSetup


def evaluate_setup(
    setup: DaytradeSetup,
    series: MultiResolutionSeries,
    as_of: datetime,
) -> SetupEvaluationResult:
    """Evaluate a setup against multi-resolution series with strict point-in-time safety.

    Guarantees:
    1. A newly materialized MultiResolutionSeries is created containing strictly
       bars available at or before as_of, with zero access path to future bars.
    2. Fail-closed: If any required resolution has zero bars available as of as_of,
       evaluation halts deterministically with INVALID_INPUT.
    3. Output is a neutral research result with explicit reasons and evidence.
    """
    if as_of.tzinfo is None:
        raise ValueError(f"as_of timestamp must be timezone-aware: {as_of}")

    if not isinstance(series, MultiResolutionSeries):
        raise TypeError(f"Expected MultiResolutionSeries, got {type(series).__name__}")

    # Materialize isolated point-in-time instance (no back-reference to unfiltered series)
    pit_series = series.filter_as_of(as_of)

    # Fail-closed check: verify all required resolutions have available data
    missing_resolutions = [
        res for res in setup.required_resolutions if len(pit_series.get_bars(res)) == 0
    ]
    if missing_resolutions:
        missing_names = sorted(res.value for res in missing_resolutions)
        available_names = sorted(res.value for res in pit_series.available_resolutions())
        return SetupEvaluationResult(
            status=SetupEvaluationStatus.INVALID_INPUT,
            setup_id=setup.setup_id,
            setup_version=setup.version,
            as_of=as_of,
            reasons=(
                (
                    f"Missing required resolution data as of {as_of.isoformat()}: "
                    f"{', '.join(missing_names)}"
                ),
            ),
            evidence={
                "missing_resolutions": missing_names,
                "available_resolutions": available_names,
                "ticker": series.ticker,
            },
        )

    # Execute setup evaluation against the PIT-safe series
    result = setup.evaluate(pit_series, as_of)
    if not isinstance(result, SetupEvaluationResult):
        raise TypeError(
            f"Setup evaluate() must return SetupEvaluationResult, got {type(result).__name__}"
        )

    return result
