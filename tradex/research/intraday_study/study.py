"""Run the locked INTRA-001 study on a real-data split."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from tradex.research.intraday_engine.engine import TickerInput, run_study
from tradex.research.intraday_engine.gates import SampleMinimums
from tradex.research.intraday_engine.models import StudyResult
from tradex.research.intraday_engine.spec import IntradaySpec

from .loader import load_symbol_month
from .manifest import (
    SymbolMonth,
    get_symbol_months_for_split,
    load_data_quality,
    load_universe_manifest,
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
        # If the symbol is not in the monthly PIT universe, skip it.
        if universe_row is None or not universe_row.get("included", False):
            continue
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


def run_split(
    dataset_root: Path,
    split: SplitName,
    spec: IntradaySpec,
    generated_at: datetime,
    *,
    sample_minimums: SampleMinimums | None = None,
    evidence_eligible: bool = False,
    symbol_months: list[SymbolMonth] | None = None,
) -> tuple[StudyResult, list[TickerInput]]:
    """Run the locked study on one split."""
    dataset_root = Path(dataset_root).expanduser().resolve()
    dq_path = dataset_root / "ohlcv" / "data_quality.csv"
    universe_path = dataset_root / "universe" / "universe_manifest.csv"

    data_quality_df = load_data_quality(dq_path)
    universe_df = load_universe_manifest(universe_path)

    ticker_inputs = load_ticker_inputs_for_split(
        dataset_root, split, data_quality_df, universe_df, symbol_months
    )

    result = run_study(
        ticker_inputs,
        spec,
        synthetic=False,
        evidence_eligible=evidence_eligible,
        generated_at=generated_at,
        sample_minimums=sample_minimums,
    )
    return result, ticker_inputs
