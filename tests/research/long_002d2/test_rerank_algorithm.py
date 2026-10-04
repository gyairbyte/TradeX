"""Tests for coverage-matched reranking algorithm in LONG-002D2."""
from __future__ import annotations

import pandas as pd
import pytest

from tradex.research.long_002d2.rerank import run_coverage_matched_reranking
from tradex.research.long_002d2.spec import CandidateSpec


@pytest.fixture
def sample_rerank_df() -> pd.DataFrame:
    """Create a minimal deterministic DataFrame with 2 dates and known rankings."""
    # Date 1: 10 stocks. 2 in top 10 (K=2), 4 in top 25.
    rows = []
    # Date 1: K(date) = 2
    # Securities: SEC_1 to SEC_10
    # VAM5 ranks: 1 to 10
    # Candidate values: SEC_1 has 1.0, SEC_2 has 0.5, SEC_3 has 2.0, SEC_4 has 1.5, others 0.1
    # Note: SEC_3 and SEC_4 are top 25 (ranks 3 and 4), but SEC_3 and SEC_4 have HIGHER candidate values!
    # So VAM5 top 2 selects: SEC_1, SEC_2
    # Candidate top 2 from top 25 (SEC_1..4) selects: SEC_3 (2.0), SEC_4 (1.5)
    for i in range(1, 11):
        sec_id = f"SEC_{i:02d}"
        cand_val = {1: 1.0, 2: 0.5, 3: 2.0, 4: 1.5}.get(i, 0.1)
        # Outcome: clean_target_reached True for SEC_3, SEC_4, False for SEC_1, SEC_2
        clean = i in (3, 4)
        rows.append(
            {
                "immutable_security_id": sec_id,
                "as_of_date": "2017-01-03",
                "cutoff_time": "20:30",
                "clean_target_reached": clean,
                "relative_volume_20": cand_val,
                "cross_sectional_rank": i,
                "raw_score_or_return": 100.0 - i,
                "top_10_flag": i <= 2,
                "top_25_flag": i <= 4,
            }
        )

    # Date 2: 10 stocks. 2 in top 10 (K=2), 4 in top 25.
    # VAM5 top 2: SEC_01, SEC_02 (clean = True for SEC_01, False for SEC_02)
    # Candidate values: SEC_01 has 3.0, SEC_02 has 2.0, SEC_03 has 1.0, SEC_04 has 0.5
    # Candidate top 2: SEC_01, SEC_02 (identical selection, overlap = 2)
    for i in range(1, 11):
        sec_id = f"SEC_{i:02d}"
        cand_val = {1: 3.0, 2: 2.0, 3: 1.0, 4: 0.5}.get(i, 0.1)
        clean = i in (1, 5)
        rows.append(
            {
                "immutable_security_id": sec_id,
                "as_of_date": "2017-01-04",
                "cutoff_time": "20:30",
                "clean_target_reached": clean,
                "relative_volume_20": cand_val,
                "cross_sectional_rank": i,
                "raw_score_or_return": 100.0 - i,
                "top_10_flag": i <= 2,
                "top_25_flag": i <= 4,
            }
        )

    return pd.DataFrame(rows)


def test_coverage_matched_counts_equal(sample_rerank_df: pd.DataFrame) -> None:
    """Verify that candidate and matched VAM5 select exactly K(date) names on every date."""
    spec = CandidateSpec(
        feature_id="relative_volume_20",
        role="primary_candidate",
        hypothesized_direction="HIGHER",
        formula="test",
    )
    overall, _annual, date_res = run_coverage_matched_reranking(sample_rerank_df, spec)

    assert overall["total_selected_count"] == 4  # 2 per date
    assert overall["evaluation_dates_count"] == 2
    for r in date_res.values():
        assert r["k_date"] == 2
        assert len(r["cand_ids"]) == 2
        assert len(r["vam5_ids"]) == 2


def test_candidate_selection_within_top_25_only(sample_rerank_df: pd.DataFrame) -> None:
    """Verify that no candidate can be selected from outside the VAM5 top-25 pool."""
    spec = CandidateSpec(
        feature_id="relative_volume_20",
        role="primary_candidate",
        hypothesized_direction="HIGHER",
        formula="test",
    )
    _, _, date_res = run_coverage_matched_reranking(sample_rerank_df, spec)

    # SEC_1 to SEC_4 are top 25; no SEC_5..10 may ever be selected
    allowed_ids = {f"SEC_{i:02d}" for i in range(1, 5)}
    for r in date_res.values():
        assert r["cand_ids"].issubset(allowed_ids)


def test_candidate_tie_break_determinism() -> None:
    """Verify that ties in candidate feature are broken by immutable_security_id ASC."""
    rows = []
    # 4 stocks in top 25, K=2. All have candidate value 1.5.
    # Sorted by ID ASC: SEC_A, SEC_B, SEC_C, SEC_D. Best 2 must be SEC_A and SEC_B.
    ids = ["SEC_D", "SEC_B", "SEC_A", "SEC_C"]
    for i, sid in enumerate(ids, 1):
        rows.append(
            {
                "immutable_security_id": sid,
                "as_of_date": "2017-01-03",
                "cutoff_time": "20:30",
                "clean_target_reached": False,
                "relative_volume_20": 1.5,
                "cross_sectional_rank": i,
                "raw_score_or_return": 10.0,
                "top_10_flag": i <= 2,
                "top_25_flag": True,
            }
        )
    df = pd.DataFrame(rows)
    spec = CandidateSpec(
        feature_id="relative_volume_20",
        role="primary_candidate",
        hypothesized_direction="HIGHER",
        formula="test",
    )
    _, _, date_res = run_coverage_matched_reranking(df, spec)
    assert date_res["2017-01-03"]["cand_ids"] == {"SEC_A", "SEC_B"}


def test_candidate_pool_deficit_fails_closed(sample_rerank_df: pd.DataFrame) -> None:
    """Verify that if top-25 pool size < K(date), the evaluator raises ValueError."""
    # Set top_10_flag for 5 stocks but top_25_flag for only 3 stocks
    df_broken = sample_rerank_df.copy()
    df_broken.loc[df_broken["as_of_date"] == "2017-01-03", "top_10_flag"] = True
    df_broken.loc[df_broken["as_of_date"] == "2017-01-03", "top_25_flag"] = False

    spec = CandidateSpec(
        feature_id="relative_volume_20",
        role="primary_candidate",
        hypothesized_direction="HIGHER",
        formula="test",
    )
    with pytest.raises(ValueError, match="CANDIDATE POOL DEFICIT"):
        run_coverage_matched_reranking(df_broken, spec)


def test_coverage_gate_fails_closed_under_95_pct(sample_rerank_df: pd.DataFrame) -> None:
    """Verify that if candidate feature coverage within top-25 pool < 95%, fails closed."""
    df_broken = sample_rerank_df.copy()
    # Null out candidate values for top-25 rows to breach 95% threshold
    df_broken.loc[df_broken["top_25_flag"] == True, "relative_volume_20"] = None

    spec = CandidateSpec(
        feature_id="relative_volume_20",
        role="primary_candidate",
        hypothesized_direction="HIGHER",
        formula="test",
    )
    with pytest.raises(ValueError, match="COVERAGE GATE BREACH"):
        run_coverage_matched_reranking(df_broken, spec)
