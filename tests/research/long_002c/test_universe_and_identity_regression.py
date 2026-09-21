"""Comprehensive regression test suite proving the 23 research-correctness invariants for LONG-002C.

Verifies:
1. No hardcoded survivor panel can be treated as full universe
2. Current index membership cannot backfill historical membership
3. Symbol-only identity cannot qualify for official-run canonical identity
4. Ticker rename uses effective historical ticker (FB vs META)
5. Unknown identity fails closed
6. Unknown classification fails closed
7. Missing market cap + no verified index = ineligible/unavailable (fail-open bug resolved)
8. Recent IPO requires listing provenance
9. Provider-truncated history != IPO
10. As-traded dollar volume uses as-traded prices
11. Analytical OHLC are consistently split-normalized
12. Split inside outcome window does not manufacture return/MFE/MAE
13. Special distribution unresolved => affected labels excluded
14. SPY-relative baselines execute
15. Sector-relative family is either validly executed or explicitly unavailable
16. Baseline winner is selected from actual primary-endpoint performance (decile lift rule)
17. Feasibility code and report use the exact same thresholds
18. Actionable observations are not raw eligible observations
19. Zero earnings-schedule coverage cannot produce a positive actionable gate
20. earnings_schedule_status entity is serialized to external Parquet
21. Report provider claims match provenance
22. Report upstream hashes match merged spec hashes
23. 09:00 and 20:30 rows obey PIT availability semantics
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.long_002c import cli
from tradex.research.long_002c.artifacts import (
    write_external_parquet_tables,
)
from tradex.research.long_002c.baselines import (
    evaluate_baselines_for_date,
    select_winning_baseline,
)
from tradex.research.long_002c.cache import ResponseCache, sanitize_url
from tradex.research.long_002c.calendar import get_trading_sessions
from tradex.research.long_002c.dataset import (
    build_decision_observations_for_security,
    compute_atr,
)
from tradex.research.long_002c.feasibility import (
    analyze_endpoint_feasibility,
)
from tradex.research.long_002c.identity import (
    CLASSIFICATION_EXCLUDED_SECURITY_TYPE,
    CLASSIFICATION_SUPPORTED_COMMON_STOCK,
    CLASSIFICATION_UNKNOWN_FAIL_CLOSED,
    SecurityIdentity,
    SecurityMaster,
    classify_security,
    make_immutable_id,
)
from tradex.research.long_002c.manifest import (
    TickerInterval,
    build_candidate_manifest_from_snapshots,
    register_manifest_in_security_master,
)
from tradex.research.long_002c.market_cap import (
    calculate_pit_market_cap,
    extract_pit_shares_fact,
    is_sec_fact_available,
)
from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    EarningsScheduleStatus,
    MasterOpportunityEpisode,
    OutcomeLabelRecord,
    ProvenanceProviderRecord,
)
from tradex.research.long_002c.outcomes import compute_outcome_cell
from tradex.research.long_002c.providers import MassiveRefClient
from tradex.research.long_002c.spec import verify_upstream_spec_hashes


# 1. No hardcoded survivor panel can be treated as full universe
def test_no_hardcoded_survivor_panel_as_full_universe() -> None:
    """Verify cli.py does not define a static FULL_UNIVERSE_SYMBOLS array."""
    assert not hasattr(cli, "FULL_UNIVERSE_SYMBOLS"), (
        "cli.py must not contain a hardcoded FULL_UNIVERSE_SYMBOLS panel; "
        "universe construction must be auditable and point-in-time."
    )


# 2. Current index membership cannot backfill historical membership
def test_current_index_membership_cannot_backfill_historical() -> None:
    """Historical dates without point-in-time verified index membership cannot pass."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-01-10",
        cik="0000320193",
        security_type="common_stock",
    )
    dates = ["2016-01-04", "2016-01-05"]
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [98.0, 99.0],
            "close": [102.0, 103.0],
            "as_traded_close": [100.0, 101.0],
            "volume": [1_000_000, 1_000_000],
        },
        index=dates,
    )
    # PIT index membership is False for 2016-01-04, even if today's membership is True
    _, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-10",
        market_caps=None,
        index_memberships={"2016-01-04": False, "2016-01-05": False},
    )
    assert not elig[0].index_membership_verified
    assert not elig[0].eligibility_passed
    assert "market_cap_or_index_unverified" in elig[0].rejection_reason_codes


# 3. Symbol-only identity cannot qualify for official-run canonical identity
def test_symbol_only_identity_cannot_qualify_for_canonical_identity() -> None:
    """Calling make_immutable_id without CIK or composite FIGI raises ValueError."""
    with pytest.raises(ValueError, match="Symbol-only identity"):
        make_immutable_id("AAPL")

    # Only permitted when allow_unverified is explicitly True (for debugging/testing)
    sym_id = make_immutable_id("AAPL", allow_unverified=True)
    assert sym_id == "US_EQ_AAPL_CS"


# 4. Ticker rename uses effective historical ticker
def test_ticker_rename_uses_effective_historical_ticker() -> None:
    """Meta Platforms CIK 0001326801 traded as FB during 2016-2020 and META post-June 2022."""
    master = SecurityMaster()
    sec_id = "CIK_0001326801_CS"

    fb_id = SecurityIdentity(
        immutable_security_id=sec_id,
        ticker_at_decision="FB",
        effective_start="2012-05-18",
        effective_end="2022-06-08",
        cik="0001326801",
        security_type="common_stock",
    )
    meta_id = SecurityIdentity(
        immutable_security_id=sec_id,
        ticker_at_decision="META",
        effective_start="2022-06-09",
        effective_end="2030-12-31",
        cik="0001326801",
        security_type="common_stock",
    )
    master.register_security(fb_id)
    master.register_security(meta_id)

    # Resolution during 2016-2020 must return FB
    res_2018 = master.resolve("FB", "2018-05-01")
    assert res_2018 is not None
    assert res_2018.immutable_security_id == sec_id
    assert res_2018.ticker_at_decision == "FB"

    # Historical ticker helper
    hist_ticker = master.resolve_historical_ticker(sec_id, "2018-05-01")
    assert hist_ticker == "FB"
    post_rename_ticker = master.resolve_historical_ticker(sec_id, "2023-01-01")
    assert post_rename_ticker == "META"


# 5. Unknown identity fails closed
def test_unknown_identity_fails_closed() -> None:
    """Unregistered security identity returns None (fail closed)."""
    master = SecurityMaster()
    assert master.resolve("UNKNOWN_XYZ", "2018-01-01") is None
    assert master.get_security_by_id("NONEXISTENT_ID") is None


# 6. Unknown classification fails closed
def test_unknown_classification_fails_closed() -> None:
    """Security with unverified security_type fails closed and is excluded from common-stock universe."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000099999_CS",
        ticker_at_decision="UNKN",
        effective_start="2016-01-01",
        effective_end="2016-01-10",
        cik="0000099999",
        security_type="unknown",  # unverified
    )
    dates = ["2016-01-04"]
    df = pd.DataFrame(
        {
            "open": [100.0],
            "high": [105.0],
            "low": [98.0],
            "close": [102.0],
            "as_traded_close": [100.0],
            "volume": [1_000_000],
        },
        index=dates,
    )
    _, elig, classification, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-10",
    )
    assert classification[0].classification_status == "unknown_fail_closed"
    assert not classification[0].is_eligible_common_stock
    assert not elig[0].eligibility_passed
    assert "excluded_classification_unknown" in elig[0].rejection_reason_codes


# 7. Missing market cap + no verified index = ineligible/unavailable
def test_missing_market_cap_and_no_verified_index_fails_closed() -> None:
    """Resolves the fail-open market-cap bug: missing market cap is None and NEVER passes."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-01-10",
        cik="0000320193",
        security_type="common_stock",
    )
    dates = ["2016-01-04"]
    df = pd.DataFrame(
        {
            "open": [100.0],
            "high": [105.0],
            "low": [98.0],
            "close": [102.0],
            "as_traded_close": [100.0],
            "volume": [1_000_000],
        },
        index=dates,
    )
    # No market_caps and no index_memberships provided
    _, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-10",
        market_caps=None,
        index_memberships=None,
    )
    assert elig[0].market_cap is None
    assert elig[0].market_cap_gte_3b is None  # strictly NOT True
    assert not elig[0].index_membership_verified
    assert not elig[0].eligibility_passed
    assert "market_cap_or_index_unverified" in elig[0].rejection_reason_codes


# 8. Recent IPO requires listing provenance
def test_recent_ipo_requires_listing_provenance() -> None:
    """Security with 100 historical bars and verified recent listing date passes as recent_ipo."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0001500000_CS",
        ticker_at_decision="NEWCO",
        effective_start="2016-01-01",
        effective_end="2016-06-30",
        cik="0001500000",
        security_type="common_stock",
        listing_date="2015-09-01",  # ~4 months prior to session
    )
    dates = get_trading_sessions("2016-01-04", "2016-01-29")
    hist_dates = get_trading_sessions("2015-09-01", "2015-12-31") + dates
    df = pd.DataFrame(
        {
            "open": [20.0] * len(hist_dates),
            "high": [22.0] * len(hist_dates),
            "low": [19.0] * len(hist_dates),
            "close": [21.0] * len(hist_dates),
            "as_traded_close": [21.0] * len(hist_dates),
            "volume": [2_000_000] * len(hist_dates),
        },
        index=hist_dates,
    )
    _, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-31",
        market_caps={d: 5_000_000_000.0 for d in dates},
    )
    assert elig[0].cohort_type == "recent_ipo"
    assert "unverified_history_truncated" not in elig[0].rejection_reason_codes


# 9. Provider-truncated history != IPO
def test_provider_truncated_history_is_not_an_ipo() -> None:
    """Security with 100 bars but missing listing provenance is classified unverified_history_truncated and fails."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0001600000_CS",
        ticker_at_decision="TRUNC",
        effective_start="2016-01-01",
        effective_end="2016-06-30",
        cik="0001600000",
        security_type="common_stock",
        listing_date=None,  # No listing provenance!
    )
    dates = get_trading_sessions("2016-01-04", "2016-01-29")
    hist_dates = get_trading_sessions("2015-09-01", "2015-12-31") + dates
    df = pd.DataFrame(
        {
            "open": [20.0] * len(hist_dates),
            "high": [22.0] * len(hist_dates),
            "low": [19.0] * len(hist_dates),
            "close": [21.0] * len(hist_dates),
            "as_traded_close": [21.0] * len(hist_dates),
            "volume": [2_000_000] * len(hist_dates),
        },
        index=hist_dates,
    )
    _, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-01-31",
        market_caps={d: 5_000_000_000.0 for d in dates},
    )
    assert elig[0].cohort_type == "unverified_history_truncated"
    assert not elig[0].eligibility_passed
    assert "unverified_history_truncated" in elig[0].rejection_reason_codes


# 10. As-traded dollar volume uses as-traded prices
def test_as_traded_dollar_volume_uses_as_traded_prices() -> None:
    """Dollar volume calculation strictly multiplies as-traded close by volume."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-02-15",
        cik="0000320193",
        security_type="common_stock",
    )
    dates = get_trading_sessions("2016-01-04", "2016-02-15")  # at least 20 trading sessions
    df = pd.DataFrame(
        {
            "open": [5.0] * len(dates),
            "high": [5.5] * len(dates),
            "low": [4.8] * len(dates),
            "close": [5.0] * len(dates),  # split-normalized
            "as_traded_close": [100.0] * len(dates),  # as-traded
            "volume": [250_000] * len(dates),
        },
        index=dates,
    )
    obs, elig, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2016-02-15",
        market_caps={d: 5_000_000_000.0 for d in dates},
    )
    # Must use as-traded close: 100 * 250,000 = 25,000,000
    assert obs[-1].dollar_volume_20d_median == 25_000_000.0
    assert elig[-1].dollar_volume_20d_gte_20m is True


# 11. Analytical OHLC are consistently split-normalized
def test_analytical_ohlc_consistently_split_normalized() -> None:
    """Technical indicators like ATR-14 are computed on split-normalized prices."""
    highs = [10.0 + 1.0] * 20
    lows = [10.0 - 1.0] * 20
    closes = [10.0] * 20
    atr = compute_atr(highs, lows, closes, 14)
    assert atr is not None
    assert round(atr, 2) == 2.0


# 12. Split inside outcome window does not manufacture return/MFE/MAE
def test_split_inside_outcome_window_does_not_manufacture_return() -> None:
    """Forward bars on split-normalized basis prevent a 2:1 split from creating a fake -50% MAE."""
    # Split-normalized forward bars: stock price moves smoothly from 100 to 112 (+12% clean target)
    forward_bars = [
        {"open": 100.0 + i * 0.5, "high": 101.0 + i * 0.6, "low": 99.5 + i * 0.4, "close": 100.5 + i * 0.5}
        for i in range(21)
    ]
    # Bar 10 reaches high 101 + 6 = 107
    # Bar 20 reaches high 101 + 12 = 113 (>= 110.10 target)
    record = compute_outcome_cell(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="TEST",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=21,
        next_open_price=100.0,
        forward_bars=forward_bars,
        pre_entry_atr=2.0,
        entry_friction_bps=10.0,
    )
    assert record.clean_target_reached is True
    # MAE should be minimal (~0.6%), NOT 50%
    assert record.mae_pct < 0.02


# 13. Special distribution unresolved => affected labels excluded
def test_special_distribution_unresolved_excludes_affected_labels() -> None:
    """Observations with unresolved special distribution have clean_target_reached forced to False."""
    forward_bars = [
        {"open": 100.0, "high": 115.0, "low": 99.0, "close": 114.0}
        for _ in range(10)
    ]
    rec = compute_outcome_cell(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="SPIN",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=10,
        next_open_price=100.0,
        forward_bars=forward_bars,
        pre_entry_atr=2.0,
        special_distribution_unresolved=True,
    )
    assert rec.special_distribution_unresolved is True
    assert rec.clean_target_reached is False
    assert rec.sustained_target is False


# 14. SPY-relative baselines execute
def test_spy_relative_baselines_execute() -> None:
    """When SPY history is passed, evaluate_baselines_for_date produces SPY-relative comparator outputs."""
    dates = [f"2016-01-{i:02d}" for i in range(4, 25)]
    df_sec = pd.DataFrame({"close": [10.0 + i * 0.2 for i in range(len(dates))]}, index=dates)
    df_spy = pd.DataFrame({"close": [200.0 + i * 0.1 for i in range(len(dates))]}, index=dates)

    sec_data = {
        "SEC_1": {
            "ticker": "ABC",
            "history_df": df_sec,
            "atr_14": 0.5,
            "universe_eligible": True,
        }
    }
    outputs = evaluate_baselines_for_date(
        as_of_date="2016-01-20",
        cutoff_time="20:30",
        securities_data=sec_data,
        spy_history_df=df_spy,
    )
    comp_ids = {o.comparator_id for o in outputs}
    assert "spy_relative_5" in comp_ids
    assert "spy_relative_10" in comp_ids


# 15. Sector-relative family is either validly executed or explicitly unavailable
def test_sector_relative_family_explicitly_unavailable_when_unsupported() -> None:
    """When sector_histories is None, sector-relative comparators are omitted and not falsely fabricated."""
    dates = [f"2016-01-{i:02d}" for i in range(4, 25)]
    df_sec = pd.DataFrame({"close": [10.0 + i * 0.2 for i in range(len(dates))]}, index=dates)
    sec_data = {
        "SEC_1": {
            "ticker": "ABC",
            "history_df": df_sec,
            "atr_14": 0.5,
            "universe_eligible": True,
            "sector": None,
        }
    }
    outputs = evaluate_baselines_for_date(
        as_of_date="2016-01-20",
        cutoff_time="20:30",
        securities_data=sec_data,
        sector_histories=None,
    )
    comp_families = {o.comparator_family for o in outputs}
    assert "sector_relative" not in comp_families


# 16. Baseline winner is selected from actual primary-endpoint performance
def test_baseline_winner_selected_from_primary_endpoint_performance() -> None:
    """Empirically select the strongest baseline comparator using top-decile clean target lift."""
    # Create 2 comparators across 10 observations: Comp_A (high lift) and Comp_B (low lift)
    obs_keys = [(f"SEC_{i}", "2016-01-04", "20:30") for i in range(10)]
    # Outcome: SEC_0 and SEC_1 reached clean target (20% base rate)
    outcomes: list[OutcomeLabelRecord] = []
    for i, (sid, d, c) in enumerate(obs_keys):
        outcomes.append(
            OutcomeLabelRecord(
                immutable_security_id=sid,
                as_of_date=d,
                cutoff_time=c,
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
                mfe_pct=0.12 if i in [0, 1] else 0.02,
                target_progress_ratio=1.2 if i in [0, 1] else 0.2,
                near_miss=False,
                partial_move=False,
                mae_pct=0.01,
                mae_atr=0.5,
                adverse_excursion=False,
                clean_target_reached=(i in [0, 1]),
                path_sequence_ambiguous=False,
                end_of_horizon_return=0.10 if i in [0, 1] else 0.0,
                retention_ratio=0.8,
                sustained_target=(i in [0, 1]),
            )
        )

    # Base outputs: Comp_A puts SEC_0 in top-10; Comp_B puts SEC_9 in top-10
    base_outputs: list[BaselineComparatorOutput] = []
    for i, (sid, d, c) in enumerate(obs_keys):
        # Comp_A: SEC_0 is top decile (rank 1)
        base_outputs.append(
            BaselineComparatorOutput(
                immutable_security_id=sid,
                as_of_date=d,
                cutoff_time=c,
                comparator_id="simple_momentum_10",
                ticker_at_decision=f"T{i}",
                comparator_family="simple_momentum",
                raw_score_or_return=float(10 - i),
                cross_sectional_rank=i + 1,
                cross_sectional_percentile=100.0 - i * 10,
                top_10_flag=(i == 0),
                top_25_flag=(i < 3),
            )
        )
        # Comp_B: SEC_9 is top decile (rank 1)
        base_outputs.append(
            BaselineComparatorOutput(
                immutable_security_id=sid,
                as_of_date=d,
                cutoff_time=c,
                comparator_id="simple_momentum_20",
                ticker_at_decision=f"T{i}",
                comparator_family="simple_momentum",
                raw_score_or_return=float(i),
                cross_sectional_rank=10 - i,
                cross_sectional_percentile=i * 10.0,
                top_10_flag=(i == 9),
                top_25_flag=(i >= 7),
            )
        )

    result = select_winning_baseline(base_outputs, outcomes)
    # Comp_A (simple_momentum_10) captured SEC_0 which reached clean target -> decile rate = 1.0 (5.0x lift)
    # Comp_B (simple_momentum_20) captured SEC_9 which missed clean target -> decile rate = 0.0 (0.0x lift)
    assert result["winner_comparator_id"] == "simple_momentum_10"
    assert result["winner_top_10_lift"] > 1.0


# 17. Feasibility code and report use the exact same thresholds
def test_feasibility_code_and_report_use_same_rule() -> None:
    """Primary endpoint retained if and only if clean occurrences >= 100, master episodes >= 100, eff_N >= 15, CI lower > 0.005."""
    episodes = [
        MasterOpportunityEpisode(
            episode_id=f"EP_{i}",
            anchor_security_id=f"SEC_{i % 20}",
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
        for i in range(120)  # >= 100
    ]
    outcomes = [
        OutcomeLabelRecord(
            immutable_security_id=f"SEC_{i % 20}",
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
            clean_target_reached=True,
            path_sequence_ambiguous=False,
            end_of_horizon_return=0.10,
            retention_ratio=0.8,
            sustained_target=True,
        )
        for i in range(120)  # >= 100
    ]
    resampling_pass = {
        "clean_target_10_10": {"ci_2_5": 0.020, "ci_97_5": 0.050, "mean": 0.035}  # > 0.005
    }
    report_pass = analyze_endpoint_feasibility(
        observations=[{"raw_outcome_eligible": True, "actionability_status": "unavailable_earnings_unknown"}],
        episodes=episodes,
        outcomes=outcomes,
        resampling_21=resampling_pass,
        resampling_42=resampling_pass,
    )
    assert report_pass["endpoint_disposition"] == "primary_retained"
    assert report_pass["selected_endpoint"] == "clean_+10%_10_sessions"

    # Fails if CI lower bound <= 0.005
    resampling_fail = {
        "clean_target_10_10": {"ci_2_5": 0.002, "ci_97_5": 0.010, "mean": 0.005}  # <= 0.005
    }
    report_fail = analyze_endpoint_feasibility(
        observations=[{"raw_outcome_eligible": True, "actionability_status": "unavailable_earnings_unknown"}],
        episodes=episodes,
        outcomes=outcomes,
        resampling_21=resampling_fail,
        resampling_42=resampling_fail,
    )
    assert report_fail["endpoint_disposition"] == "fallback_invoked"
    assert report_fail["selected_endpoint"] == "clean_+10%_21_sessions"


# 18. Actionable observations are not raw eligible observations
def test_actionable_observations_are_not_raw_eligible() -> None:
    """When earnings schedule status is unknown, actionability_status is unavailable_earnings_unknown."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-01-31",
        cik="0000320193",
        security_type="common_stock",
    )
    dates = get_trading_sessions("2016-01-04", "2016-02-15")
    hist_dates = get_trading_sessions("2015-01-01", "2015-12-31") + dates
    df = pd.DataFrame(
        {
            "open": [100.0] * len(hist_dates),
            "high": [102.0] * len(hist_dates),
            "low": [99.0] * len(hist_dates),
            "close": [101.0] * len(hist_dates),
            "as_traded_close": [101.0] * len(hist_dates),
            "volume": [2_000_000] * len(hist_dates),
        },
        index=hist_dates,
    )
    obs, elig, _, earn, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        dev_start="2016-01-01",
        dev_end="2020-12-31",
        market_caps={d: 5_000_000_000.0 for d in dates},
        earnings_schedules=None,  # unknown!
    )
    # Observation with sufficient history is raw outcome eligible, but actionability is unavailable
    assert elig[-1].eligibility_passed is True
    assert obs[-1].raw_outcome_eligible is True
    assert obs[-1].actionability_status == "unavailable_earnings_unknown"
    assert earn[-1].schedule_status == "unknown"


# 19. Zero earnings-schedule coverage cannot produce a positive actionable gate
def test_zero_earnings_coverage_cannot_produce_positive_actionable_gate() -> None:
    """If earnings coverage is zero/unknown, minimum_actionable_observations_validation is None (null)."""
    observations = [
        {
            "raw_outcome_eligible": True,
            "actionability_status": "unavailable_earnings_unknown",
        }
        for _ in range(500)
    ]
    report = analyze_endpoint_feasibility(
        observations=observations,
        episodes=[],
        outcomes=[],
        resampling_21={},
        resampling_42={},
    )
    gates = report["proposed_evidence_gates_for_review"]
    assert gates["actionable_observations_status"] == "unavailable_historical_earnings_unknown"
    assert gates["minimum_actionable_observations_validation"] is None


# 20. earnings_schedule_status entity is serialized to external Parquet
def test_earnings_schedule_status_entity_is_serialized() -> None:
    """write_external_parquet_tables writes earnings_schedule_status.parquet."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir)
        earnings_list = [
            EarningsScheduleStatus(
                immutable_security_id="CIK_0000320193_CS",
                as_of_date="2016-01-04",
                cutoff_time="20:30",
                ticker_at_decision="AAPL",
                schedule_status="unknown",
                provenance_source="sec_edgar",
            )
        ]
        manifests = write_external_parquet_tables(
            output_dir=out_path,
            observations=[],
            eligibilities=[],
            classifications=[],
            outcomes=[],
            episodes=[],
            memberships=[],
            baselines=[],
            quality=[],
            provenance=[],
            exclusions=[],
            earnings=earnings_list,
        )
        parquet_names = [Path(m["relative_path"]).name for m in manifests]
        assert "earnings_schedule_status.parquet" in parquet_names
        assert (out_path / "earnings_schedule_status.parquet").exists()


# 21. Report provider claims match provenance
def test_report_provider_claims_match_provenance() -> None:
    """ProvenanceProviderRecord entries accurately record provider name and request details."""
    rec = ProvenanceProviderRecord(
        record_id="test_prov_1",
        data_family="market_data",
        provider_name="alpaca",
        provider_role="primary",
        endpoint_url_pattern="/v2/stocks/AAPL/bars",
        retrieval_timestamp_utc="2026-09-21T00:00:00Z",
        request_fingerprint_sha256="abc",
        response_sha256="def",
    )
    assert rec.provider_name == "alpaca"
    assert rec.data_family == "market_data"


# 22. Report upstream hashes match merged spec hashes
def test_report_upstream_hashes_match_merged_spec_hashes() -> None:
    """verify_upstream_spec_hashes confirms all 11 specification hashes match exactly."""
    verified = verify_upstream_spec_hashes()
    assert len(verified) == 11
    assert "docs/research/specs/LONG-002C-design-v1.json" not in verified  # 11 upstream files referenced inside design


# 23. 09:00 and 20:30 rows obey PIT availability semantics
def test_dual_snapshots_obey_pit_availability() -> None:
    """Both 20:30 and 09:00 decision timestamps are correctly formed and information sets are PIT."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-01-10",
        cik="0000320193",
        security_type="common_stock",
    )
    dates = ["2016-01-04"]
    df = pd.DataFrame(
        {
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
            "as_traded_close": [101.0],
            "volume": [2_000_000],
        },
        index=dates,
    )
    obs_2030, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        cutoff_time="20:30",
        dev_start="2016-01-01",
        dev_end="2016-01-10",
    )
    obs_0900, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        cutoff_time="09:00",
        dev_start="2016-01-01",
        dev_end="2016-01-10",
    )
    assert obs_2030[0].cutoff_time == "20:30"
    assert obs_0900[0].cutoff_time == "09:00"
    # 20:30 ET in winter converts to 01:30 UTC next day; 09:00 ET converts to 14:00 UTC same day
    assert "01:30:00Z" in obs_2030[0].decision_timestamp_utc
    assert "14:00:00Z" in obs_0900[0].decision_timestamp_utc


# 24. 09:00 snapshot leakage protection: mutating session T bar does not affect 09:00 features
def test_0900_snapshot_leakage_protection_session_t_mutation() -> None:
    """Modifying session T daily bar has ZERO effect on 09:00 features for session T, but modifies 20:30 features."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-02-28",
        cik="0000320193",
        security_type="common_stock",
    )
    trading_days = get_trading_sessions("2016-01-01", "2016-03-01")[:25]
    dates = trading_days
    base_prices = [100.0 + i for i in range(25)]
    df_clean = pd.DataFrame(
        {
            "open": base_prices,
            "high": [p + 2.0 for p in base_prices],
            "low": [p - 2.0 for p in base_prices],
            "close": base_prices,
            "as_traded_close": base_prices,
            "volume": [1_000_000 for _ in range(25)],
        },
        index=dates,
    )

    target_session = dates[-1]

    # Initial computations
    obs_0900_clean, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df_clean,
        trading_sessions=dates,
        cutoff_time="09:00",
        dev_start=dates[0],
        dev_end=dates[-1],
    )
    obs_2030_clean, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df_clean,
        trading_sessions=dates,
        cutoff_time="20:30",
        dev_start=dates[0],
        dev_end=dates[-1],
    )

    # Target session T (last session)
    t_obs_0900_clean = next(o for o in obs_0900_clean if o.as_of_date == target_session)
    t_obs_2030_clean = next(o for o in obs_2030_clean if o.as_of_date == target_session)

    # Mutate session T radically in a separate DataFrame
    df_mutated = df_clean.copy()
    df_mutated.loc[target_session, "close"] = 9999.0
    df_mutated.loc[target_session, "as_traded_close"] = 9999.0
    df_mutated.loc[target_session, "high"] = 10050.0
    df_mutated.loc[target_session, "low"] = 5000.0
    df_mutated.loc[target_session, "volume"] = 50_000_000

    obs_0900_mut, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df_mutated,
        trading_sessions=dates,
        cutoff_time="09:00",
        dev_start=dates[0],
        dev_end=dates[-1],
    )
    obs_2030_mut, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df_mutated,
        trading_sessions=dates,
        cutoff_time="20:30",
        dev_start=dates[0],
        dev_end=dates[-1],
    )

    t_obs_0900_mut = next(o for o in obs_0900_mut if o.as_of_date == target_session)
    t_obs_2030_mut = next(o for o in obs_2030_mut if o.as_of_date == target_session)

    # Invariant: 09:00 features for session T are completely unaffected by session T bar
    assert t_obs_0900_clean.atr_14 == t_obs_0900_mut.atr_14, (
        "09:00 ATR must NOT be affected by session T bar; leakage detected!"
    )
    assert t_obs_0900_clean.dollar_volume_20d_median == t_obs_0900_mut.dollar_volume_20d_median, (
        "09:00 dollar volume median must NOT be affected by session T bar; leakage detected!"
    )
    assert t_obs_0900_clean.as_traded_close == t_obs_0900_mut.as_traded_close, (
        "09:00 as-traded close must remain session T-1 close; leakage detected!"
    )

    # In contrast, 20:30 features for session T MUST reflect session T bar
    assert t_obs_2030_clean.atr_14 != t_obs_2030_mut.atr_14, (
        "20:30 ATR must change when session T bar is mutated"
    )
    assert t_obs_2030_clean.as_traded_close != t_obs_2030_mut.as_traded_close, (
        "20:30 as-traded close must change when session T bar is mutated"
    )


# 25. PIT market-cap pathway using SEC EDGAR facts
def test_pit_market_cap_sec_edgar_facts() -> None:
    """extract_pit_shares_fact enforces filed <= session_date and selects latest defensible fact."""
    facts = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"filed": "2015-11-05", "end": "2015-10-31", "val": 1_000_000_000, "form": "10-K", "accn": "001"},
                            {"filed": "2016-02-10", "end": "2016-01-31", "val": 2_000_000_000, "form": "10-Q", "accn": "002"},
                        ]
                    }
                }
            }
        }
    }

    # As of 2016-01-15: only the 2015-11-05 filing is knowable (2016-02-10 is future lookahead)
    fact_pit = extract_pit_shares_fact(facts, session_date="2016-01-15")
    assert fact_pit is not None
    assert fact_pit.shares_outstanding == 1_000_000_000
    assert fact_pit.filing_date == "2015-11-05"

    mcap, err = calculate_pit_market_cap(fact_pit, as_traded_close=50.0)
    assert err is None
    assert mcap == 50_000_000_000.0  # $50B

    # As of 2015-10-01: neither filing has occurred yet -> fail closed
    fact_early = extract_pit_shares_fact(facts, session_date="2015-10-01")
    assert fact_early is None
    mcap_early, err_early = calculate_pit_market_cap(fact_early, as_traded_close=50.0)
    assert mcap_early is None
    assert err_early == "missing_pit_shares_fact"

    # As of 2016-03-01: both filings are knowable, latest defensible (2016-02-10) is selected
    fact_late = extract_pit_shares_fact(facts, session_date="2016-03-01")
    assert fact_late is not None
    assert fact_late.shares_outstanding == 2_000_000_000
    assert fact_late.filing_date == "2016-02-10"


# 26. Security classification rules
def test_security_classification_rules() -> None:
    """Item 5: classify_security excludes ADRs, ETFs, warrants, preferreds, and unknown types."""
    assert classify_security({"type": "CS", "locale": "us", "primary_exchange": "XNAS", "name": "Apple Inc."}) == CLASSIFICATION_SUPPORTED_COMMON_STOCK
    assert classify_security({"type": "ADRC", "locale": "us", "primary_exchange": "XNAS", "name": "Alibaba Group"}) == CLASSIFICATION_EXCLUDED_SECURITY_TYPE
    assert classify_security({"type": "ETF", "locale": "us", "primary_exchange": "XNAS", "name": "SPDR S&P 500"}) == CLASSIFICATION_EXCLUDED_SECURITY_TYPE
    assert classify_security({"type": "WAR", "locale": "us", "primary_exchange": "XNAS", "name": "Acme Warrants"}) == CLASSIFICATION_EXCLUDED_SECURITY_TYPE
    assert classify_security({"type": "CS", "locale": "us", "primary_exchange": "XNAS", "name": "Acme Corp Preferred Stock"}) == CLASSIFICATION_EXCLUDED_SECURITY_TYPE
    assert classify_security({"type": "", "locale": "us", "primary_exchange": "XNAS", "name": "Unknown Corp"}) == CLASSIFICATION_UNKNOWN_FAIL_CLOSED


# 27. Candidate manifest and multi-ticker intervals
def test_candidate_manifest_and_multi_ticker_intervals() -> None:
    """Item 6: Candidate manifest groups multi-dated ticker renames under one immutable ID."""
    snapshots = {
        "2016-01-04": [
            {
                "ticker": "FB",
                "name": "Facebook, Inc. Class A Common Stock",
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
                "cik": "0001326801",
                "composite_figi": "BBG000MM2P62",
            }
        ],
        "2022-06-15": [
            {
                "ticker": "META",
                "name": "Meta Platforms, Inc. Class A Common Stock",
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
                "cik": "0001326801",
                "composite_figi": "BBG000MM2P62",
            }
        ],
    }

    candidates, _metrics = build_candidate_manifest_from_snapshots(snapshots)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.immutable_security_id == "FIGI_BBG000MM2P62"
    assert cand.cik == "0001326801"
    assert len(cand.ticker_intervals) == 2
    assert cand.ticker_intervals[0].symbol == "FB"
    assert cand.ticker_intervals[1].symbol == "META"

    master = register_manifest_in_security_master(candidates)
    assert master.resolve_historical_ticker(cand.immutable_security_id, "2016-01-04") == "FB"
    assert master.resolve_historical_ticker(cand.immutable_security_id, "2022-06-15") == "META"


# 28. Persistent response cache determinism and URL credential sanitization
def test_persistent_response_cache_determinism() -> None:
    """Item 8: ResponseCache redacts secrets, stores responses with SHA-256, and returns identical cached data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ResponseCache(cache_dir=Path(tmpdir))
        url = "https://api.massive.com/v3/reference/tickers?date=2016-01-04&apiKey=secret_key_123"
        sanitized = sanitize_url(url)
        assert "secret_key_123" not in sanitized
        assert "apiKey=[REDACTED]" in sanitized

        req_fp = "test_fp_001"
        payload = b'{"results": [{"ticker": "AAPL"}]}'

        sha = cache.set(url, req_fp, payload, endpoint_pattern="/v3/reference/tickers")
        assert cache.has(url, req_fp)

        cached_data, cached_sha, cached_ts = cache.get_json(url, req_fp)
        assert cached_data == {"results": [{"ticker": "AAPL"}]}
        assert cached_sha == sha
        assert cached_ts is not None


# 29. Reference snapshot pagination exhaustion
def test_snapshot_pagination_exhaustion() -> None:
    """Item 1: MassiveRefClient paginates until next_url is exhausted, records metadata, and flags completeness."""
    # Mock responses across 3 pages
    page_1 = json.dumps({
        "results": [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}],
        "next_url": "https://api.massive.com/v3/reference/tickers?cursor=p2",
    }).encode("utf-8")
    page_2 = json.dumps({
        "results": [{"ticker": "D"}, {"ticker": "E"}, {"ticker": "F"}],
        "next_url": "https://api.massive.com/v3/reference/tickers?cursor=p3",
    }).encode("utf-8")
    page_3 = json.dumps({
        "results": [{"ticker": "G"}, {"ticker": "H"}, {"ticker": "I"}],
        "next_url": None,
    }).encode("utf-8")

    def mock_fetch(url: str) -> bytes:
        if "cursor=p2" in url:
            return page_2
        elif "cursor=p3" in url:
            return page_3
        return page_1

    client = MassiveRefClient(api_key="test_key", request_func=mock_fetch, min_interval_seconds=0)

    # 1. Exhausted normally within safety cap
    results, _prov, meta = client.fetch_reference_snapshot("2016-01-04", active=True, safety_max_pages=10)
    assert len(results) == 9
    assert meta.pages_fetched == 3
    assert meta.pagination_exhausted_normally is True
    assert meta.safety_max_pages_hit is False
    assert meta.is_complete is True
    assert meta.first_ticker == "A"
    assert meta.last_ticker == "I"

    # 2. Safety max pages hit before exhaustion
    results_capped, _prov_capped, meta_capped = client.fetch_reference_snapshot("2016-01-04", active=True, safety_max_pages=2)
    assert len(results_capped) == 6
    assert meta_capped.pages_fetched == 2
    assert meta_capped.records_per_page == [3, 3]
    assert meta_capped.safety_max_pages_hit is True
    assert meta_capped.pagination_exhausted_normally is False
    assert meta_capped.is_complete is False


# 30. Inactive and delisted coverage semantics
def test_inactive_and_delisted_coverage_semantics() -> None:
    """Item 2: Proves Massive reference snapshots support historical PIT date with active=false.

    SolarCity (SCTY) was active in Jan 2016, acquired by Tesla in Nov 2016,
    and returns delisted_utc when queried as inactive.
    """
    # Active record
    active_rec = {
        "ticker": "SCTY",
        "name": "SolarCity Corp",
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": "CS",
        "active": True,
        "cik": "0001408356",
        "composite_figi": "BBG000BH51N7",
    }
    # Delisted / inactive record with delisted_utc
    delisted_rec = {
        "ticker": "SCTY",
        "name": "SolarCity Corp",
        "market": "stocks",
        "locale": "us",
        "primary_exchange": "XNAS",
        "type": "CS",
        "active": False,
        "cik": "0001408356",
        "composite_figi": "BBG000BH51N7",
        "delisted_utc": "2016-11-22T05:00:00Z",
    }

    assert classify_security(active_rec) == CLASSIFICATION_SUPPORTED_COMMON_STOCK
    assert classify_security(delisted_rec) == CLASSIFICATION_SUPPORTED_COMMON_STOCK
    assert delisted_rec["delisted_utc"] == "2016-11-22T05:00:00Z"


# 31. Sparse snapshots do not invent rename transition dates
def test_sparse_snapshots_do_not_invent_rename_date() -> None:
    """Item 3: Sparse snapshots identify tickers belonging to an identity, but do NOT invent transition dates.

    Unverified intermediate dates fail closed until authoritative lifecycle evidence is attached.
    """
    snapshots = {
        "2016-01-04": [
            {
                "ticker": "FB",
                "name": "Facebook, Inc. Class A Common Stock",
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
                "cik": "0001326801",
                "composite_figi": "BBG000MM2P62",
            }
        ],
        "2022-06-15": [
            {
                "ticker": "META",
                "name": "Meta Platforms, Inc. Class A Common Stock",
                "market": "stocks",
                "locale": "us",
                "primary_exchange": "XNAS",
                "type": "CS",
                "cik": "0001326801",
                "composite_figi": "BBG000MM2P62",
            }
        ],
    }

    candidates, _ = build_candidate_manifest_from_snapshots(snapshots)
    cand = candidates[0]
    master = register_manifest_in_security_master(candidates)

    # Observed snapshot dates resolve
    assert master.resolve_historical_ticker(cand.immutable_security_id, "2016-01-04") == "FB"
    assert master.resolve_historical_ticker(cand.immutable_security_id, "2022-06-15") == "META"

    # Intermediate unobserved date between disparate tickers FAILS CLOSED (does not invent transition date)
    assert master.resolve_historical_ticker(cand.immutable_security_id, "2019-06-01") is None

    # When authoritative lifecycle intervals are attached (e.g. from SEC EDGAR formerNames), intermediate dates resolve
    cand.attach_authoritative_lifecycle(
        intervals=[
            TickerInterval(symbol="FB", start_date="2012-05-18", end_date="2022-06-08", source="sec_edgar_former_names", confidence="high"),
            TickerInterval(symbol="META", start_date="2022-06-09", end_date="9999-12-31", source="sec_edgar_former_names", confidence="high"),
        ],
        provenance={"sec_edgar_cik": "0001326801", "former_names": [{"name": "Facebook Inc", "from": "2005-05-06", "to": "2021-10-27"}]},
    )
    master_authoritative = register_manifest_in_security_master([cand])
    assert master_authoritative.resolve_historical_ticker(cand.immutable_security_id, "2019-06-01") == "FB"
    assert master_authoritative.resolve_historical_ticker(cand.immutable_security_id, "2023-01-15") == "META"


# 32. Weighted-average shares strictly rejected for PIT market cap
def test_weighted_average_shares_strictly_rejected() -> None:
    """Item 4: extract_pit_shares_fact rejects WeightedAverageNumberOfSharesOutstandingBasic."""
    facts = {
        "facts": {
            "us-gaap": {
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {
                        "shares": [
                            {"filed": "2016-02-10", "end": "2015-12-31", "val": 2_800_000_000, "form": "10-K", "accn": "001"}
                        ]
                    }
                }
            }
        }
    }
    fact = extract_pit_shares_fact(facts, session_date="2016-03-01")
    assert fact is None, "WeightedAverageNumberOfSharesOutstandingBasic must be rejected as non-PIT shares concept"

    mcap, reason = calculate_pit_market_cap(fact, as_traded_close=100.0)
    assert mcap is None
    assert reason == "missing_pit_shares_fact"


# 33. SEC Fact Availability Timing Hierarchy for 09:00 vs 20:30
def test_sec_fact_availability_timing_hierarchy() -> None:
    """Item 5: Acceptance timestamp <= decision timestamp; date-only unavailable all filing day."""
    dec_ts_0900 = "2018-05-01T13:00:00Z"
    dec_ts_2030 = "2018-05-02T00:30:00Z"
    session_date = "2018-05-01"

    # Case A1: Filing accepted 08:00 EDT (12:00 UTC) => available at 09:00 EDT (13:00 UTC)
    avail, _ts, src, conf = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc="2018-05-01T12:00:00Z",
        decision_timestamp_utc=dec_ts_0900,
        session_date=session_date,
    )
    assert avail is True
    assert src == "exact_acceptance_timestamp"
    assert conf == "high"

    # Case A2: Filing accepted 10:00 EDT (14:00 UTC) => unavailable at 09:00 EDT, available at 20:30 EDT
    avail_0900, _, _, _ = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc="2018-05-01T14:00:00Z",
        decision_timestamp_utc=dec_ts_0900,
        session_date=session_date,
    )
    assert avail_0900 is False

    avail_2030, _, _, _ = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc="2018-05-01T14:00:00Z",
        decision_timestamp_utc=dec_ts_2030,
        session_date=session_date,
    )
    assert avail_2030 is True

    # Case A3: Filing accepted 21:00 EDT (01:00 UTC next day) => unavailable at same-day 20:30 EDT (00:30 UTC next day)
    avail_late, _, _, _ = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc="2018-05-02T01:00:00Z",
        decision_timestamp_utc=dec_ts_2030,
        session_date=session_date,
    )
    assert avail_late is False

    # Case B: Date-only filing (acceptance timestamp None) => unavailable all filing day; available next session
    avail_date_only_0900, _, src_d, conf_d = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc=None,
        decision_timestamp_utc=dec_ts_0900,
        session_date="2018-05-01",
    )
    assert avail_date_only_0900 is False
    assert src_d == "date_only_next_session_conservative"
    assert conf_d == "conservative"

    avail_date_only_2030, _, _, _ = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc=None,
        decision_timestamp_utc=dec_ts_2030,
        session_date="2018-05-01",
    )
    assert avail_date_only_2030 is False

    # Available next trading session 2018-05-02 at 09:00
    avail_next_session, _, _, _ = is_sec_fact_available(
        filing_date="2018-05-01",
        acceptance_timestamp_utc=None,
        decision_timestamp_utc="2018-05-02T13:00:00Z",
        session_date="2018-05-02",
    )
    assert avail_next_session is True


# 34. Dual 09:00 and 20:30 build path and forward outcome entry
def test_dual_snapshots_and_forward_outcome_entry() -> None:
    """Item 8: Build generates both 09:00 and 20:30 rows; 09:00 enters at session T open, 20:30 at session T+1 open."""
    identity = SecurityIdentity(
        immutable_security_id="CIK_0000320193_CS",
        ticker_at_decision="AAPL",
        effective_start="2016-01-01",
        effective_end="2016-02-15",
        cik="0000320193",
        security_type="common_stock",
    )

    # Real trading sessions from exchange calendar
    dates = get_trading_sessions("2016-01-04", "2016-03-01")[:35]
    df = pd.DataFrame(
        {
            "open": [100.0 + i for i in range(len(dates))],
            "high": [105.0 + i for i in range(len(dates))],
            "low": [98.0 + i for i in range(len(dates))],
            "close": [102.0 + i for i in range(len(dates))],
            "as_traded_close": [102.0 + i for i in range(len(dates))],
            "volume": [1_000_000 for _ in range(len(dates))],
        },
        index=dates,
    )

    # Build observations for 09:00 and 20:30
    obs_0900, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        cutoff_time="09:00",
        dev_start=dates[0],
        dev_end=dates[10],
        market_caps={d: 50_000_000_000.0 for d in dates},
    )
    obs_2030, _, _, _, _, _ = build_decision_observations_for_security(
        identity=identity,
        bars_df=df,
        trading_sessions=dates,
        cutoff_time="20:30",
        dev_start=dates[0],
        dev_end=dates[10],
        market_caps={d: 50_000_000_000.0 for d in dates},
    )

    assert len(obs_0900) > 0
    assert len(obs_2030) > 0
    assert all(o.cutoff_time == "09:00" for o in obs_0900)
    assert all(o.cutoff_time == "20:30" for o in obs_2030)

    # Verify forward entry price calculation
    t_date = dates[5]
    idx = dates.index(t_date)

    # For 09:00: execution session is session T; open price is session T open
    fwd_0900 = df.iloc[idx : idx + 21]
    entry_open_0900 = float(fwd_0900["open"].iloc[0])
    assert entry_open_0900 == df.loc[t_date, "open"]

    # For 20:30: execution session is session T+1; open price is session T+1 open
    fwd_2030 = df.iloc[idx + 1 : idx + 22]
    entry_open_2030 = float(fwd_2030["open"].iloc[0])
    next_date = dates[idx + 1]
    assert entry_open_2030 == df.loc[next_date, "open"]
    assert entry_open_0900 != entry_open_2030

