"""Run the locked INTRA-001 study on a real-data split."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.intraday_engine.engine import TickerInput, run_study
from tradex.research.intraday_engine.gates import SampleMinimums
from tradex.research.intraday_engine.models import StudyResult
from tradex.research.intraday_engine.spec import IntradaySpec

from .loader import load_symbol_month
from .manifest import (
    SymbolMonth,
    get_symbol_months_for_split,
    verify_dataset_bundle,
)
from .split import SplitName


class StudyError(Exception):
    """Raised when a study cannot be run or a required gate is violated."""


def _lookup_universe_row(
    universe_df: pd.DataFrame,
    symbol: str,
    effective_month: str,
) -> pd.Series | None:
    rows = universe_df[
        (universe_df["ticker"] == symbol) & (universe_df["effective_month"] == effective_month)
    ]
    if rows.empty:
        return None
    return rows.iloc[0]


def _lookup_data_quality_row(
    dq_df: pd.DataFrame,
    symbol: str,
    effective_month: str,
) -> pd.Series | None:
    rows = dq_df[
        (dq_df["symbol"] == symbol) & (dq_df["effective_month"] == effective_month)
    ]
    if rows.empty:
        return None
    return rows.iloc[0]


def _is_rejected_for_data_quality(row: pd.Series) -> bool:
    """Return True when a data_quality row represents a rejected symbol-month."""
    return (
        str(row.get("rejected")).lower() == "true"
        or str(row.get("symbol_mismatch")).lower() == "true"
        or str(row.get("file_sha256_match")).lower() == "false"
        or str(row.get("pagination_complete")).lower() == "false"
    )


def compute_monthly_rejection_summary(
    data_quality_df: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Return per-effective-month rejected counts, percentages, and per-split counts."""
    summary: dict[str, dict[str, Any]] = {}
    for month, group in data_quality_df.groupby("effective_month"):
        total = len(group)
        rejected_rows = [row for _, row in group.iterrows() if _is_rejected_for_data_quality(row)]
        rejected = len(rejected_rows)
        by_split: dict[str, int] = {}
        for row in rejected_rows:
            split = str(row.get("split")) if not pd.isna(row.get("split")) else "unknown"
            by_split[split] = by_split.get(split, 0) + 1
        summary[month] = {
            "total": total,
            "rejected": rejected,
            "rejected_pct": (rejected / total * 100.0) if total else 0.0,
            "rejected_by_split": by_split,
        }
    return summary


def load_ticker_inputs_for_split(
    dataset_root: Path,
    split: SplitName,
    data_quality_df: pd.DataFrame,
    universe_df: pd.DataFrame,
    symbol_months: list[SymbolMonth] | None = None,
) -> list[TickerInput]:
    """Load all symbol-months for a split into TickerInput objects."""
    if symbol_months is None:
        symbol_months = get_symbol_months_for_split(data_quality_df, split)

    inputs: list[TickerInput] = []
    for sm in symbol_months:
        universe_row = _lookup_universe_row(universe_df, sm.symbol, sm.effective_month)
        dq_row = _lookup_data_quality_row(data_quality_df, sm.symbol, sm.effective_month)
        try:
            ti = load_symbol_month(
                dataset_root,
                sm,
                universe_row,
                dq_row,
                normalize=True,
            )
        except Exception as e:
            raise StudyError(f"failed to load {sm.symbol}/{sm.effective_month}: {e}") from e
        inputs.append(ti)
    return inputs


def _monthly_sufficiency_failures(
    monthly_summary: dict[str, dict[str, float | int]],
    max_rejected_pct: float = 5.0,
) -> tuple[bool, list[str]]:
    """Return (failed, reasons) if any monthly universe exceeds the locked rejection cap."""
    reasons: list[str] = []
    failed = False
    for month, info in sorted(monthly_summary.items()):
        if info["rejected_pct"] > max_rejected_pct:
            failed = True
            reasons.append(
                f"monthly_rejection_{month}_{info['rejected']}/{info['total']}_"
                f"{info['rejected_pct']:.2f}%_above_{max_rejected_pct}%"
            )
    return failed, reasons


def run_split(
    dataset_root: Path,
    split: SplitName,
    spec: IntradaySpec,
    generated_at: datetime,
    *,
    sample_minimums: SampleMinimums | None = None,
    evidence_eligible: bool = False,
    symbol_months: list[SymbolMonth] | None = None,
) -> tuple[StudyResult, list[TickerInput], dict[str, dict[str, Any]]]:
    """Run the locked study on one split.

    The full manifest/data-quality/universe bundle is verified before any split
    is loaded so missing rows, duplicates, identity mismatches, or path traversal
    fail closed.
    """
    dataset_root = Path(dataset_root).expanduser().resolve()

    verified = verify_dataset_bundle(dataset_root, expected_count=None)
    if symbol_months is None:
        symbol_months = verified.by_split.get(split, [])

    monthly_rejection_summary = compute_monthly_rejection_summary(verified.data_quality)
    extra_fail, extra_reasons = _monthly_sufficiency_failures(monthly_rejection_summary)

    ticker_inputs = load_ticker_inputs_for_split(
        dataset_root,
        split,
        verified.data_quality,
        verified.universe_manifest,
        symbol_months,
    )

    result = run_study(
        ticker_inputs,
        spec,
        synthetic=False,
        evidence_eligible=evidence_eligible,
        generated_at=generated_at,
        sample_minimums=sample_minimums,
        extra_sufficiency_fail=extra_fail,
        extra_sufficiency_reasons=extra_reasons,
    )
    return result, ticker_inputs, monthly_rejection_summary
