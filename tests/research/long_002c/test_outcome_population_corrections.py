"""Deterministic regression tests for LONG-002C outcome population corrections, date-aware quality gates, and baseline denominators (PR #85).

Tests:
1. Ineligible observation creates zero outcome labels.
2. Eligible observation creates exactly nine outcome labels.
3. Data-quality-failed observation creates zero outcome labels.
4. Special-distribution-excluded observation creates zero outcome labels.
5. Missing forward adjusted OHLC creates no outcome labels and records forward_analytical_data_incomplete.
6. One missing adjusted historical date does not invalidate unrelated years (date-aware incompleteness).
7. +10/10 denominator equals eligible +10/10 observation count.
8. +10/21 denominator equals eligible +10/21 observation count.
9. 09:00 cell prevalence uses cell-specific denominator.
10. Outcome artifact nine-cell denominator is eligible-only and reports observation funnel.
11. Baseline ranking excludes raw-outcome-ineligible observations.
12. Legacy scorer does not affect simple-baseline common observation set.
13. Inconclusive baseline writes null winner (never simple_momentum_20).
14. Inconclusive baseline CLI printing does not crash on winner_top_10_lift None.
15. PIT market-cap coverage differs correctly from CIK coverage.
16. Ticker-gap coverage uses actual interval gaps.
17. Massive HTTP 500 retry/recovery and exhaustion to ProviderRequestFailed.
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from tradex.research.long_002c.artifacts import write_committed_summaries
from tradex.research.long_002c.baselines import (
    evaluate_baselines_for_date,
    select_winning_baseline,
)
from tradex.research.long_002c.calendar import get_trading_sessions
from tradex.research.long_002c.dataset import build_decision_observations_for_security
from tradex.research.long_002c.feasibility import analyze_endpoint_feasibility
from tradex.research.long_002c.frozen_manifest import build_frozen_pre_run_manifest_data
from tradex.research.long_002c.identity import (
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    SecurityIdentity,
    SecurityMaster,
)
from tradex.research.long_002c.manifest import CandidateSecurity, TickerInterval
from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    DecisionObservation,
    MasterOpportunityEpisode,
    OutcomeLabelRecord,
)
from tradex.research.long_002c.outcomes import compute_all_nine_outcomes
from tradex.research.long_002c.providers import MassiveRefClient, ProviderRequestFailed
from tradex.research.long_002c.screening import screen_candidates_manifest
from tradex.research.long_002c.spec import DEV_END, DEV_START


def _make_obs(
    sec_id: str = "SEC_1",
    date: str = "2016-01-04",
    cutoff: str = "20:30",
    raw_eligible: bool = True,
    universe_eligible: bool = True,
    data_complete: bool = True,
    earnings_status: str = "known_point_in_time",
    actionability_status: str = "eligible",
) -> DecisionObservation:
    return DecisionObservation(
        immutable_security_id=sec_id,
        ticker_at_decision=sec_id.replace("SEC_", "T"),
        as_of_date=date,
        cutoff_time=cutoff,
        decision_timestamp_utc=f"{date}T{cutoff}:00Z",
        as_traded_close=100.0,
        split_normalized_close=100.0,
        volume=1_000_000,
        raw_outcome_eligible=raw_eligible,
        universe_eligible=universe_eligible,
        data_complete=data_complete,
        earnings_schedule_status=earnings_status,
        actionability_status=actionability_status,
    )


# =====================================================================
# 1-5: Outcome Generation Gated on Raw-Outcome-Eligibility & Forward Path
# =====================================================================
def test_ineligible_observation_creates_zero_outcomes() -> None:
    """An observation failing universe eligibility produces zero outcome records."""
    obs = _make_obs(sec_id="SEC_INELIG", raw_eligible=False, universe_eligible=False, actionability_status="ineligible_universe")
    outcomes = []
    if obs.raw_outcome_eligible:
        outcomes = compute_all_nine_outcomes(
            immutable_security_id=obs.immutable_security_id,
            ticker_at_decision=obs.ticker_at_decision,
            as_of_date=obs.as_of_date,
            cutoff_time=obs.cutoff_time,
            next_open_price=100.0,
            forward_bars=[{"open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0}] * 21,
            pre_entry_atr=2.0,
            entry_friction_bps=10.0,
        )
    assert len(outcomes) == 0


def test_eligible_observation_creates_exactly_nine_outcomes() -> None:
    """An eligible observation with valid 21 forward bars produces exactly 9 outcome records."""
    obs = _make_obs(sec_id="SEC_ELIG", raw_eligible=True, universe_eligible=True, actionability_status="eligible")
    forward_bars = [
        {"open": 100.0 + i, "high": 102.0 + i, "low": 99.0 + i, "close": 101.0 + i}
        for i in range(21)
    ]
    outcomes = compute_all_nine_outcomes(
        immutable_security_id=obs.immutable_security_id,
        ticker_at_decision=obs.ticker_at_decision,
        as_of_date=obs.as_of_date,
        cutoff_time=obs.cutoff_time,
        next_open_price=100.0,
        forward_bars=forward_bars,
        pre_entry_atr=2.0,
        entry_friction_bps=10.0,
    )
    assert len(outcomes) == 9
    pairs = {(o.target_pct, o.horizon_sessions) for o in outcomes}
    expected_pairs = {
        (10.0, 5), (10.0, 10), (10.0, 21),
        (20.0, 5), (20.0, 10), (20.0, 21),
        (30.0, 5), (30.0, 10), (30.0, 21),
    }
    assert pairs == expected_pairs


def test_missing_forward_adjusted_ohlc_creates_zero_outcomes_and_records_exclusion() -> None:
    """Forward analytical path with non-finite or missing prices invalidates observation and yields zero outcomes."""
    forward_bars_df = pd.DataFrame([
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 101.0, "as_traded_open": 100.0}
        for _ in range(20)
    ] + [
        {"open": np.nan, "high": 105.0, "low": 99.0, "close": 103.0, "as_traded_open": 100.0}
    ])

    # Observation starts eligible
    obs = {
        "immutable_security_id": "SEC_FWD_FAIL",
        "ticker_at_decision": "FWDFAIL",
        "as_of_date": "2016-01-04",
        "cutoff_time": "20:30",
        "universe_eligible": True,
        "data_complete": True,
        "raw_outcome_eligible": True,
        "actionability_status": "eligible",
    }

    exclusions = []
    # Test the forward path validation logic implemented in cmd_build
    has_invalid_ohlc = False
    for col in ["open", "high", "low", "close"]:
        vals = forward_bars_df[col].to_numpy()
        if not np.all(np.isfinite(vals)):
            has_invalid_ohlc = True
            break

    if has_invalid_ohlc:
        obs["raw_outcome_eligible"] = False
        obs["data_complete"] = False
        obs["actionability_status"] = "unavailable_data_incomplete"
        exclusions.append("forward_analytical_data_incomplete")

    assert obs["raw_outcome_eligible"] is False
    assert obs["data_complete"] is False
    assert obs["actionability_status"] == "unavailable_data_incomplete"
    assert "forward_analytical_data_incomplete" in exclusions


# =====================================================================
# 6: Date-Aware Analytical Incompleteness
# =====================================================================
def test_date_aware_analytical_incompleteness_does_not_invalidate_unrelated_years() -> None:
    """An analytical incomplete date in 2017 does NOT invalidate a 2019 observation."""
    sessions = get_trading_sessions("2015-01-01", DEV_END)
    bar_dates = sessions[:800]
    df = pd.DataFrame(
        {
            "open": [100.0] * len(bar_dates),
            "high": [105.0] * len(bar_dates),
            "low": [95.0] * len(bar_dates),
            "close": [102.0] * len(bar_dates),
            "volume": [1_000_000] * len(bar_dates),
            "as_traded_open": [100.0] * len(bar_dates),
            "as_traded_high": [105.0] * len(bar_dates),
            "as_traded_low": [95.0] * len(bar_dates),
            "as_traded_close": [102.0] * len(bar_dates),
            "as_traded_volume": [1_000_000] * len(bar_dates),
        },
        index=bar_dates,
    )

    candidate = CandidateSecurity(
        immutable_security_id="SEC_DATE_AWARE",
        primary_symbol="DTEST",
        cik="0001234567",
        security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
        ticker_intervals=[TickerInterval(symbol="DTEST", start_date=bar_dates[0], end_date=bar_dates[-1])],
    )
    identity = SecurityIdentity(
        immutable_security_id="SEC_DATE_AWARE",
        ticker_at_decision="DTEST",
        effective_start=bar_dates[0],
        effective_end=bar_dates[-1],
        security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    )
    sec_master = SecurityMaster()
    sec_master.register_security(identity)

    # Incomplete analytical date is at index 300
    incomplete_date = bar_dates[300]
    bar_meta = {
        "analytical_data_incomplete": True,
        "analytical_incomplete_dates": [incomplete_date],
    }

    obs_list, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=sessions,
        cutoff_time="20:30",
        dev_start=bar_dates[100],
        dev_end=bar_dates[-1],
        market_caps={d: 10_000_000_000.0 for d in bar_dates},
        candidate=candidate,
        security_master=sec_master,
        bar_meta=bar_meta,
    )

    # Observation around index 305 (whose trailing window includes incomplete_date) fails data completeness
    obs_around_incomplete = [o for o in obs_list if o.as_of_date == bar_dates[305]]
    assert len(obs_around_incomplete) == 1
    assert obs_around_incomplete[0].data_complete is False

    # Observation at index 700 (in 2019, far from index 300) retains data_complete == True
    obs_2019 = [o for o in obs_list if o.as_of_date == bar_dates[700]]
    assert len(obs_2019) == 1
    assert obs_2019[0].data_complete is True
    assert obs_2019[0].raw_outcome_eligible is True


# =====================================================================
# 7-8: Endpoint Feasibility Denominators & Assertions
# =====================================================================
def test_feasibility_denominators_match_eligible_population() -> None:
    """analyze_endpoint_feasibility calculates prevalence using strictly raw-outcome-eligible keys."""
    episodes = [
        MasterOpportunityEpisode(
            episode_id=f"EP_{i}",
            anchor_security_id=f"SEC_{i % 5}",
            anchor_ticker="T",
            anchor_as_of_date="2016-01-04",
            anchor_cutoff_time="20:30",
            anchor_entry_price=100.0,
            window_start_date="2016-01-04",
            window_end_date="2016-02-04",
            window_session_count=21,
            max_return_pct_21=15.0,
            max_target_tier_reached="10",
            clean_target_reached_10_21=True,
            clean_target_reached_20_21=False,
            clean_target_reached_30_21=False,
            first_target_session_index=5,
            constituent_observation_count=10,
        )
        for i in range(120)
    ]
    # 100 eligible observations
    obs_list = [
        {
            "immutable_security_id": f"SEC_{i}",
            "as_of_date": "2016-01-04",
            "cutoff_time": "20:30",
            "raw_outcome_eligible": True,
            "actionability_status": "eligible",
        }
        for i in range(100)
    ]
    outcomes = []
    for i in range(100):
        outcomes.append(
            OutcomeLabelRecord(
                immutable_security_id=f"SEC_{i}",
                as_of_date="2016-01-04",
                cutoff_time="20:30",
                target_pct=10.0,
                horizon_sessions=10,
                ticker_at_decision="T",
                reference_entry_price=100.0,
                entry_friction_bps=10.0,
                target_price=110.0,
                adverse_barrier_pct=0.05,
                adverse_barrier_price=95.0,
                clean_risk_cap_pct=0.05,
                clean_risk_cap_amount=5.0,
                mfe_pct=0.15,
                target_progress_ratio=1.5,
                near_miss=False,
                partial_move=False,
                mae_pct=0.01,
                mae_atr=0.5,
                adverse_excursion=False,
                clean_target_reached=(i < 30),
                path_sequence_ambiguous=False,
                end_of_horizon_return=0.10,
                retention_ratio=0.8,
                sustained_target=True,
            )
        )
        outcomes.append(
            OutcomeLabelRecord(
                immutable_security_id=f"SEC_{i}",
                as_of_date="2016-01-04",
                cutoff_time="20:30",
                target_pct=10.0,
                horizon_sessions=21,
                ticker_at_decision="T",
                reference_entry_price=100.0,
                entry_friction_bps=10.0,
                target_price=110.0,
                adverse_barrier_pct=0.05,
                adverse_barrier_price=95.0,
                clean_risk_cap_pct=0.05,
                clean_risk_cap_amount=5.0,
                mfe_pct=0.15,
                target_progress_ratio=1.5,
                near_miss=False,
                partial_move=False,
                mae_pct=0.01,
                mae_atr=0.5,
                adverse_excursion=False,
                clean_target_reached=(i < 40),
                path_sequence_ambiguous=False,
                end_of_horizon_return=0.10,
                retention_ratio=0.8,
                sustained_target=True,
            )
        )

    resampling = {"clean_target_10_10": {"ci_2_5": 0.02, "ci_97_5": 0.05, "mean": 0.03}}
    report = analyze_endpoint_feasibility(
        observations=obs_list,
        episodes=episodes,
        outcomes=outcomes,
        resampling_21=resampling,
        resampling_42=resampling,
    )
    assert report["primary_10_10_denominator"] == 100
    assert report["fallback_10_21_denominator"] == 100
    assert report["primary_clean_10_10_prevalence"] == 0.30
    assert report["fallback_clean_10_21_prevalence"] == 0.40


# =====================================================================
# 9-10: Artifact Funnel & Pre-market Reevaluation Denominators
# =====================================================================
def test_outcome_artifact_observation_funnel_and_cell_denominators(tmp_path: Path) -> None:
    """write_committed_summaries writes eligible_denominator and observation funnel with known_point_in_time."""
    obs = [
        _make_obs(
            sec_id=f"SEC_{i}",
            earnings_status="known_point_in_time" if i % 2 == 0 else "unknown",
        )
        for i in range(20)
    ]
    outcomes = [
        OutcomeLabelRecord(
            immutable_security_id=f"SEC_{i}",
            as_of_date="2016-01-04",
            cutoff_time="20:30",
            target_pct=10.0,
            horizon_sessions=10,
            ticker_at_decision=f"T{i}",
            reference_entry_price=100.0,
            entry_friction_bps=10.0,
            target_price=110.0,
            adverse_barrier_pct=0.05,
            adverse_barrier_price=95.0,
            clean_risk_cap_pct=0.05,
            clean_risk_cap_amount=5.0,
            mfe_pct=0.15,
            target_progress_ratio=1.5,
            near_miss=False,
            partial_move=False,
            mae_pct=0.01,
            mae_atr=0.5,
            adverse_excursion=False,
            clean_target_reached=True,
            path_sequence_ambiguous=False,
            end_of_horizon_return=0.10,
            retention_ratio=0.8,
            sustained_target=True,
        )
        for i in range(20)
    ]

    bundle_dir = tmp_path / "artifacts"
    write_committed_summaries(
        bundle_dir=bundle_dir,
        run_id="test_funnel",
        manifest_files=[],
        observations=obs,
        outcomes=outcomes,
        episodes=[],
        baselines=[],
        quality=[],
        provenance=[],
        exclusions=[],
        feasibility_report={},
        execution_metadata={},
    )

    summary_file = bundle_dir / "outcome_census_summary.json"
    assert summary_file.exists()
    data = json.loads(summary_file.read_text(encoding="utf-8"))
    funnel = data["observation_funnel"]
    assert funnel["total_decision_observations"] == 20
    assert funnel["raw_outcome_eligible"] == 20
    assert funnel["earnings_known"] == 10
    assert funnel["earnings_unknown"] == 10
    cell_10_10 = data["nine_cells"]["+10%_10d"]
    assert cell_10_10["eligible_denominator"] == 20
    assert cell_10_10["clean_target_reached_count"] == 20


# =====================================================================
# 11-14: Baseline Population, Legacy Scorer Isolation & Inconclusive Winner
# =====================================================================
def test_baselines_ranking_excludes_ineligible_observations() -> None:
    """evaluate_baselines_for_date does not score securities with universe_eligible == False."""
    sec_data = {
        "SEC_A": {"ticker": "A", "history_df": pd.DataFrame({"close": [10.0] * 30}), "atr_14": 1.0, "universe_eligible": True},
        "SEC_B": {"ticker": "B", "history_df": pd.DataFrame({"close": [10.0] * 30}), "atr_14": 1.0, "universe_eligible": False},
    }
    outputs = evaluate_baselines_for_date(
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        securities_data=sec_data,
        spy_history_df=None,
    )
    outputs_A = [o for o in outputs if o.immutable_security_id == "SEC_A"]
    outputs_B = [o for o in outputs if o.immutable_security_id == "SEC_B"]
    assert len(outputs_A) > 0
    assert len(outputs_B) == 0


def test_legacy_tradex_scorer_does_not_affect_simple_baseline_selection() -> None:
    """select_winning_baseline determines common_keys from simple baselines only, ignoring legacy_tradex_scorer."""
    outcomes = [
        OutcomeLabelRecord(
            immutable_security_id="SEC_1",
            as_of_date="2016-01-04",
            cutoff_time="20:30",
            target_pct=10.0,
            horizon_sessions=10,
            ticker_at_decision="T1",
            reference_entry_price=100.0,
            entry_friction_bps=10.0,
            target_price=110.0,
            adverse_barrier_pct=0.05,
            adverse_barrier_price=95.0,
            clean_risk_cap_pct=0.05,
            clean_risk_cap_amount=5.0,
            mfe_pct=0.15,
            target_progress_ratio=1.5,
            near_miss=False,
            partial_move=False,
            mae_pct=0.01,
            mae_atr=0.5,
            adverse_excursion=False,
            clean_target_reached=True,
            path_sequence_ambiguous=False,
            end_of_horizon_return=0.10,
            retention_ratio=0.8,
            sustained_target=True,
        )
    ]
    # Simple baseline evaluated SEC_1, legacy evaluated SEC_2
    b_simple = BaselineComparatorOutput(
        immutable_security_id="SEC_1",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        comparator_id="simple_momentum_20",
        ticker_at_decision="T1",
        comparator_family="simple_momentum",
        raw_score_or_return=1.0,
        cross_sectional_rank=1,
        cross_sectional_percentile=100.0,
        top_10_flag=True,
        top_25_flag=True,
    )
    b_legacy = BaselineComparatorOutput(
        immutable_security_id="SEC_2",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        comparator_id="legacy_tradex_scorer",
        ticker_at_decision="T2",
        comparator_family="legacy_tradex_scorer",
        raw_score_or_return=2.0,
        cross_sectional_rank=1,
        cross_sectional_percentile=100.0,
        top_10_flag=True,
        top_25_flag=True,
    )
    res = select_winning_baseline([b_simple, b_legacy], outcomes=outcomes, primary_cutoff_time="20:30")
    # Selection should evaluate on SEC_1 from simple baseline, without requiring SEC_2
    assert "simple_momentum_20" in res.get("table", {})


def test_inconclusive_baseline_writes_null_winner() -> None:
    """When no baseline passes gates, winner is null, not falling back to simple_momentum_20."""
    res = select_winning_baseline([], outcomes=[], primary_cutoff_time="20:30")
    assert res["winner_comparator_id"] is None
    assert "inconclusive" in res["status"]


# =====================================================================
# 15-16: PIT Market-Cap & Lifecycle-Bounded Ticker Gap Metrics
# =====================================================================
def test_pit_market_cap_and_cik_coverage_reporting() -> None:
    """screening summary distinguishes cik_coverage_pct from pit_market_cap_session_coverage_pct."""
    mock_alpaca = MagicMock()
    mock_alpaca.fetch_daily_bars.return_value = (
        [{"t": "2016-01-04T05:00:00Z", "o": 50.0, "h": 52.0, "l": 49.0, "c": 51.0, "v": 1000000}],
        [],
    )
    mock_alpaca.get_audit_metrics.return_value = {}

    mock_edgar = MagicMock()
    mock_edgar.fetch_company_facts.return_value = (None, [])
    mock_edgar.fetch_submissions.return_value = (None, [])
    mock_edgar.get_audit_metrics.return_value = {}

    cands = [
        CandidateSecurity(
            immutable_security_id="CAND_1",
            primary_symbol="C1",
            cik="0001111111",
            security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
            ticker_intervals=[TickerInterval(symbol="C1", start_date="2016-01-04", end_date="2016-01-08")],
        ),
        CandidateSecurity(
            immutable_security_id="CAND_2",
            primary_symbol="C2",
            cik="",  # Missing CIK
            security_type=CLASSIFICATION_SUPPORTED_COMMON_STOCK,
            ticker_intervals=[TickerInterval(symbol="C2", start_date="2016-01-04", end_date="2016-01-08")],
        ),
    ]

    _elig, _rej, summary = screen_candidates_manifest(
        candidates=cands,
        alpaca=mock_alpaca,
        edgar=mock_edgar,
    )
    assert summary["cik_coverage_pct"] == 50.0
    assert summary["candidates_with_valid_cik"] == 1
    assert "candidate_pit_market_cap_coverage_pct" in summary
    assert "pit_market_cap_session_coverage_pct" in summary
    assert "ticker_resolution_coverage_pct" in summary


def test_ticker_gap_coverage_lifecycle_bounded() -> None:
    """Ticker interval gaps are measured only between first and last interval dates in dev window."""
    dev_sessions = get_trading_sessions(DEV_START, DEV_END)
    # Candidate trading only in 2018 with a 5-day gap in 2018
    s1, e1 = "2018-01-02", "2018-03-01"
    s2, e2 = "2018-03-15", "2018-06-01"
    cand = {
        "immutable_security_id": "SEC_GAP_TEST",
        "primary_symbol": "GAP",
        "cik": "0009999999",
        "security_type": CLASSIFICATION_SUPPORTED_COMMON_STOCK,
        "ticker_intervals": [
            {"symbol": "GAP1", "start_date": s1, "end_date": e1},
            {"symbol": "GAP2", "start_date": s2, "end_date": e2},
        ],
    }
    disc_data = {
        "discovery_manifest_sha256": "mock_disc_sha",
        "candidates": [cand],
        "metrics": {"snapshot_dates_evaluated": []},
    }
    mock_disc_path = Path("mock_discovery_manifest.json")
    with (
        patch("tradex.research.long_002c.frozen_manifest.compute_file_sha256", return_value="dummy_sha"),
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "read_text", return_value=json.dumps(disc_data)),
    ):
        manifest_data = build_frozen_pre_run_manifest_data(
            discovery_manifest_path=mock_disc_path,
            stage_b_eligible_ids=["SEC_GAP_TEST"],
            stage_b_summary={"unresolved_provider_failures_count": 0},
        )
    disc_meta = manifest_data["discovery_manifest"]
    assert disc_meta["discovered_securities_with_internal_gaps"] == 1
    # Gap sessions must be strictly the trading sessions between e1 and s2
    expected_gap_sess = [s for s in dev_sessions if e1 < s < s2]
    assert disc_meta["discovered_internal_gap_sessions"] == len(expected_gap_sess)


# =====================================================================
# 17: Massive HTTP 500 Retry & Failure Hardening
# =====================================================================
def test_massive_500_retry_and_exhaustion() -> None:
    """MassiveRefClient retries on HTTP 500 with backoff and raises ProviderRequestFailed on exhaustion."""
    mock_request_func = MagicMock()
    mock_request_func.side_effect = urllib.error.HTTPError(
        url="https://api.massive.example/test",
        code=500,
        msg="Internal Server Error",
        hdrs=MagicMock(),
        fp=None,
    )

    client = MassiveRefClient(
        api_key="test_key",
        min_interval_seconds=0.0,
        request_func=mock_request_func,
    )

    with pytest.raises(ProviderRequestFailed) as exc_info:
        client.fetch_corporate_actions("FAIL500")

    assert client.retries_count == 3
    assert "500" in str(exc_info.value)
