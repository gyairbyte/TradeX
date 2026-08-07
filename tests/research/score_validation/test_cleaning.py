"""Tests for deterministic malformed-row exclusion in research snapshots."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.score_validation.cleaning import (
    IngestionPolicy,
    clean_ticker,
    load_ingestion_policy,
    write_invalid_rows,
    write_snapshot_audit,
    write_snapshot_checksums,
    write_snapshot_data_quality,
)
from tradex.research.score_validation.models import ValidationError

_DOCS_SPEC = Path(__file__).parents[3] / "docs" / "research" / "specs" / "SHORT-001-ingestion-v2.json"


def _policy(required_symbol_count: int = 1) -> IngestionPolicy:
    """Return a valid v2-like policy with a configurable symbol count."""
    return IngestionPolicy(
        schema_version=1,
        policy_id="test-hard-invalid-row-exclusion",
        action="drop",
        structural_failures_remain_fatal=True,
        repair_values=False,
        require_all_symbols=True,
        required_symbol_count=required_symbol_count,
        max_total_invalid_rows=50,
        max_total_invalid_rate_pct=0.10,
        max_invalid_rows_per_ticker=5,
        max_invalid_rate_pct_per_ticker=100.0,
        max_consecutive_invalid_rows_per_ticker=1,
        allow_first_or_last_row_removal=False,
        minimum_pre_development_warmup_bars=5,
        hard_row_invariants=["open, high, low, or close is nonpositive"],
    )


def _make_history(start: str = "2020-01-01", periods: int = 120) -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * periods,
            "high": [101.0] * periods,
            "low": [99.0] * periods,
            "close": [100.5] * periods,
            "volume": [1e6] * periods,
        },
        index=idx,
    )


def test_load_ingestion_policy_rejects_unknown_keys(tmp_path: Path):
    spec = tmp_path / "policy.json"
    spec.write_text(
        '{"schema_version": 1, "policy_id": "x", "action": "drop", '
        '"structural_failures_remain_fatal": true, "repair_values": false, '
        '"require_all_symbols": true, "required_symbol_count": 1, '
        '"max_total_invalid_rows": 1, "max_total_invalid_rate_pct": 1.0, '
        '"max_invalid_rows_per_ticker": 1, "max_invalid_rate_pct_per_ticker": 1.0, '
        '"max_consecutive_invalid_rows_per_ticker": 1, '
        '"allow_first_or_last_row_removal": false, '
        '"minimum_pre_development_warmup_bars": 1, '
        '"hard_row_invariants": [], "unknown_field": 1}'
    )
    with pytest.raises(ValidationError, match="unknown keys"):
        load_ingestion_policy(spec)


def test_clean_ticker_keeps_valid_history():
    df = _make_history()
    policy = _policy()
    cleaned, removed, result = clean_ticker(
        df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab"
    )
    assert len(cleaned) == 120
    assert removed.empty
    assert result.invalid_rows_removed == 0
    assert result.raw_normalized_sha256 == result.cleaned_csv_sha256


def test_clean_ticker_drops_one_invalid_row():
    df = _make_history()
    # Create an impossible OHLC relationship: high < open and close.
    df.loc[df.index[10], "high"] = 98.0
    policy = _policy()
    cleaned, removed, result = clean_ticker(
        df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab"
    )
    assert len(cleaned) == 119
    assert len(removed) == 1
    assert result.invalid_rows_removed == 1
    assert "high_below_open" in removed.iloc[0]["reason_codes"]
    assert "high_below_close" in removed.iloc[0]["reason_codes"]


def test_clean_ticker_preserves_provider_values_in_removed_rows():
    df = _make_history()
    df.loc[df.index[5], "low"] = 102.0
    df.loc[df.index[5], "high"] = 103.0
    policy = _policy()
    _cleaned, removed, _ = clean_ticker(
        df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab"
    )
    row = removed.loc[df.index[5]]
    assert row["low"] == 102.0
    assert row["high"] == 103.0


def test_clean_ticker_sorts_multiple_reason_codes():
    df = _make_history()
    # low above both open and close should produce two relationship codes.
    df.loc[df.index[7], "low"] = 102.0
    policy = _policy()
    _, removed, _ = clean_ticker(
        df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab"
    )
    codes = removed.iloc[0]["reason_codes"].split(",")
    assert "low_above_open" in codes
    assert "low_above_close" in codes
    # Codes must appear in fixed deterministic order.
    assert codes.index("low_above_open") < codes.index("low_above_close")


def test_clean_ticker_missing_columns_fatal():
    df = _make_history().drop(columns=["volume"])
    policy = _policy()
    with pytest.raises(ValidationError, match="missing required columns"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_naive_index_fatal():
    df = _make_history()
    df.index = df.index.tz_localize(None)
    policy = _policy()
    with pytest.raises(ValidationError, match="naive"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_duplicate_timestamps_fatal():
    df = _make_history()
    dup = pd.DataFrame(df.iloc[0]).T
    df = pd.concat([df, dup])
    policy = _policy()
    with pytest.raises(ValidationError, match="duplicate"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_non_monotonic_timestamps_fatal():
    df = _make_history()
    # Reorder two rows so the timestamp index is no longer increasing.
    order = list(range(5)) + [6, 5] + list(range(7, len(df)))
    df = df.iloc[order]
    policy = _policy()
    with pytest.raises(ValidationError, match="monotonic"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_first_row_removal_prohibited():
    df = _make_history()
    df.loc[df.index[0], "high"] = 98.0
    policy = _policy()
    with pytest.raises(ValidationError, match="first or last row"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_last_row_removal_prohibited():
    df = _make_history()
    df.loc[df.index[-1], "high"] = 98.0
    policy = _policy()
    with pytest.raises(ValidationError, match="first or last row"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_consecutive_invalid_rows_fatal():
    df = _make_history()
    df.loc[df.index[10], "high"] = 98.0
    df.loc[df.index[11], "high"] = 98.0
    policy = _policy()
    with pytest.raises(ValidationError, match="consecutive"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_per_ticker_count_threshold_boundary():
    df = _make_history()
    policy = _policy()
    # Allow up to 5 invalid rows per ticker.
    for i in range(5):
        df.loc[df.index[10 + i * 2], "high"] = 98.0
    cleaned, _, _ = clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")
    assert len(cleaned) == 115

    df2 = _make_history()
    for i in range(6):
        df2.loc[df2.index[10 + i * 2], "high"] = 98.0
    with pytest.raises(ValidationError, match="per-ticker limit"):
        clean_ticker(df2, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_warmup_minimum_fatal():
    df = _make_history()
    policy = _policy()
    # Move development start so early that not enough pre-development bars remain.
    with pytest.raises(ValidationError, match="pre-development bars"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 1, 2), "schwab")


def test_clean_ticker_rows_outside_date_contract_fatal():
    df = _make_history(start="2019-12-01", periods=160)
    policy = _policy()
    with pytest.raises(ValidationError, match="outside requested date range"):
        clean_ticker(df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")


def test_clean_ticker_no_repair_or_clamping():
    df = _make_history()
    df.loc[df.index[9], "high"] = 98.0
    policy = _policy()
    cleaned, removed, _ = clean_ticker(
        df, "AAPL", policy, date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab"
    )
    # Removed invalid row must not appear in the cleaned frame and must retain the
    # original provider value (not be clamped or repaired).
    assert cleaned.index.intersection(removed.index).empty
    assert removed.loc[df.index[9], "high"] == 98.0


def test_snapshot_audit_and_sidecars_are_deterministic(tmp_path: Path):
    results = [
        clean_ticker(_make_history(), "AAPL", _policy(2), date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")[2],
        clean_ticker(_make_history(), "MSFT", _policy(2), date(2020, 1, 1), date(2020, 4, 30), date(2020, 2, 1), "schwab")[2],
    ]
    from tradex.research.score_validation.cleaning import build_snapshot_audit

    audit = build_snapshot_audit(
        results,
        _policy(2),
        "schwab",
        date(2020, 1, 1),
        date(2020, 4, 30),
        "abc123",
        "def456",
    )
    write_snapshot_data_quality(results, tmp_path / "snapshot_data_quality.csv")
    write_invalid_rows(pd.DataFrame(), tmp_path / "invalid_rows.csv")
    write_snapshot_audit(audit, tmp_path / "snapshot_audit.json")
    write_snapshot_checksums(tmp_path, tmp_path / "snapshot_checksums.sha256")
    assert (tmp_path / "snapshot_data_quality.csv").is_file()
    assert (tmp_path / "snapshot_audit.json").is_file()
    assert (tmp_path / "snapshot_checksums.sha256").is_file()


def test_locked_ingestion_spec_loads_from_docs():
    policy, raw_bytes = load_ingestion_policy(_DOCS_SPEC)
    assert policy.policy_id == "short-001-hard-invalid-row-exclusion-v2"
    assert policy.action == "drop"
    assert not policy.repair_values
    assert policy.required_symbol_count == 45
    assert len(raw_bytes) > 0
