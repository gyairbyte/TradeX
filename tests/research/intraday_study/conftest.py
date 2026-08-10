"""Deterministic fixtures for the INTRA-001D real-data study adapter tests."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tradex.research.intraday_engine.engine import TickerInput
from tradex.research.intraday_engine.models import as_json_dict
from tradex.research.intraday_engine.normalize import bars_to_dataframe
from tradex.research.intraday_engine.spec import load_spec
from tradex.research.intraday_engine.synthetic import generate_synthetic_inputs

SPEC_PATH = Path(__file__).resolve().parents[3] / "docs/research/specs/INTRA-001-v1.json"
DATASET_PLAN_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/research/specs/INTRA-001B-dataset-v1.json"
)


def _effective_month(session_date: date) -> str:
    return session_date.strftime("%Y-%m")


def _write_ticker_parquet(
    root: Path,
    ticker_input: TickerInput,
    effective_month: str,
) -> str:
    """Write all session bars for a ticker to a symbol-month parquet."""
    all_bars = []
    for session in sorted(ticker_input.sessions, key=lambda s: s.session_date):
        all_bars.extend(session.bars.values())
    all_bars = sorted(all_bars, key=lambda b: b.bar_start)
    df = bars_to_dataframe(all_bars)
    df = df[["open", "high", "low", "close", "volume"]]
    rel_path = f"{effective_month}/{ticker_input.ticker}.parquet"
    file_path = root / "ohlcv" / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(file_path, index=True)
    return rel_path


def _manifest_row(
    ticker_input: TickerInput,
    rel_path: str,
    effective_month: str,
    sha256: str,
    file_size: int,
    file_path: Path,
) -> dict:
    all_bars = []
    for session in sorted(ticker_input.sessions, key=lambda s: s.session_date):
        all_bars.extend(session.bars.values())
    all_bars = sorted(all_bars, key=lambda b: b.bar_start)
    start_utc = all_bars[0].bar_start.isoformat()
    end_utc = all_bars[-1].bar_start.isoformat()
    n_sessions = len(ticker_input.sessions)
    n_bars = len(all_bars)
    return {
        "manifest_id": f"{effective_month}/{ticker_input.ticker}",
        "symbol": ticker_input.ticker,
        "effective_month": effective_month,
        "feed": "sip",
        "timeframe": "5Min",
        "adjustment": "raw",
        "start_utc": start_utc,
        "end_utc": end_utc,
        "regular_session_bars": n_bars,
        "regular_session_sessions": n_sessions,
        "missing_bars": 0,
        "missing_bar_rate_pct": 0.0,
        "pre_dedup_duplicate_bars": 0,
        "duplicate_bars": 0,
        "duplicate_bar_rate_pct": 0.0,
        "malformed_rows": 0,
        "malformed_row_rate_pct": 0.0,
        "zero_volume_bars": 0,
        "zero_volume_bar_rate_pct": 0.0,
        "invalid_ohlc_rows": 0,
        "off_grid_bars": 0,
        "premarket_removed": 0,
        "after_hours_removed": 0,
        "early_close_removed": 0,
        "file_size_bytes": file_size,
        "sha256": sha256,
        "relative_path": rel_path,
        "requested_symbol": ticker_input.ticker,
        "returned_symbol": ticker_input.ticker,
        "pagination_complete": True,
        "page_count": 1,
        "pre_normalization_metrics_available": True,
    }


def _data_quality_row(
    ticker_input: TickerInput,
    effective_month: str,
    split: str,
    rel_path: str,
    sha256: str,
) -> dict:
    # split is passed explicitly so tests can target development/validation/holdout months
    n_sessions = len(ticker_input.sessions)
    n_bars = sum(len(s.bars) for s in ticker_input.sessions)
    return {
        "symbol": ticker_input.ticker,
        "effective_month": effective_month,
        "split": split,
        "expected_sessions": n_sessions,
        "actual_sessions": n_sessions,
        "expected_bars": n_bars,
        "actual_bars": n_bars,
        "missing_bars": 0,
        "missing_bar_rate_pct": 0.0,
        "zero_volume_bars": 0,
        "zero_volume_bar_rate_pct": 0.0,
        "invalid_ohlc_rows": 0,
        "off_grid_bars": 0,
        "premarket_removed": 0,
        "after_hours_removed": 0,
        "early_close_removed": 0,
        "ohlc_consistency_violations": 0,
        "provider_feed": "sip",
        "timeframe": "5Min",
        "adjustment": "raw",
        "file_sha256": sha256,
        "relative_path": rel_path,
        "requested_symbol": ticker_input.ticker,
        "returned_symbol": ticker_input.ticker,
        "symbol_mismatch": False,
        "pagination_complete": True,
        "rejected": False,
        "rejection_reason": "",
        "pre_normalization_metrics_available": True,
        "pre_dedup_duplicate_bars": 0,
        "duplicate_bars": 0,
        "duplicate_bar_rate_pct": 0.0,
        "malformed_rows": 0,
        "malformed_row_rate_pct": 0.0,
        "file_sha256_match": True,
    }


def _universe_row(
    ticker_input: TickerInput,
    effective_month: str,
    pit_date: str,
    rank: int,
) -> dict:
    return {
        "effective_month": effective_month,
        "pit_date": pit_date,
        "ticker": ticker_input.ticker,
        "stratum": "etf" if ticker_input.meta.is_etf else "stock",
        "reference_provider": "massive",
        "security_type_category": "etf" if ticker_input.meta.is_etf else "common_stock",
        "primary_exchange": "XNYS",
        "duplicate_status": "unique",
        "prior_close": ticker_input.meta.prior_close,
        "valid_prior_session_count": 20,
        "median_prior_20_dollar_volume": ticker_input.meta.prior_20_median_dollar_volume,
        "liquidity_rank": rank,
        "included": True,
        "exclusion_reason": "",
        "source_snapshot_sha256": "a" * 64,
        "ohlcv_manifest_id": f"{effective_month}/{ticker_input.ticker}",
    }


def _append_month(
    tmp_path: Path,
    spec,
    effective_month: str,
    start_date: date,
    pit_date: str,
    seed: int = 42,
    n_sessions: int = 42,
) -> list:
    """Generate one month of synthetic data and append it to an existing dataset root."""
    (tmp_path / "ohlcv").mkdir(parents=True, exist_ok=True)
    (tmp_path / "universe").mkdir(parents=True, exist_ok=True)

    inputs = generate_synthetic_inputs(
        spec,
        seed=seed,
        n_stock_tickers=2,
        n_etf_tickers=1,
        n_sessions=n_sessions,
        start_date=start_date,
    )

    from tradex.research.intraday_study.split import split_for_effective_month

    split = split_for_effective_month(effective_month)
    manifest_records = []
    dq_rows = []
    universe_rows = []

    for i, ti in enumerate(inputs):
        rel = _write_ticker_parquet(tmp_path, ti, effective_month)
        file_path = tmp_path / "ohlcv" / rel
        import hashlib

        sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        file_size = file_path.stat().st_size
        manifest_records.append(_manifest_row(ti, rel, effective_month, sha, file_size, file_path))
        dq_rows.append(_data_quality_row(ti, effective_month, split, rel, sha))
        universe_rows.append(_universe_row(ti, effective_month, pit_date, i + 1))

    return inputs, manifest_records, dq_rows, universe_rows


def _write_dataset_files(tmp_path: Path, manifest_records: list, dq_rows: list, universe_rows: list) -> None:
    """Write the canonical CSV/JSON files for a dataset root."""
    # manifest.lock.json
    lock = {"schema_version": "1.0", "files": manifest_records}
    (tmp_path / "manifest.lock.json").write_text(
        json.dumps(as_json_dict(lock), indent=2), encoding="utf-8"
    )

    # ohlcv_manifest.csv
    ohlcv_manifest_path = tmp_path / "ohlcv" / "ohlcv_manifest.csv"
    pd.DataFrame(manifest_records).to_csv(ohlcv_manifest_path, index=False)

    # data_quality.csv
    dq_path = tmp_path / "ohlcv" / "data_quality.csv"
    pd.DataFrame(dq_rows).to_csv(dq_path, index=False)

    # universe_manifest.csv
    universe_path = tmp_path / "universe" / "universe_manifest.csv"
    pd.DataFrame(universe_rows).to_csv(universe_path, index=False)

    # dataset_state.json
    (tmp_path / "dataset_state.json").write_text(
        json.dumps({"dataset_id": "INTRA-001B-DATASET-TEST", "version": "1.0"}), encoding="utf-8"
    )

    # dataset_plan.lock.json — copy the committed locked plan byte-for-byte so the
    # CLI hash verification matches docs/research/specs/INTRA-001B-dataset-v1.json.
    if DATASET_PLAN_PATH.is_file():
        import shutil

        shutil.copy2(DATASET_PLAN_PATH, tmp_path / "dataset_plan.lock.json")
    else:
        (tmp_path / "dataset_plan.lock.json").write_text(
            json.dumps({"dataset_id": "INTRA-001B-DATASET-TEST"}, indent=2),
            encoding="utf-8",
        )


def _build_dataset(tmp_path: Path, n_sessions: int = 42, effective_month: str = "2025-02"):
    """Create a minimal, deterministic dataset root in tmp_path."""
    spec, _ = load_spec(SPEC_PATH)
    inputs, manifest_records, dq_rows, universe_rows = _append_month(
        tmp_path,
        spec,
        effective_month=effective_month,
        start_date=date(2025, 1, 2),
        pit_date="2025-01-31",
        seed=42,
    )
    _write_dataset_files(tmp_path, manifest_records, dq_rows, universe_rows)
    return inputs, spec


@pytest.fixture
def synthetic_dataset(tmp_path_factory):
    """A temporary dataset root with 2 stocks + 1 ETF for the development split."""
    tmp_path = tmp_path_factory.mktemp("intra001d-dataset")
    _build_dataset(tmp_path)
    return tmp_path


@pytest.fixture
def synthetic_split_dataset(tmp_path_factory):
    """A temporary dataset root with 2 stocks + 1 ETF across dev/val/holdout months."""
    tmp_path = tmp_path_factory.mktemp("intra001d-split-dataset")
    spec, _ = load_spec(SPEC_PATH)
    months = [
        ("2025-02", date(2025, 1, 2), "2025-01-31"),
        ("2025-08", date(2025, 7, 1), "2025-07-31"),
        ("2025-12", date(2025, 11, 3), "2025-11-30"),
    ]
    all_manifest: list = []
    all_dq: list = []
    all_universe: list = []
    all_inputs: list = []
    for effective_month, start_date, pit_date in months:
        inputs, manifest_records, dq_rows, universe_rows = _append_month(
            tmp_path, spec, effective_month, start_date, pit_date, seed=42
        )
        all_inputs.extend(inputs)
        all_manifest.extend(manifest_records)
        all_dq.extend(dq_rows)
        all_universe.extend(universe_rows)
    _write_dataset_files(tmp_path, all_manifest, all_dq, all_universe)
    return tmp_path


@pytest.fixture
def spec():
    return load_spec(SPEC_PATH)[0]
