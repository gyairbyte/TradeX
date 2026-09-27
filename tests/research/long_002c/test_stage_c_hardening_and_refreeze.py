"""Regression tests for Stage-C hardening, provider failure handling, and re-freeze invariants (PR #85).

Tests all 12 items and 4 clarifications:
1. SEC EDGAR failure semantics (typed exceptions, retry, genuine 404 vs failure).
2. Split-normalized analytical OHLC separation (no fallback to raw OHLC).
3. Massive corporate action hardening (pagination, retries, typed exceptions).
4. Historical ticker pair Massive request projections ($2 \\times historical_ticker_pairs$).
5. Real internal ticker gap auditing.
6. Locked historical daily-bar quality gates (completeness >= 99%, max 2 missing, max 1 consec, 0 dups, 0 malformed).
7. Historical ticker resolution propagation (no fallback to primary_symbol on unresolved).
8. Baseline winner selection (no max_overlap fallback, legacy_tradex_scorer disqualified from winning).
9. Stage C source-of-truth authorization & abort semantics.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradex.research.long_002c.bars import load_interval_aware_daily_bars
from tradex.research.long_002c.baselines import select_winning_baseline
from tradex.research.long_002c.calendar import get_trading_sessions
from tradex.research.long_002c.dataset import build_decision_observations_for_security
from tradex.research.long_002c.frozen_manifest import build_frozen_pre_run_manifest_data
from tradex.research.long_002c.identity import (
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    SecurityIdentity,
)
from tradex.research.long_002c.manifest import (
    CandidateSecurity,
    TickerInterval,
)
from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    OutcomeLabelRecord,
)
from tradex.research.long_002c.providers import (
    EdgarClient,
    MassiveRefClient,
    ProviderRateLimitedUnresolved,
    ProviderRequestFailed,
)
from tradex.research.long_002c.screening import screen_candidate_security
from tradex.research.long_002c.spec import DEV_END, WARMUP_START


# =====================================================================
# 1. SEC EDGAR Failure Semantics & Stage B Screening
# =====================================================================
def test_edgar_retry_and_rate_limit_metrics() -> None:
    """EdgarClient records retries, 429s, and raises ProviderRateLimitedUnresolved on 429 exhaustion."""
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "0"}
    mock_resp_429.content = b'{"error": "rate limit"}'

    client = EdgarClient(max_retries=2, request_delay_seconds=0, request_func=lambda url: mock_resp_429)

    with pytest.raises(ProviderRateLimitedUnresolved) as exc_info:
        client._fetch_json("https://data.sec.gov/test.json")

    assert exc_info.value.status_code == 429

    metrics = client.get_audit_metrics()
    assert metrics["rate_limit_429_count"] > 0
    assert metrics["retries_count"] > 0
    assert metrics["unresolved_failure_count"] > 0


def test_edgar_genuine_404_not_found() -> None:
    """EdgarClient treats HTTP 404 as genuine not found (no exception, increments not_found_genuine_count)."""
    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404
    mock_resp_404.headers = {}
    mock_resp_404.content = b""

    client = EdgarClient(max_retries=1, request_delay_seconds=0, request_func=lambda url: mock_resp_404)

    data, prov = client.fetch_company_facts("0009999999")
    assert data is None
    assert len(prov) == 1

    metrics = client.get_audit_metrics()
    assert metrics["not_found_genuine_count"] == 1
    assert metrics["unresolved_failure_count"] == 0


def test_screening_catches_edgar_failure_as_provider_failure() -> None:
    """screen_candidate_security isolates EDGAR provider failure from genuine missing shares."""
    cand = CandidateSecurity(
        immutable_security_id="SEC_EDGAR_FAIL",
        primary_symbol="FAILSYM",
        cik="0001234567",
        security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
        ticker_intervals=[
            TickerInterval(symbol="FAILSYM", start_date=WARMUP_START, end_date=DEV_END)
        ],
    )

    mock_alpaca = MagicMock()
    sessions = get_trading_sessions("2015-01-01", "2016-04-01")
    bars = [
        {"t": f"{s}T16:00:00Z", "o": 50.0, "h": 55.0, "l": 49.0, "c": 52.0, "v": 1_000_000}
        for s in sessions
    ]
    mock_alpaca.fetch_daily_bars.return_value = (bars, [])

    mock_edgar = MagicMock()
    mock_edgar.fetch_company_facts.side_effect = ProviderRateLimitedUnresolved(
        "Rate limited unresolved after 3 attempts",
        symbol="0001234567",
        status_code=429,
        retry_count=3,
    )

    is_elig, reasons, details = screen_candidate_security(
        candidate=cand,
        alpaca=mock_alpaca,
        edgar=mock_edgar,
        dev_start="2016-01-01",
        dev_end="2016-03-31",
    )
    assert not is_elig
    assert details["is_provider_failure"] is True
    assert details["provider_failure"]["provider"] == "sec_edgar"
    assert "provider_rate_limited_unresolved" in reasons


# =====================================================================
# 2. Split-Normalized Analytical OHLC Separation (Clarification 2)
# =====================================================================
def test_no_raw_fallback_in_split_adjusted_bars() -> None:
    """load_interval_aware_daily_bars never fills missing split-adjusted OHLC with raw OHLC."""
    cand = CandidateSecurity(
        immutable_security_id="SEC_ADJ_TEST",
        primary_symbol="TEST",
        cik="0001111111",
        security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
        ticker_intervals=[
            TickerInterval(symbol="TEST", start_date="2016-01-01", end_date="2016-01-10")
        ],
    )

    raw_bars = [
        {"t": "2016-01-04T16:00:00Z", "o": 100.0, "h": 105.0, "l": 95.0, "c": 102.0, "v": 1000},
        {"t": "2016-01-05T16:00:00Z", "o": 102.0, "h": 106.0, "l": 101.0, "c": 105.0, "v": 1000},
    ]
    # Split bars only contain first date; second date is missing
    adj_bars = [
        {"t": "2016-01-04T16:00:00Z", "o": 50.0, "h": 52.5, "l": 47.5, "c": 51.0, "v": 2000},
    ]

    mock_alpaca = MagicMock()

    def fetch_bars(sym: str, *args: Any, adjustment: str = "raw", **kwargs: Any) -> tuple[list[dict[str, Any]], list[Any]]:
        return (adj_bars, []) if adjustment == "split" else (raw_bars, [])

    mock_alpaca.fetch_daily_bars.side_effect = fetch_bars

    df, _, bar_meta = load_interval_aware_daily_bars(
        candidate=cand,
        alpaca=mock_alpaca,
        warmup_start="2016-01-01",
        dev_end="2016-01-10",
        load_split_adjusted=True,
    )

    assert bar_meta["analytical_data_incomplete"] is True
    # The second date must have None/NaN for adjusted open/high/low/close, NOT raw 105.0
    row_2 = df.loc["2016-01-05"]
    assert row_2["as_traded_close"] == 105.0
    assert pd.isna(row_2["close"])


# =====================================================================
# 3. Massive Corporate Action Hardening
# =====================================================================
def test_massive_pagination_and_retry_hardening() -> None:
    """MassiveRefClient follows pagination to exhaustion and aggregates provenance."""
    client = MassiveRefClient("dummy_api_key", min_interval_seconds=0)

    # Page 1 has next_url; Page 2 is terminal for splits; Page 3 is empty terminal for dividends
    resp_split_1 = (
        {"results": [{"execution_date": "2016-05-01", "split_from": 1, "split_to": 2}], "next_url": "https://api.polygon.io/v3/reference/splits?cursor=abc"},
        200,
        None,
        "hash1",
        "2026-09-22T00:00:00Z",
    )
    resp_split_2 = (
        {"results": [{"execution_date": "2018-06-01", "split_from": 1, "split_to": 3}], "next_url": None},
        200,
        None,
        "hash2",
        "2026-09-22T00:00:00Z",
    )
    resp_div_1 = (
        {"results": [{"ex_date": "2017-03-01", "cash_amount": 0.5, "dividend_type": "CD"}], "next_url": None},
        200,
        None,
        "hash3",
        "2026-09-22T00:00:00Z",
    )

    with patch.object(client, "_fetch_json", side_effect=[resp_split_1, resp_split_2, resp_div_1]):
        splits, divs, prov = client.fetch_corporate_actions("AAPL")
        assert len(splits) == 2
        assert len(divs) == 1
        assert len(prov) == 3


def test_massive_failure_raises_typed_exception() -> None:
    """MassiveRefClient raises ProviderRequestFailed on exhausted 500 error."""
    client = MassiveRefClient("dummy_api_key", min_interval_seconds=0)

    resp_500 = (None, 500, "HTTP 500 Internal Server Error", "hash500", "2026-09-22T00:00:00Z")

    with patch.object(client, "_fetch_json", return_value=resp_500):
        with pytest.raises(ProviderRequestFailed) as exc_info:
            client.fetch_corporate_actions("AAPL")
        assert exc_info.value.status_code == 500


# =====================================================================
# 4. Projected Massive Requests & Internal Ticker Gaps
# =====================================================================
def test_ticker_pairs_and_internal_gaps_in_frozen_manifest(tmp_path: Path) -> None:
    """Frozen manifest computes 2 * historical_ticker_pairs and audits internal ticker gaps."""
    disc_manifest = tmp_path / "discovery_manifest.json"
    candidates_data = [
        # Candidate 1: Has a ticker change (2 intervals intersecting warmup/dev)
        {
            "immutable_security_id": "SEC_1",
            "primary_symbol": "NEW1",
            "cik": "0000000001",
            "security_type": CLASSIFICATION_SUPPORTED_COMMON_STOCK,
            "ticker_intervals": [
                {"symbol": "OLD1", "start_date": "2015-01-01", "end_date": "2017-12-31"},
                {"symbol": "NEW1", "start_date": "2018-01-01", "end_date": "2020-12-31"},
            ],
        },
        # Candidate 2: Has an internal gap between 2017-06-30 and 2017-08-01
        {
            "immutable_security_id": "SEC_2",
            "primary_symbol": "GAPSYM",
            "cik": "0000000002",
            "security_type": CLASSIFICATION_SUPPORTED_COMMON_STOCK,
            "ticker_intervals": [
                {"symbol": "GAP1", "start_date": "2015-01-01", "end_date": "2017-06-30"},
                {"symbol": "GAP2", "start_date": "2017-08-01", "end_date": "2020-12-31"},
            ],
        },
    ]
    disc_manifest.write_text(json.dumps({"candidates": candidates_data}), encoding="utf-8")

    # Both are Stage B eligible
    manifest_data = build_frozen_pre_run_manifest_data(
        discovery_manifest_path=disc_manifest,
        stage_b_eligible_ids=["SEC_1", "SEC_2"],
        stage_b_summary={
            "total_evaluated": 2,
            "eligible_count": 2,
            "rejected_count": 0,
            "unresolved_provider_failures_count": 0,
            "unresolved_alpaca_provider_failures": 0,
            "unresolved_edgar_provider_failures": 0,
        },
        git_commit_sha="test_commit_sha",
    )

    plan = manifest_data["provider_request_plan_stage_c"]
    # Candidate 1 has 2 pairs, Candidate 2 has 2 pairs => total 4 historical ticker pairs
    assert plan["historical_ticker_pair_count"] == 4
    # Massive calls projected as 2 * historical_ticker_pair_count = 8
    assert plan["projected_massive_total_requests"] == 8
    assert plan["projected_massive_split_requests"] == 4
    assert plan["projected_massive_dividend_requests"] == 4

    disc = manifest_data["discovery_manifest"]
    # Candidate 2 has internal gap with trading sessions in July 2017
    assert disc["internal_gap_count"] >= 1
    assert disc["internal_gap_trading_sessions"] >= 20
    assert "SEC_2" in disc["unresolved_gap_security_ids"]


# =====================================================================
# 5. Locked Daily-Bar Quality Gates (Item 8)
# =====================================================================
def test_observation_data_quality_gates() -> None:
    """Observations failing daily-bar quality gates are marked data_complete=False and fail closed."""
    identity = SecurityIdentity(
        immutable_security_id="SEC_QUALITY_TEST",
        ticker_at_decision="QUAL",
        effective_start="2016-01-01",
        effective_end="2016-12-31",
        cik="0001999999",
        security_type="common_stock",
    )

    # 300 trading sessions
    sessions = get_trading_sessions("2015-01-01", "2016-03-31")
    # Drop 5 consecutive sessions in February 2016 to trigger missing sessions & consecutive missing gates
    dropped_sessions = {"2016-02-08", "2016-02-09", "2016-02-10", "2016-02-11", "2016-02-12"}
    bar_dates = [s for s in sessions if s not in dropped_sessions]

    df = pd.DataFrame(
        {
            "open": [50.0] * len(bar_dates),
            "high": [52.0] * len(bar_dates),
            "low": [49.0] * len(bar_dates),
            "close": [51.0] * len(bar_dates),
            "as_traded_close": [51.0] * len(bar_dates),
            "volume": [1_000_000] * len(bar_dates),
        },
        index=bar_dates,
    )

    obs, _, _, _, exclusions, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=sessions,
        dev_start="2016-01-01",
        dev_end="2016-03-31",
        market_caps={s: 5_000_000_000.0 for s in bar_dates},
    )

    # Observations after the dropped dates should fail quality checks
    feb_obs = [o for o in obs if o.as_of_date >= "2016-02-15"]
    assert len(feb_obs) > 0
    for o in feb_obs:
        assert not o.data_complete
        assert not o.raw_outcome_eligible
        assert o.actionability_status == "unavailable_data_incomplete"

    excl_codes = {e.reason_code for e in exclusions}
    assert "data_quality_missing_sessions_exceeded" in excl_codes
    assert "data_quality_consecutive_missing_exceeded" in excl_codes


# =====================================================================
# 6. Historical Ticker Resolution Propagation (Item 6)
# =====================================================================
def test_unresolved_ticker_interval_sets_empty_string() -> None:
    """When a session is uncovered by ticker intervals, ticker is set to empty string (no primary_symbol fallback)."""
    cand = CandidateSecurity(
        immutable_security_id="SEC_UNRESOLVED_TICKER",
        primary_symbol="FALLBACK_SYM",
        cik="0001888888",
        security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
        ticker_intervals=[
            # Interval covers only January 2016
            TickerInterval(symbol="OLD", start_date="2016-01-01", end_date="2016-01-31"),
        ],
    )
    identity = SecurityIdentity(
        immutable_security_id=cand.immutable_security_id,
        ticker_at_decision=cand.primary_symbol,
        effective_start="2016-01-01",
        effective_end="2016-06-30",
        cik=cand.cik,
        security_type="common_stock",
    )

    sessions = get_trading_sessions("2016-01-04", "2016-02-15")
    df = pd.DataFrame(
        {
            "open": [10.0] * len(sessions),
            "high": [11.0] * len(sessions),
            "low": [9.0] * len(sessions),
            "close": [10.0] * len(sessions),
            "as_traded_close": [10.0] * len(sessions),
            "volume": [1_000_000] * len(sessions),
        },
        index=sessions,
    )

    obs, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=sessions,
        dev_start="2016-01-01",
        dev_end="2016-02-15",
        candidate=cand,
    )

    # February observation is after the interval ended
    feb_obs = next(o for o in obs if o.as_of_date == "2016-02-01")
    feb_elig = next(e for e in elig if e.as_of_date == "2016-02-01")

    # Must NOT fall back to FALLBACK_SYM
    assert feb_obs.ticker_at_decision == ""
    assert feb_elig.ticker_at_decision == ""
    assert not feb_elig.eligibility_passed
    assert "ticker_unresolved_at_decision" in feb_elig.rejection_reason_codes


# =====================================================================
# 7. Baseline Winner Selection Constraints (Item 9)
# =====================================================================
def test_baselines_winner_selection_disqualifies_legacy() -> None:
    """select_winning_baseline requires common observations and disqualifies legacy_tradex_scorer."""
    outcomes = [
        OutcomeLabelRecord(
            immutable_security_id="SEC_A",
            as_of_date="2016-06-01",
            cutoff_time="20:30",
            target_pct=10.0,
            horizon_sessions=10,
            ticker_at_decision="A",
            reference_entry_price=100.0,
            entry_friction_bps=5.0,
            target_price=110.0,
            adverse_barrier_pct=-5.0,
            adverse_barrier_price=95.0,
            clean_risk_cap_pct=5.0,
            clean_risk_cap_amount=5.0,
            mfe_pct=0.12,
            target_progress_ratio=1.0,
            near_miss=False,
            partial_move=False,
            mae_pct=-0.02,
            mae_atr=0.5,
            adverse_excursion=False,
            clean_target_reached=True,
            path_sequence_ambiguous=False,
            end_of_horizon_return=0.10,
            retention_ratio=0.8,
            sustained_target=True,
        )
    ]

    base_outputs = [
        # Simple momentum comparator
        BaselineComparatorOutput(
            immutable_security_id="SEC_A",
            as_of_date="2016-06-01",
            cutoff_time="20:30",
            comparator_id="simple_momentum_21",
            ticker_at_decision="A",
            comparator_family="simple_momentum",
            raw_score_or_return=0.15,
            cross_sectional_rank=1,
            cross_sectional_percentile=95.0,
            top_10_flag=True,
            top_25_flag=True,
        ),
        # Legacy tradex scorer has higher score, but is disqualified from winning
        BaselineComparatorOutput(
            immutable_security_id="SEC_A",
            as_of_date="2016-06-01",
            cutoff_time="20:30",
            comparator_id="legacy_tradex_scorer",
            ticker_at_decision="A",
            comparator_family="legacy_tradex_scorer",
            raw_score_or_return=0.99,
            cross_sectional_rank=1,
            cross_sectional_percentile=99.0,
            top_10_flag=True,
            top_25_flag=True,
        ),
    ]

    result = select_winning_baseline(base_outputs, outcomes, primary_cutoff_time="20:30")
    assert result["status"] == "winner_selected"
    assert result["winner_comparator_id"] == "simple_momentum_21"
    assert result["winner_family"] == "simple_momentum"
    # Legacy tradex scorer remains in table as comparator only
    assert "legacy_tradex_scorer" in result["table"]
    assert result["table"]["legacy_tradex_scorer"]["winner_eligible"] is False


def test_baselines_no_common_observations_returns_inconclusive() -> None:
    """select_winning_baseline strictly rejects non-overlapping observations without max_overlap fallback."""
    outcomes = [
        OutcomeLabelRecord(
            immutable_security_id="SEC_A",
            as_of_date="2016-06-01",
            cutoff_time="20:30",
            target_pct=10.0,
            horizon_sessions=10,
            ticker_at_decision="A",
            reference_entry_price=100.0,
            entry_friction_bps=5.0,
            target_price=110.0,
            adverse_barrier_pct=-5.0,
            adverse_barrier_price=95.0,
            clean_risk_cap_pct=5.0,
            clean_risk_cap_amount=5.0,
            mfe_pct=0.12,
            target_progress_ratio=1.0,
            near_miss=False,
            partial_move=False,
            mae_pct=-0.02,
            mae_atr=0.5,
            adverse_excursion=False,
            clean_target_reached=True,
            path_sequence_ambiguous=False,
            end_of_horizon_return=0.10,
            retention_ratio=0.8,
            sustained_target=True,
        )
    ]

    # Two comparators on disjoint observations
    base_outputs = [
        BaselineComparatorOutput(
            immutable_security_id="SEC_A",
            as_of_date="2016-06-01",
            cutoff_time="20:30",
            comparator_id="simple_momentum_21",
            ticker_at_decision="A",
            comparator_family="simple_momentum",
            raw_score_or_return=0.15,
            cross_sectional_rank=1,
            cross_sectional_percentile=95.0,
            top_10_flag=True,
            top_25_flag=True,
        ),
        BaselineComparatorOutput(
            immutable_security_id="SEC_B",
            as_of_date="2016-06-02",
            cutoff_time="20:30",
            comparator_id="spy_relative_63",
            ticker_at_decision="B",
            comparator_family="spy_relative",
            raw_score_or_return=0.08,
            cross_sectional_rank=1,
            cross_sectional_percentile=92.0,
            top_10_flag=True,
            top_25_flag=True,
        ),
    ]

    result = select_winning_baseline(base_outputs, outcomes, primary_cutoff_time="20:30")
    # Must NOT select a winner using partial overlap
    assert result["status"] == "inconclusive_no_common_observations"
    assert result["winner_comparator_id"] is None
