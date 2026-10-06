"""Tests for execution CLI, artifact schema, provenance, and governance constraints (Tests 58-65)."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.long_002e1.artifacts import (
    build_and_write_artifacts,
    generate_markdown_results_report,
    sort_configurations_within_family,
)
from tradex.research.long_002e1.bootstrap import BootstrapResult
from tradex.research.long_002e1.cli import get_git_head_sha, main, run_official_round1_search
from tradex.research.long_002e1.configs import build_round1_registry
from tradex.research.long_002e1.evaluation import EvaluationSummary, TopKMetrics
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


def _make_dummy_artifacts_data():
    metadata = {
        "task_id": "LONG-002E1-ROUND1-CANDIDATE-SEARCH-001",
        "correction_task_id": "LONG-002E1-CORR-001",
        "correction_spec_sha": "6a4345f6c9c0b96a3c11d4e44b437157128f1222ad346466f8d51c9f4f550c96",
        "attempt_number": 2,
        "consumes_new_material_slot": False,
        "superseded_run_id": "LONG-002E1-20261006_133722",
        "base_git_sha": "8058c5d858b70090335338176f11a20ddfd04502",
        "preregistration_commit_sha": "49103f84ffbf7cd7b60216c2866ad103282bae58",
        "preregistration_spec_sha": "d10b3fd5e24cf6880d76f18cf84eabe23cf65d6fa0a32735877b7383ae51c2b0",
        "execution_code_sha": "8058c5d858b70090335338176f11a20ddfd04502",
        "round2_authorized": False,
        "requires_separate_assignment": True,
    }
    input_integrity = {
        "file_digests": {"test": "abc"},
        "total_population_rows": 100,
        "clean_events_count": 10,
        "clean_base_rate": 0.1,
        "verification_status": "verified_against_spec",
    }
    configs = build_round1_registry()[:1]
    c = configs[0]
    eval_sum = EvaluationSummary(
        configuration_id=c.config_id,
        family=c.family,
        feature_subset_id=c.feature_subset_id,
        evaluation_dates_count=730,
        oof_base_rate=0.1,
        top10=TopKMetrics(
            k=10,
            selected_count=7300,
            clean_count=1800,
            precision=0.25,
            matched_vam5_precision=0.24,
            precision_delta_vs_vam5=0.01,
            lift_vs_oof_base_rate=2.5,
            empirical_clean_move_value=1.5,
            matched_vam5_clean_move_value=1.4,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.15,
            matched_vam5_adverse_rate=0.16,
            median_time_to_target=4.0,
            selection_overlap_pct=0.4,
            distinct_tickers_count=400,
        ),
        top25=TopKMetrics(
            k=25,
            selected_count=18250,
            clean_count=3500,
            precision=0.20,
            matched_vam5_precision=0.19,
            precision_delta_vs_vam5=0.01,
            lift_vs_oof_base_rate=2.0,
            empirical_clean_move_value=1.2,
            matched_vam5_clean_move_value=1.1,
            clean_move_value_delta=0.1,
            primary_adverse_rate=0.18,
            matched_vam5_adverse_rate=0.19,
            median_time_to_target=5.0,
            selection_overlap_pct=0.45,
            distinct_tickers_count=600,
        ),
        annual_precision_10={2018: 0.25, 2019: 0.25, 2020: 0.25},
        annual_vam5_precision_10={2018: 0.24, 2019: 0.24, 2020: 0.24},
        annual_precision_10_delta={2018: 0.01, 2019: 0.01, 2020: 0.01},
        annual_positive_years_count=3,
        calibration_status="not_applicable_round1_unscaled_score",
        brier_score=None,
        reliability_table=None,
        date_level_data=pd.DataFrame(),
    )
    bs = BootstrapResult(
        block_size_sessions=21,
        replicates_count=100,
        seed=42,
        p10_delta_lower=0.005,
        p10_delta_median=0.01,
        p10_delta_upper=0.015,
        p25_delta_lower=0.002,
        p25_delta_median=0.01,
        p25_delta_upper=0.018,
    )
    return (
        metadata,
        input_integrity,
        configs,
        {c.config_id: eval_sum},
        {c.config_id: bs},
        {c.config_id: bs},
        {c.config_id: "round2_eligible"},
        {"run_id": "TEST", "storage_directory": "test", "total_files": 0, "files": []},
        {},
    )


def test_58_search_registry_composition():
    """Test 58: Search registry builds exactly 36 configurations: 12 Rank, 12 Logistic, 12 GBDT."""
    configs = build_round1_registry()
    assert len(configs) == 36
    rank_cnt = sum(1 for c in configs if c.family == "cross_sectional_rank_score")
    log_cnt = sum(1 for c in configs if c.family == "regularized_probabilistic")
    gbdt_cnt = sum(1 for c in configs if c.family == "shallow_strongly_regularized_gbdt")
    assert rank_cnt == 12
    assert log_cnt == 12
    assert gbdt_cnt == 12


def test_59_budget_slots_consecutive():
    """Test 59: Budget slots are strictly 1..36 with no duplicates or gaps."""
    configs = build_round1_registry()
    slots = [c.budget_slot for c in configs]
    assert slots == list(range(1, 37))


def test_60_status_ordering_locked_eight_level():
    """Test 60: Status ordering implements locked 8-level sort."""
    items = [
        {
            "configuration_id": "CONFIG_B",
            "family": "cross_sectional_rank_score",
            "feature_subset_id": "S1",
            "status": "round2_eligible",
            "p10_delta": 0.02,
            "bootstrap_21_p10_lower": 0.005,
            "p25_delta": 0.01,
            "ecmv10_delta": 0.1,
            "adverse_rate_10": 0.15,
        },
        {
            "configuration_id": "CONFIG_A",
            "family": "cross_sectional_rank_score",
            "feature_subset_id": "S1",
            "status": "round2_eligible",
            "p10_delta": 0.03,  # Higher p10_delta should sort ahead of CONFIG_B
            "bootstrap_21_p10_lower": 0.010,
            "p25_delta": 0.01,
            "ecmv10_delta": 0.2,
            "adverse_rate_10": 0.14,
        },
    ]
    sorted_items = sort_configurations_within_family(items)
    assert sorted_items[0]["configuration_id"] == "CONFIG_A"
    assert sorted_items[1]["configuration_id"] == "CONFIG_B"


def test_61_cli_rejects_round_2():
    """Test 61: CLI rejects --round 2 with required error message."""
    ret = main(["run", "--round", "2"])
    assert ret == 1

    with pytest.raises(ValueError, match="Round 2 is not authorized"):
        run_official_round1_search(round_num=2)


def test_62_artifacts_list_matches_spec(tmp_path: Path):
    """Test 62: Artifact generation creates all 13 required artifact files."""
    metadata, input_integrity, configs, eval_sums, bs21, bs42, statuses, ext_man, failures = (
        _make_dummy_artifacts_data()
    )
    checksums = build_and_write_artifacts(
        run_id="TEST_RUN",
        output_dir=tmp_path,
        metadata=metadata,
        input_integrity=input_integrity,
        configs=configs,
        eval_summaries=eval_sums,
        bootstrap_results_21=bs21,
        bootstrap_results_42=bs42,
        config_statuses=statuses,
        external_manifest=ext_man,
        execution_failures=failures,
    )
    expected_files = {
        "execution_metadata.json",
        "input_integrity.json",
        "configuration_registry.json",
        "experiment_ledger.jsonl",
        "round1_summary.json",
        "family_summary.json",
        "baseline_summary.json",
        "bootstrap_summary.json",
        "annual_stability.json",
        "model_diagnostics.json",
        "round2_readiness.json",
        "external_files_manifest.json",
        "checksums.sha256",
    }
    actual_files = {p.name for p in tmp_path.iterdir()}
    assert actual_files == expected_files
    assert len(checksums) == 12  # All files except checksums.sha256 itself


def test_63_checksums_format(tmp_path: Path):
    """Test 63: Checksums manifest contains correct format and valid SHA-256 digests."""
    metadata, input_integrity, configs, eval_sums, bs21, bs42, statuses, ext_man, failures = (
        _make_dummy_artifacts_data()
    )
    build_and_write_artifacts(
        run_id="TEST_RUN",
        output_dir=tmp_path,
        metadata=metadata,
        input_integrity=input_integrity,
        configs=configs,
        eval_summaries=eval_sums,
        bootstrap_results_21=bs21,
        bootstrap_results_42=bs42,
        config_statuses=statuses,
        external_manifest=ext_man,
        execution_failures=failures,
    )
    chk_file = tmp_path / "checksums.sha256"
    assert chk_file.exists()
    lines = chk_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 12
    for line in lines:
        parts = line.split("  ")
        assert len(parts) == 2, f"Line format invalid: {line}"
        digest, fname = parts
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        target = tmp_path / fname
        assert target.exists()
        actual_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == actual_digest


def test_64_markdown_report_structure(tmp_path: Path):
    """Test 64: Markdown report contains all required sections, audit notices, and governance invariants."""
    metadata, input_integrity, configs, eval_sums, bs21, bs42, statuses, ext_man, failures = (
        _make_dummy_artifacts_data()
    )
    checksums = build_and_write_artifacts(
        run_id="TEST_RUN",
        output_dir=tmp_path,
        metadata=metadata,
        input_integrity=input_integrity,
        configs=configs,
        eval_summaries=eval_sums,
        bootstrap_results_21=bs21,
        bootstrap_results_42=bs42,
        config_statuses=statuses,
        external_manifest=ext_man,
        execution_failures=failures,
    )
    with (tmp_path / "baseline_summary.json").open("r", encoding="utf-8") as f:
        base_sum = json.load(f)
    with (tmp_path / "round1_summary.json").open("r", encoding="utf-8") as f:
        r1_sum = json.load(f)
    with (tmp_path / "family_summary.json").open("r", encoding="utf-8") as f:
        fam_sum = json.load(f)
    with (tmp_path / "round2_readiness.json").open("r", encoding="utf-8") as f:
        readiness = json.load(f)

    report = generate_markdown_results_report(
        run_id="TEST_RUN",
        metadata=metadata,
        base_summary=base_sum,
        round1_summary=r1_sum,
        family_summary=fam_sum,
        readiness=readiness,
        checksums=checksums,
    )
    assert report.startswith("# LONG-002E1:")
    assert "## 1. Executive Summary & Purpose" in report
    assert "## 2. Matched Baseline Comparator Performance (VAM5)" in report
    assert "## 3. Round-1 Family Summary & Dispositions" in report
    assert "## 4. Search Budget Accounting & Round-2 Readiness" in report
    assert "## 5. Artifact Inventory & Cryptographic Checksums" in report
    assert "## 6. Stop Condition & Governance Invariants" in report
    assert "LONG-002E1-CORR-001" in report
    assert "LONG-002E1-20261006_133722" in report
    assert "APPROVED_PRODUCTION_STRATEGIES == ()" in report
    assert "**Round 2 Authorized:** `false`" in report


def test_65_production_strategies_preserved():
    """Test 65: Production strategies assertion: APPROVED_PRODUCTION_STRATEGIES == ()."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()


def test_cli_execution_sha_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch):
    """Verify CLI raises ValueError if supplied execution-sha does not match runtime HEAD."""
    monkeypatch.setattr("tradex.research.long_002e1.cli.check_git_clean", lambda _: True)
    repo_root = Path(__file__).resolve().parents[3]
    runtime_head = get_git_head_sha(repo_root)
    fake_sha = "0000000000000000000000000000000000000000"
    assert fake_sha != runtime_head

    with pytest.raises(ValueError, match="EXECUTION SHA MISMATCH"):
        run_official_round1_search(execution_sha=fake_sha, repo_root=repo_root)


def test_cli_spec_integrity_upfront(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Verify CLI calls verify_spec_integrity upfront before data loading."""
    called = []

    def mock_verify():
        called.append(True)
        raise ValueError("MOCK SPEC INTEGRITY BREACH")

    monkeypatch.setattr("tradex.research.long_002e1.cli.verify_spec_integrity", mock_verify)

    with pytest.raises(ValueError, match="MOCK SPEC INTEGRITY BREACH"):
        run_official_round1_search()

    assert called == [True]
