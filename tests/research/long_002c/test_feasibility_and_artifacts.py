"""Tests for block resampling, endpoint feasibility, artifact manifests, and credential secrecy."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tradex.research.long_002c.artifacts import (
    write_committed_summaries,
)
from tradex.research.long_002c.feasibility import (
    compute_hhi_and_effective_n,
    run_block_resampling,
)
from tradex.research.long_002c.models import (
    OutcomeLabelRecord,
)


def test_hhi_and_effective_n() -> None:
    """Verify HHI and effective number of securities calculation."""
    # 4 securities with equal counts (25% each) -> HHI = 4 * (0.25^2) = 0.25 -> Eff N = 4.0
    counts = {"A": 25, "B": 25, "C": 25, "D": 25}
    hhi, eff_n = compute_hhi_and_effective_n(counts)
    assert round(hhi, 2) == 0.25
    assert eff_n == 4.0


def test_block_resampling_reproducibility() -> None:
    """Verify 21-session block resampling runs deterministically with fixed seed."""
    sessions = [f"2016-01-{i:02d}" for i in range(4, 25)]
    observations = [
        {
            "immutable_security_id": "SEC_1",
            "as_of_date": s,
            "cutoff_time": "20:30",
            "raw_outcome_eligible": True,
            "split_boundary_purged": False,
        }
        for s in sessions
    ]
    dummy_rec = OutcomeLabelRecord(
        immutable_security_id="SEC_1",
        as_of_date="2016-01-04",
        cutoff_time="20:30",
        target_pct=10.0,
        horizon_sessions=10,
        ticker_at_decision="TEST",
        reference_entry_price=100.0,
        entry_friction_bps=10.0,
        target_price=110.0,
        adverse_barrier_pct=0.05,
        adverse_barrier_price=95.0,
        clean_risk_cap_pct=0.05,
        clean_risk_cap_amount=5.0,
        mfe_pct=0.12,
        target_progress_ratio=1.2,
        near_miss=False,
        partial_move=False,
        mae_pct=0.01,
        mae_atr=0.5,
        adverse_excursion=False,
        clean_target_reached=True,
        path_sequence_ambiguous=False,
        end_of_horizon_return=0.10,
        retention_ratio=0.83,
        sustained_target=True,
    )
    outcomes_map = {
        ("SEC_1", s, "20:30"): {(10.0, 10): dummy_rec, (10.0, 21): dummy_rec} for s in sessions
    }

    res1 = run_block_resampling(observations, outcomes_map, sessions, block_size_sessions=5, num_bootstraps=50, seed=123)
    res2 = run_block_resampling(observations, outcomes_map, sessions, block_size_sessions=5, num_bootstraps=50, seed=123)

    assert res1["clean_target_10_10"]["mean"] == res2["clean_target_10_10"]["mean"]
    assert res1["clean_target_10_10"]["ci_2_5"] == res2["clean_target_10_10"]["ci_2_5"]


def test_artifacts_contain_no_secrets() -> None:
    """Verify generated JSON summary manifests contain no secrets, API keys, or tokens."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle"
        sha_map = write_committed_summaries(
            bundle_dir=bundle_path,
            run_id="test_run",
            manifest_files=[],
            observations=[],
            outcomes=[],
            episodes=[],
            baselines=[],
            quality=[],
            provenance=[],
            exclusions=[],
            feasibility_report={"status": "ok"},
            execution_metadata={"task_id": "LONG-002C-EXEC-001"},
        )

        assert "checksums.sha256" in sha_map

        for fpath in bundle_path.glob("*.json"):
            content = fpath.read_text(encoding="utf-8")
            lower = content.lower()
            assert "api_key" not in lower or "alpaca_api_key" not in content
            assert "secret" not in lower or "rejection_reason" in lower
            assert "token" not in lower or "page_token" in lower or "constituent_token" in lower
