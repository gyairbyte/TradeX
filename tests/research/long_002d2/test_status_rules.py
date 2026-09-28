"""Tests for LONG-002D2 status decision rules."""
from __future__ import annotations

from tradex.research.long_002d2.spec import (
    STATUS_INCONCLUSIVE,
    STATUS_INVALID_DATA_CONTRACT,
    STATUS_NOT_SUPPORTED,
    STATUS_SUPPORTED,
    evaluate_relative_volume_status,
)


def test_status_supported_when_all_criteria_met() -> None:
    """Verify supported_for_next_stage when all 5 preregistered conditions hold."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=0.015,
        ci_2_5_block_21=0.002,
        ci_97_5_block_21=0.028,
        median_block_42=0.014,
        annual_positive_delta_years=4,
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_SUPPORTED


def test_status_invalid_data_contract_when_gates_fail() -> None:
    """Verify invalid_data_contract overrides statistical results when gates fail."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=0.05,
        ci_2_5_block_21=0.02,
        ci_97_5_block_21=0.08,
        median_block_42=0.05,
        annual_positive_delta_years=5,
        all_integrity_gates_passed=False,
    )
    assert status == STATUS_INVALID_DATA_CONTRACT


def test_status_not_supported_when_upper_ci_lte_zero() -> None:
    """Verify not_supported when 21-session 97.5th percentile is non-positive."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=-0.005,
        ci_2_5_block_21=-0.020,
        ci_97_5_block_21=0.0,
        median_block_42=-0.004,
        annual_positive_delta_years=2,
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_NOT_SUPPORTED


def test_status_not_supported_when_delta_lte_zero_and_years_lte_two() -> None:
    """Verify not_supported when pooled delta <= 0 and positive years <= 2."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=-0.002,
        ci_2_5_block_21=-0.015,
        ci_97_5_block_21=0.010,
        median_block_42=-0.001,
        annual_positive_delta_years=2,
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_NOT_SUPPORTED


def test_status_inconclusive_when_positive_years_is_three() -> None:
    """Verify inconclusive when positive delta, positive CI, but only 3/5 years."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=0.010,
        ci_2_5_block_21=0.001,
        ci_97_5_block_21=0.020,
        median_block_42=0.009,
        annual_positive_delta_years=3,  # requires >= 4
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_INCONCLUSIVE


def test_status_inconclusive_when_lower_ci_crosses_zero() -> None:
    """Verify inconclusive when lower CI is <= 0 despite positive pooled delta."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=0.010,
        ci_2_5_block_21=-0.002,  # crosses zero
        ci_97_5_block_21=0.025,
        median_block_42=0.009,
        annual_positive_delta_years=4,
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_INCONCLUSIVE


def test_status_inconclusive_when_median_42_lte_zero() -> None:
    """Verify inconclusive when 42-session median is non-positive."""
    status = evaluate_relative_volume_status(
        pooled_precision_delta=0.005,
        ci_2_5_block_21=0.001,
        ci_97_5_block_21=0.015,
        median_block_42=0.0,  # requires > 0
        annual_positive_delta_years=4,
        all_integrity_gates_passed=True,
    )
    assert status == STATUS_INCONCLUSIVE
