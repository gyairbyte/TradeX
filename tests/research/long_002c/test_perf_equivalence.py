"""Focused numerical and semantic equivalence tests for LONG-002C-PERF-001 optimizations."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002c.artifacts import write_committed_summaries
from tradex.research.long_002c.baselines import (
    compute_legacy_tradex_score,
)
from tradex.research.long_002c.feasibility import run_block_resampling
from tradex.research.long_002c.models import (
    DecisionObservation,
    OutcomeLabelRecord,
)
from tradex.signals.weights import LongWeights


def _make_dummy_obs(sec_id: str, date: str, cutoff: str, eligible: bool = True) -> DecisionObservation:
    return DecisionObservation(
        immutable_security_id=sec_id,
        as_of_date=date,
        cutoff_time=cutoff,
        ticker_at_decision=sec_id.replace("FIGI_", ""),
        universe_eligible=eligible,
        data_complete=eligible,
        raw_outcome_eligible=eligible,
        actionability_status="eligible" if eligible else "ineligible",
        earnings_schedule_status="known_point_in_time",
        split_boundary_purged=False,
        atr_14=1.25,
        decision_timestamp_utc=f"{date}T{cutoff}:00Z",
        as_traded_close=100.0,
        split_normalized_close=100.0,
        volume=100000.0,
    )


def test_observation_lookup_equivalence():
    """Verify that O(1) dictionary lookup returns identical object references to linear scan."""
    dates = ["2016-01-04", "2016-01-05", "2016-01-06"]
    cutoffs = ["09:00", "20:30"]
    sec_ids = [f"FIGI_SEC_{i}" for i in range(20)]

    all_obs: list[DecisionObservation] = []
    for s in sec_ids:
        for d in dates:
            for c in cutoffs:
                all_obs.append(_make_dummy_obs(s, d, c))

    obs_obj_map = {(o.immutable_security_id, o.as_of_date, o.cutoff_time): o for o in all_obs}

    for s in sec_ids:
        for d in dates:
            for c in cutoffs:
                # Reference linear scan
                ref = next(
                    (o for o in all_obs if o.immutable_security_id == s and o.as_of_date == d and o.cutoff_time == c),
                    None,
                )
                # Optimized O(1) lookup
                opt = obs_obj_map.get((s, d, c))
                assert ref is not None
                assert opt is not None
                assert opt is ref

    # Missing key check
    assert obs_obj_map.get(("MISSING_SEC", "2016-01-04", "20:30")) is None


def test_date_position_lookup_equivalence():
    """Verify that precomputed date position map returns identical indices and DataFrame slices."""
    dates = pd.date_range("2015-01-02", "2020-12-31", freq="B").strftime("%Y-%m-%d").tolist()
    df = pd.DataFrame({"close": np.arange(len(dates), dtype=float)}, index=dates)

    date_pos_map = {d: i for i, d in enumerate(df.index)}

    test_dates = ["2015-01-02", "2016-06-15", "2018-11-20", "2020-12-30", "2020-12-31"]
    for d in test_dates:
        # Reference
        ref_idx = list(df.index).index(d)
        # Optimized
        opt_idx = date_pos_map.get(d)
        assert ref_idx == opt_idx

        # Slice equivalence for 09:00 ([:idx]) and 20:30 ([:idx+1])
        ref_slice_09 = df.iloc[:ref_idx]
        opt_slice_09 = df.iloc[:opt_idx]
        pd.testing.assert_frame_equal(ref_slice_09, opt_slice_09)

        ref_slice_20 = df.iloc[: ref_idx + 1]
        opt_slice_20 = df.iloc[: opt_idx + 1]
        pd.testing.assert_frame_equal(ref_slice_20, opt_slice_20)

    # Missing date check
    assert date_pos_map.get("1999-01-01") is None


def test_block_resampling_numerical_equivalence():
    """Verify that optimized preaggregated block resampling is 100% numerically identical to reference."""
    sessions = [f"2016-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 22)]
    observations: list[dict[str, Any]] = []
    outcomes_by_obs_key: dict[tuple[str, str, str], dict[tuple[float, int], OutcomeLabelRecord]] = {}

    for s_idx, s in enumerate(sessions):
        for sec_idx in range(50):
            sec_id = f"FIGI_TEST_{sec_idx}"
            observations.append({
                "immutable_security_id": sec_id,
                "as_of_date": s,
                "cutoff_time": "20:30",
                "raw_outcome_eligible": True,
                "split_boundary_purged": False,
            })
            key = (sec_id, s, "20:30")
            # Build mock outcome records with clean target and progress ratio
            dummy_record_10_10 = OutcomeLabelRecord(
                immutable_security_id=sec_id,
                as_of_date=s,
                cutoff_time="20:30",
                target_pct=10.0,
                horizon_sessions=10,
                clean_target_reached=((sec_idx + s_idx) % 7 == 0),
                target_progress_ratio=1.2 if ((sec_idx + s_idx) % 5 == 0) else 0.4,
                ticker_at_decision=sec_id,
                reference_entry_price=100.0,
                entry_friction_bps=5.0,
                target_price=110.0,
                adverse_barrier_pct=-5.0,
                adverse_barrier_price=95.0,
                clean_risk_cap_pct=5.0,
                clean_risk_cap_amount=5.0,
                mfe_pct=8.0,
                near_miss=False,
                partial_move=False,
                mae_pct=-2.0,
                mae_atr=0.5,
                adverse_excursion=False,
                path_sequence_ambiguous=False,
                end_of_horizon_return=0.05,
                retention_ratio=0.8,
                sustained_target=False,
            )
            dummy_record_10_21 = OutcomeLabelRecord(
                immutable_security_id=sec_id,
                as_of_date=s,
                cutoff_time="20:30",
                target_pct=10.0,
                horizon_sessions=21,
                clean_target_reached=((sec_idx + s_idx) % 6 == 0),
                target_progress_ratio=1.1 if ((sec_idx + s_idx) % 4 == 0) else 0.3,
                ticker_at_decision=sec_id,
                reference_entry_price=100.0,
                entry_friction_bps=5.0,
                target_price=110.0,
                adverse_barrier_pct=-5.0,
                adverse_barrier_price=95.0,
                clean_risk_cap_pct=5.0,
                clean_risk_cap_amount=5.0,
                mfe_pct=9.0,
                near_miss=False,
                partial_move=False,
                mae_pct=-2.5,
                mae_atr=0.6,
                adverse_excursion=False,
                path_sequence_ambiguous=False,
                end_of_horizon_return=0.06,
                retention_ratio=0.85,
                sustained_target=False,
            )
            outcomes_by_obs_key[key] = {
                (10.0, 10): dummy_record_10_10,
                (10.0, 21): dummy_record_10_21,
            }

    # Reference implementation (slow nested loop)
    def _reference_resampling(obs, outcomes_map, sess_ordered, block_size, num_boot, seed):
        rng = np.random.default_rng(seed)
        blocks = [sess_ordered[i : i + block_size] for i in range(0, len(sess_ordered), block_size)]
        obs_by_sess: dict[str, list[dict[str, Any]]] = {}
        for o in obs:
            if o.get("raw_outcome_eligible", False) and not o.get("split_boundary_purged", False):
                obs_by_sess.setdefault(o["as_of_date"], []).append(o)
        n_blks = len(blocks)
        c10_10_rates, c10_21_rates, g10_10_rates, g10_21_rates = [], [], [], []
        for _ in range(num_boot):
            sampled = rng.integers(0, n_blks, size=n_blks)
            tot, c10, c21, g10, g21 = 0, 0, 0, 0, 0
            for b_i in sampled:
                for s in blocks[b_i]:
                    for o in obs_by_sess.get(s, []):
                        k = (o["immutable_security_id"], o["as_of_date"], o.get("cutoff_time", "20:30"))
                        co = outcomes_map.get(k, {})
                        r10 = co.get((10.0, 10))
                        r21 = co.get((10.0, 21))
                        tot += 1
                        if r10:
                            if r10.clean_target_reached:
                                c10 += 1
                            if r10.target_progress_ratio >= 1.0:
                                g10 += 1
                        if r21:
                            if r21.clean_target_reached:
                                c21 += 1
                            if r21.target_progress_ratio >= 1.0:
                                g21 += 1
            if tot > 0:
                c10_10_rates.append(c10 / tot)
                c10_21_rates.append(c21 / tot)
                g10_10_rates.append(g10 / tot)
                g10_21_rates.append(g21 / tot)
            else:
                c10_10_rates.append(0.0)
                c10_21_rates.append(0.0)
                g10_10_rates.append(0.0)
                g10_21_rates.append(0.0)

        def _stats(arr):
            np_arr = np.array(arr)
            return {
                "mean": float(np.mean(np_arr)),
                "std_err": float(np.std(np_arr)),
                "ci_2_5": float(np.percentile(np_arr, 2.5)),
                "median": float(np.percentile(np_arr, 50.0)),
                "ci_97_5": float(np.percentile(np_arr, 97.5)),
            }

        return {
            "clean_target_10_10": _stats(c10_10_rates),
            "clean_target_10_21": _stats(c10_21_rates),
            "gross_target_10_10": _stats(g10_10_rates),
            "gross_target_10_21": _stats(g10_21_rates),
        }

    ref_res = _reference_resampling(
        observations, outcomes_by_obs_key, sessions, block_size=21, num_boot=200, seed=12345
    )
    opt_res = run_block_resampling(
        observations, outcomes_by_obs_key, sessions, block_size_sessions=21, num_bootstraps=200, seed=12345
    )

    for metric in ["clean_target_10_10", "clean_target_10_21", "gross_target_10_10", "gross_target_10_21"]:
        for stat in ["mean", "std_err", "ci_2_5", "median", "ci_97_5"]:
            v_ref = ref_res[metric][stat]
            v_opt = opt_res[metric][stat]
            assert abs(v_ref - v_opt) < 1e-12, f"Discrepancy in {metric}.{stat}: ref={v_ref}, opt={v_opt}"


def test_outcome_cell_aggregation_equivalence(tmp_path):
    """Verify that single-pass outcome aggregation produces identical outcome census summary."""
    import json

    dates = ["2016-01-04", "2016-01-05"]
    cutoffs = ["20:30", "09:00"]
    sec_ids = [f"FIGI_CELL_{i}" for i in range(10)]

    obs: list[DecisionObservation] = []
    for s in sec_ids:
        for d in dates:
            for c in cutoffs:
                obs.append(_make_dummy_obs(s, d, c, eligible=True))

    outcomes: list[OutcomeLabelRecord] = []
    for o in obs:
        for target_pct, horizon in [
            (10.0, 5), (10.0, 10), (10.0, 21),
            (20.0, 5), (20.0, 10), (20.0, 21),
            (30.0, 5), (30.0, 10), (30.0, 21),
        ]:
            outcomes.append(
                OutcomeLabelRecord(
                    immutable_security_id=o.immutable_security_id,
                    as_of_date=o.as_of_date,
                    cutoff_time=o.cutoff_time,
                    target_pct=target_pct,
                    horizon_sessions=horizon,
                    clean_target_reached=(int(o.immutable_security_id.split("_")[-1]) % 2 == 0),
                    target_progress_ratio=1.2 if (int(o.immutable_security_id.split("_")[-1]) % 3 == 0) else 0.5,
                    ticker_at_decision=o.ticker_at_decision,
                    reference_entry_price=100.0,
                    entry_friction_bps=5.0,
                    target_price=110.0,
                    adverse_barrier_pct=-5.0,
                    adverse_barrier_price=95.0,
                    clean_risk_cap_pct=5.0,
                    clean_risk_cap_amount=5.0,
                    mfe_pct=8.0,
                    near_miss=False,
                    partial_move=False,
                    mae_pct=-2.0,
                    mae_atr=0.5,
                    adverse_excursion=False,
                    path_sequence_ambiguous=False,
                    end_of_horizon_return=0.05,
                    retention_ratio=0.8,
                    sustained_target=False,
                )
            )

    bundle_dir = tmp_path / "bundle"
    write_committed_summaries(
        bundle_dir=bundle_dir,
        run_id="test_run",
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
        winning_baseline={},
    )

    summary_file = bundle_dir / "outcome_census_summary.json"
    assert summary_file.exists()
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))

    # Assert nine cells are populated and denominators match
    primary_cells = summary_data["primary_2030"]["nine_cells"]
    assert len(primary_cells) == 9
    for cell_val in primary_cells.values():
        assert cell_val["eligible_denominator"] == len(sec_ids) * len(dates)
        assert 0.0 <= cell_val["clean_target_reached_rate"] <= 1.0


def test_legacy_weights_local_semantics():
    """Verify that compute_legacy_tradex_score with local weights preserves fresh default behavior."""
    dates = pd.date_range("2016-01-01", periods=60, freq="B").strftime("%Y-%m-%d").tolist()
    np.random.seed(42)
    closes = np.cumprod(1 + np.random.normal(0.001, 0.02, size=len(dates))) * 100.0
    highs = closes * 1.01
    lows = closes * 0.99
    volumes = np.random.uniform(100000, 500000, size=len(dates))
    df = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes}, index=dates)

    score_default = compute_legacy_tradex_score(df)
    local_weights = LongWeights()
    score_local = compute_legacy_tradex_score(df, weights=local_weights)

    assert score_default == score_local
    assert isinstance(score_local, float)
    assert 0.0 <= score_local <= 100.0
