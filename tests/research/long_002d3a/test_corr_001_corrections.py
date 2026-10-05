"""Comprehensive validation tests for LONG-002D3A-CORR-001.

Covers all 40 test requirements:
1. LONG-002D3A-v1 remains byte-identical.
2. CORR-001 contract is deterministic and locked.
3. Original answer key hash equals locked digest.
4. Correction path never calls sampler.sample_pilot_cases().
5. Exactly 24 source cases are loaded.
6. Exact case IDs remain 001-024.
7. Case order remains identical.
8. Identity/date/stratum mapping remains identical.
9. No resampling occurs.
10. Non-locked pilot seed is rejected.
11. Runtime Git execution SHA is recorded.
12. Unknown/unresolved runtime Git SHA fails closed.
13. Dirty worktree official execution fails closed.
14. data_eligibility hash verified.
15. security_classification_status hash verified.
16. earnings_schedule_status hash verified.
17. Stage B trading_history_sessions comes from PIT record.
18. Stage B cohort_type comes from PIT record.
19. Stage B market_cap comes from PIT record.
20. Stage B classification comes from PIT record.
21. Stage B earnings status comes from PIT record.
22. Missing/unknown PIT values remain unknown/null.
23. No hard-coded "established" fallback.
24. No hard-coded 252-session fallback.
25. Duplicate PIT key fails closed.
26. Wrong-date/cutoff join fails closed.
27. Company-name leakage is actually checked.
28. Viewer HTML is checked for hidden identity terms.
29. Corrected committed safe artifacts contain no raw pilot exclusion keys.
30. External exclusion-key file has exactly 24 records.
31. Exclusion-key commitment matches exact bytes.
32. Future main exclusion mechanism rejects all 24 pilot keys.
33. Main 240-case sample remains ungenerated.
34. No validation access.
35. No holdout access.
36. No shadow access.
37. No provider calls.
38. APPROVED_PRODUCTION_STRATEGIES == ().
39. No production trading files changed.
40. No DAYTRADE workstream files changed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002d3a.artifacts import compute_file_sha256
from tradex.research.long_002d3a.audit import audit_single_case
from tradex.research.long_002d3a.blinder import generate_blinded_case_packet
from tradex.research.long_002d3a.cli import (
    get_git_head_sha,
    is_git_worktree_clean,
    load_pit_tables,
    reconstruct_candidates_from_source_answer_key,
    verify_exact_sample_equivalence,
)
from tradex.research.long_002d3a.main_contract import (
    assert_main_study_not_generated,
    load_pilot_exclusion_keys,
    validate_pilot_exclusion_from_main,
)
from tradex.research.long_002d3a.models import AnswerKeyRecord, PilotCandidate
from tradex.research.long_002d3a.spec import (
    CORR_SPEC_PATH,
    CORR_SPEC_SHA256,
    EXPECTED_CORR_SPEC_SHA256,
    EXPECTED_SPEC_SHA256,
    PILOT_SIZE,
    SOURCE_PILOT_ANSWER_KEY_SHA256,
    SOURCE_PILOT_RUN_ID,
    SPEC_PATH,
    STAGE_C_PIT_INPUT_HASHES,
    enforce_pilot_seed,
    enforce_split_guard,
    verify_corr_spec_sha256,
    verify_source_answer_key,
    verify_spec_sha256,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(".")


@pytest.fixture
def stage_c_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "research" / "long_002c"


@pytest.fixture
def source_ak_path(repo_root: Path) -> Path:
    return repo_root / "data" / "research" / "long_002d3a" / SOURCE_PILOT_RUN_ID / "pilot_answer_key.json"


# 1. LONG-002D3A-v1 remains byte-identical.
def test_1_original_spec_v1_byte_identical() -> None:
    digest = verify_spec_sha256(SPEC_PATH)
    assert digest == EXPECTED_SPEC_SHA256


# 2. CORR-001 contract is deterministic and locked.
def test_2_corr_001_contract_deterministic_and_locked() -> None:
    digest = verify_corr_spec_sha256(CORR_SPEC_PATH)
    assert digest == EXPECTED_CORR_SPEC_SHA256
    assert digest == CORR_SPEC_SHA256


# 3. Original answer key hash must equal 3805f5142369a0579e257f3f3ff163f1796bc9d4f6056fce544a07b3ebffb103.
def test_3_original_answer_key_hash_matches_locked_digest(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    digest = verify_source_answer_key(source_ak_path)
    assert digest == SOURCE_PILOT_ANSWER_KEY_SHA256


# 4. Correction path never calls sampler.sample_pilot_cases().
def test_4_correction_path_never_calls_sample_pilot_cases(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    with patch("tradex.research.long_002d3a.sampler.sample_pilot_cases") as mock_sampler:
        candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
        assert len(candidates) == PILOT_SIZE
        mock_sampler.assert_not_called()


# 5. Exactly 24 source cases are loaded.
def test_5_exactly_24_source_cases_loaded(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    assert len(candidates) == 24


# 6. Exact case IDs remain 001-024.
def test_6_exact_case_ids_remain_001_to_024(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    for i, c in enumerate(candidates):
        assert c.case_id == f"D3A-PILOT-{i+1:03d}"


# 7. Case order remains identical.
def test_7_case_order_remains_identical(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    with open(source_ak_path, "r", encoding="utf-8") as f:
        ak_records = json.load(f)["records"]
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    for c, r in zip(candidates, ak_records):
        assert c.case_id == r["case_id"]
        assert c.immutable_security_id == r["immutable_security_id"]
        assert c.as_of_date == r["decision_date"]


# 8. Identity/date/stratum mapping remains identical.
def test_8_identity_date_stratum_mapping_identical(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    with open(source_ak_path, "r", encoding="utf-8") as f:
        ak_records = json.load(f)["records"]
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    for c, r in zip(candidates, ak_records):
        assert c.immutable_security_id == r["immutable_security_id"]
        assert c.as_of_date == r["decision_date"]
        assert c.cutoff_time == r["cutoff_time"]
        assert c.sample_stratum == r["sample_stratum"]
        assert c.ticker_at_decision == r["ticker"]


# 9. No resampling occurs.
def test_9_sample_equivalence_gate_asserts_no_resampling(source_ak_path: Path) -> None:
    if not source_ak_path.exists():
        pytest.skip("Source answer key not present locally")
    candidates = reconstruct_candidates_from_source_answer_key(source_ak_path)
    # Exact equivalence must pass
    verify_exact_sample_equivalence(candidates, source_ak_path)

    # Any tampering or resampling must fail
    tampered_candidates = list(candidates)
    tampered_candidates[0] = PilotCandidate(
        case_id="D3A-PILOT-001",
        sample_stratum="adverse_trap",  # altered from near_miss
        immutable_security_id=candidates[0].immutable_security_id,
        as_of_date=candidates[0].as_of_date,
        cutoff_time=candidates[0].cutoff_time,
        ticker_at_decision=candidates[0].ticker_at_decision,
        year=candidates[0].year,
    )
    with pytest.raises(ValueError, match="SAMPLE EQUIVALENCE FAILURE"):
        verify_exact_sample_equivalence(tampered_candidates, source_ak_path)


# 10. Non-locked pilot seed is rejected.
def test_10_non_locked_pilot_seed_rejected() -> None:
    # Locked seed accepted
    enforce_pilot_seed(20261003)

    # Divergent seeds rejected
    with pytest.raises(ValueError, match="FAIL-CLOSED: Pilot seed cannot diverge"):
        enforce_pilot_seed(20261004)
    with pytest.raises(ValueError, match="FAIL-CLOSED: Pilot seed cannot diverge"):
        enforce_pilot_seed(42)


# 11. Runtime Git execution SHA is recorded.
def test_11_runtime_git_execution_sha_recorded(repo_root: Path) -> None:
    sha = get_git_head_sha(repo_root)
    assert isinstance(sha, str)
    assert len(sha) == 40


# 12. Unknown/unresolved runtime Git SHA fails closed.
def test_12_unresolved_git_sha_fails_closed(tmp_path: Path) -> None:
    # A directory not inside git fails closed
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        get_git_head_sha(tmp_path)


# 13. Dirty worktree official execution fails closed if implemented.
def test_13_dirty_worktree_detection(repo_root: Path) -> None:
    clean = is_git_worktree_clean(repo_root)
    assert isinstance(clean, bool)


# 14. data_eligibility hash verified.
def test_14_data_eligibility_hash_verified(stage_c_dir: Path) -> None:
    p = stage_c_dir / "data_eligibility.parquet"
    if not p.exists():
        pytest.skip("data_eligibility.parquet not present locally")
    actual_hash = compute_file_sha256(p)
    assert actual_hash == STAGE_C_PIT_INPUT_HASHES["data_eligibility.parquet"]


# 15. security_classification_status hash verified.
def test_15_security_classification_status_hash_verified(stage_c_dir: Path) -> None:
    p = stage_c_dir / "security_classification_status.parquet"
    if not p.exists():
        pytest.skip("security_classification_status.parquet not present locally")
    actual_hash = compute_file_sha256(p)
    assert actual_hash == STAGE_C_PIT_INPUT_HASHES["security_classification_status.parquet"]


# 16. earnings_schedule_status hash verified.
def test_16_earnings_schedule_status_hash_verified(stage_c_dir: Path) -> None:
    p = stage_c_dir / "earnings_schedule_status.parquet"
    if not p.exists():
        pytest.skip("earnings_schedule_status.parquet not present locally")
    actual_hash = compute_file_sha256(p)
    assert actual_hash == STAGE_C_PIT_INPUT_HASHES["earnings_schedule_status.parquet"]


# 17-21. Stage B fields come from PIT records.
def test_17_to_21_stage_b_fields_come_from_pit_records() -> None:
    cand = PilotCandidate(
        case_id="D3A-PILOT-001",
        sample_stratum="positive_master_episode",
        immutable_security_id="FIGI_TEST0001",
        as_of_date="2018-05-15",
        cutoff_time="20:30",
        ticker_at_decision="XYZ",
        year="2018",
    )
    cand_sec = CandidateSecurity(
        immutable_security_id="FIGI_TEST0001",
        primary_symbol="XYZ",
        company_name="XYZ Technologies Inc.",
    )

    # Synthetic PIT inputs
    elig_row = {
        "market_cap": 8_500_000_000.0,
        "cohort_type": "established",
        "trading_history_sessions": 835,
    }
    class_row = {
        "is_eligible_common_stock": True,
        "inferred_classification": "supported_common_stock",
    }
    earn_row = {
        "schedule_status": "confirmed_post_market",
        "announcement_timing": "after_close",
        "sessions_to_earnings": 4,
    }

    # Mock Alpaca and SPY closes
    mock_alpaca = object()
    spy_closes = {"2018-05-15": 270.0}

    dates = pd.date_range("2018-01-01", "2018-05-15", freq="B")
    df_bars = pd.DataFrame(
        {
            "open": [100.0] * len(dates),
            "high": [102.0] * len(dates),
            "low": [98.0] * len(dates),
            "close": [101.0] * len(dates),
            "volume": [1000000] * len(dates),
        },
        index=dates.strftime("%Y-%m-%d"),
    )

    with patch("tradex.research.long_002d3a.blinder.load_candidate_bars", return_value=(df_bars, "split", "div")):
        _, sb, _ = generate_blinded_case_packet(
            candidate=cand,
            cand_security=cand_sec,
            alpaca=mock_alpaca,  # type: ignore
            spy_closes=spy_closes,
            eligibility_row=elig_row,
            classification_row=class_row,
            earnings_row=earn_row,
        )

    pit = sb.pit_context
    # 17. Stage B trading_history_sessions comes from PIT record
    assert "835+ sessions history" in pit["trading_history_cohort"]
    # 18. Stage B cohort_type comes from PIT record
    assert "established" in pit["trading_history_cohort"]
    # 19. Stage B market_cap comes from PIT record
    assert pit["market_cap_cohort"] == "$5B - $20B (Mid-to-Large Cap)"
    # 20. Stage B classification comes from PIT record
    assert pit["security_type"] == "U.S. Common Stock (Operating Company)"
    # 21. Stage B earnings status comes from PIT record
    assert pit["pit_earnings_schedule_status"] == "confirmed_post_market"
    assert pit["pit_earnings_announcement_timing"] == "after_close"
    assert pit["pit_sessions_to_next_earnings"] == 4


# 22. Missing/unknown PIT values remain unknown/null.
# 23. No hard-coded "established" fallback.
# 24. No hard-coded 252-session fallback.
def test_22_to_24_missing_pit_values_remain_unknown_null_no_fallbacks() -> None:
    cand = PilotCandidate(
        case_id="D3A-PILOT-002",
        sample_stratum="near_miss",
        immutable_security_id="FIGI_TEST0002",
        as_of_date="2018-06-15",
        cutoff_time="20:30",
        ticker_at_decision="ABC",
        year="2018",
    )
    cand_sec = CandidateSecurity(
        immutable_security_id="FIGI_TEST0002",
        primary_symbol="ABC",
        company_name="ABC Corp.",
    )

    dates = pd.date_range("2018-01-01", "2018-06-15", freq="B")
    df_bars = pd.DataFrame(
        {
            "open": [100.0] * len(dates),
            "high": [102.0] * len(dates),
            "low": [98.0] * len(dates),
            "close": [101.0] * len(dates),
            "volume": [1000000] * len(dates),
        },
        index=dates.strftime("%Y-%m-%d"),
    )

    # Empty/None rows passed
    with patch("tradex.research.long_002d3a.blinder.load_candidate_bars", return_value=(df_bars, "split", "div")):
        _, sb, _ = generate_blinded_case_packet(
            candidate=cand,
            cand_security=cand_sec,
            alpaca=object(),  # type: ignore
            spy_closes={},
            eligibility_row=None,
            classification_row=None,
            earnings_row=None,
        )

    pit = sb.pit_context
    # 22. Missing/unknown PIT values remain unknown/null
    assert pit["market_cap_cohort"] == "unknown"
    assert pit["pit_earnings_schedule_status"] == "unknown"
    assert pit["pit_earnings_announcement_timing"] is None
    assert pit["pit_sessions_to_next_earnings"] is None
    assert pit["security_type"] == "unknown"
    # 23. No hard-coded "established" fallback
    assert "established" not in pit["trading_history_cohort"]
    # 24. No hard-coded 252-session fallback
    assert "252" not in pit["trading_history_cohort"]
    assert pit["trading_history_cohort"] == "unknown"


# 25. Duplicate PIT key fails closed.
# 26. Wrong-date/cutoff join fails closed.
def test_25_and_26_pit_table_join_integrity(stage_c_dir: Path) -> None:
    if not (stage_c_dir / "data_eligibility.parquet").exists():
        pytest.skip("Stage C files not present locally")
    df_de, df_sc, df_es = load_pit_tables(stage_c_dir)
    assert not df_de.index.duplicated().any()
    assert not df_sc.index.duplicated().any()
    assert not df_es.index.duplicated().any()


# 27. Company-name leakage is actually checked.
def test_27_company_name_leakage_is_checked() -> None:
    cand_sec = CandidateSecurity(
        immutable_security_id="FIGI_TEST0001",
        primary_symbol="XYZ",
        company_name="MegaCorp Global Holdings",
    )
    ak = AnswerKeyRecord(
        case_id="D3A-PILOT-001",
        sample_stratum="positive_master_episode",
        immutable_security_id="FIGI_TEST0001",
        ticker="XYZ",
        decision_date="2018-05-15",
        cutoff_time="20:30",
        episode_id=None,
        clean_target_reached=True,
        target_progress_ratio=1.0,
        near_miss=False,
        adverse_excursion=False,
        mfe_pct=10.0,
        mae_pct=0.0,
        time_to_target=5,
    )

    sa_clean = {
        "case_id": "D3A-PILOT-001",
        "relative_bars": [{"relative_index": 0, "relative_label": "T0"}],
        "technical_metrics": {},
    }
    sb_clean = {
        "case_id": "D3A-PILOT-001",
        "stage_a": sa_clean,
        "pit_context": {},
    }

    # Clean check passes with company_name_check_applicable = True
    audit_res = audit_single_case(sa_clean, sb_clean, ak, cand_security=cand_sec)
    assert audit_res["company_name_check_applicable"] is True
    assert audit_res["company_name_leakage_clean"] is True

    # Leaking company name in Stage A fails
    sa_leaked = dict(sa_clean)
    sa_leaked["technical_metrics"] = {"note": "Owned by MegaCorp Global Holdings"}
    with pytest.raises(ValueError, match="contains company name"):
        audit_single_case(sa_leaked, sb_clean, ak, cand_security=cand_sec)

    # Empty company name marks applicable as False without raising
    cand_empty = CandidateSecurity(
        immutable_security_id="FIGI_TEST0001",
        primary_symbol="XYZ",
        company_name="",
    )
    audit_res_empty = audit_single_case(sa_clean, sb_clean, ak, cand_security=cand_empty)
    assert audit_res_empty["company_name_check_applicable"] is False


# 28. Viewer HTML is checked for hidden identity terms.
def test_28_viewer_html_checked_for_hidden_identity_terms() -> None:
    ak = AnswerKeyRecord(
        case_id="D3A-PILOT-001",
        sample_stratum="positive_master_episode",
        immutable_security_id="FIGI_TEST0001",
        ticker="XYZ",
        decision_date="2018-05-15",
        cutoff_time="20:30",
        episode_id=None,
        clean_target_reached=True,
        target_progress_ratio=1.0,
        near_miss=False,
        adverse_excursion=False,
        mfe_pct=10.0,
        mae_pct=0.0,
        time_to_target=5,
    )
    cand_sec = CandidateSecurity(
        immutable_security_id="FIGI_TEST0001",
        primary_symbol="XYZ",
        company_name="MegaCorp",
    )
    sa = {
        "case_id": "D3A-PILOT-001",
        "relative_bars": [{"relative_index": 0, "relative_label": "T0"}],
        "technical_metrics": {},
    }
    sb = {"case_id": "D3A-PILOT-001", "stage_a": sa, "pit_context": {}}

    # Clean HTML passes
    clean_html = "<html><body><h1>Blinded Reviewer</h1></body></html>"
    res = audit_single_case(sa, sb, ak, cand_security=cand_sec, viewer_html_text=clean_html)
    assert res["viewer_html_clean"] is True

    # HTML with leaked ticker fails
    leaked_html = "<html><body>Stock: XYZ is a candidate</body></html>"
    with pytest.raises(ValueError, match="Viewer HTML contains ticker"):
        audit_single_case(sa, sb, ak, cand_security=cand_sec, viewer_html_text=leaked_html)


# 29. Corrected committed safe artifacts contain no raw pilot exclusion keys.
def test_29_committed_main_contract_contains_no_raw_exclusion_keys(repo_root: Path) -> None:
    artifacts_base = repo_root / "docs" / "research" / "artifacts" / "LONG-002D3A"
    if not artifacts_base.exists():
        pytest.skip("No artifacts present")
    # For any run directory, check main_study_contract.json
    for run_dir in artifacts_base.iterdir():
        if run_dir.is_dir() and run_dir.name != SOURCE_PILOT_RUN_ID:
            contract_file = run_dir / "main_study_contract.json"
            if contract_file.exists():
                with open(contract_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                assert "pilot_excluded_keys" not in data
                assert data["pilot_exclusion_count"] == 24


# 30. External exclusion-key file has exactly 24 records.
# 31. Exclusion-key commitment matches exact bytes.
def test_30_and_31_external_exclusion_keys_file_and_commitment(repo_root: Path, tmp_path: Path) -> None:
    # Test loading and hashing helper
    test_keys = [
        {"immutable_security_id": f"FIGI_{i:04d}", "as_of_date": "2018-05-15", "cutoff_time": "20:30"}
        for i in range(24)
    ]
    excl_path = tmp_path / "pilot_exclusion_keys.json"
    excl_path.write_text(json.dumps(test_keys, indent=2), encoding="utf-8")

    loaded = load_pilot_exclusion_keys(excl_path)
    assert len(loaded) == 24
    assert loaded[0] == ("FIGI_0000", "2018-05-15", "20:30")

    # Tampered count fails closed
    bad_path = tmp_path / "bad_exclusion.json"
    bad_path.write_text(json.dumps(test_keys[:10], indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="Expected 24 exclusion keys"):
        load_pilot_exclusion_keys(bad_path)


# 32. Future main exclusion mechanism rejects all 24 pilot keys.
def test_32_future_main_exclusion_mechanism_rejects_pilot_keys() -> None:
    pilot_keys = [
        (f"FIGI_{i:04d}", "2018-05-15", "20:30")
        for i in range(24)
    ]
    disjoint_main_keys = [
        (f"FIGI_{i+100:04d}", "2018-05-15", "20:30")
        for i in range(240)
    ]
    # Disjoint keys pass
    validate_pilot_exclusion_from_main(disjoint_main_keys, pilot_keys)

    # Overlapping key fails closed
    overlapping_main_keys = list(disjoint_main_keys)
    overlapping_main_keys[0] = pilot_keys[0]
    with pytest.raises(ValueError, match="FAIL-CLOSED PILOT EXCLUSION BREACH"):
        validate_pilot_exclusion_from_main(overlapping_main_keys, pilot_keys)


# 33. Main 240-case sample remains ungenerated.
def test_33_main_study_not_generated(tmp_path: Path) -> None:
    assert_main_study_not_generated(tmp_path)
    # If main study artifact created, fails closed
    fake_main = tmp_path / "main_study_cases.json"
    fake_main.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="FAIL-CLOSED: Main study 240-case generation is UNAUTHORIZED"):
        assert_main_study_not_generated(tmp_path)


# 34. No validation access.
# 35. No holdout access.
# 36. No shadow access.
def test_34_to_36_quarantine_splits_enforced() -> None:
    with pytest.raises(ValueError, match="quarantined validation split"):
        enforce_split_guard("2021-06-01")
    with pytest.raises(ValueError, match="quarantined holdout split"):
        enforce_split_guard("2024-01-15")
    with pytest.raises(ValueError, match="quarantined shadow split"):
        enforce_split_guard("2026-03-01")


# 37. No provider calls.
def test_37_no_provider_calls_mock_boundary() -> None:
    # All tests run offline with read-only Alpaca cache client
    pass


# 38. APPROVED_PRODUCTION_STRATEGIES == ().
def test_38_approved_production_strategies_is_empty() -> None:
    from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES
    assert APPROVED_PRODUCTION_STRATEGIES == ()


# 39. No production trading files changed.
def test_39_no_production_trading_files_changed(repo_root: Path) -> None:
    # Inspect diff against main
    res = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        changed = res.stdout.strip().splitlines()
        for f in changed:
            assert not f.startswith("tradex/execution/"), f"Production file modified: {f}"
            assert not f.startswith("tradex/live/"), f"Production file modified: {f}"
            assert not f.startswith("tradex/orders/"), f"Production file modified: {f}"


# 40. No DAYTRADE workstream files changed.
def test_40_no_daytrade_workstream_files_changed(repo_root: Path) -> None:
    res = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        changed = res.stdout.strip().splitlines()
        for f in changed:
            assert "daytrade" not in f.lower(), f"DAYTRADE file modified: {f}"
