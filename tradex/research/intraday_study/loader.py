"""Load symbol-month Parquet files into TickerInput objects for the INTRA-001D study."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from tradex.research.intraday_engine.engine import TickerInput
from tradex.research.intraday_engine.models import DataQualitySummary, TickerMeta
from tradex.research.intraday_engine.normalize import (
    NormalizationError,
    evaluate_data_contract,
    evaluate_data_sufficiency,
    normalize_to_sessions,
)

from .manifest import SymbolMonth


class LoaderError(Exception):
    """Raised when a symbol-month cannot be loaded or normalized."""


def _clean_str(value: Any) -> str:
    if pd.isna(value) or value is None:
        return ""
    return str(value)


def _float_or_none(value: Any) -> float | None:
    if pd.isna(value) or value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_false(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _build_meta_from_universe(
    symbol: str,
    month: str,
    universe_row: pd.Series | None,
    data_quality_row: pd.Series | None,
) -> TickerMeta:
    """Build TickerMeta from universe and data-quality records."""
    is_etf = False
    security_type = "common_stock"
    prior_close: float | None = None
    median_dv: float | None = None
    included = False
    if universe_row is not None:
        is_etf = _clean_str(universe_row.get("stratum")).lower() == "etf"
        security_type = _clean_str(universe_row.get("security_type_category")) or security_type
        prior_close = _float_or_none(universe_row.get("prior_close"))
        median_dv = _float_or_none(universe_row.get("median_prior_20_dollar_volume"))
        included = _bool_or_false(universe_row.get("included"))

    # Data-quality rejection overrides eligibility, but universe inclusion is the
    # primary source of truth for the monthly PIT universe.
    rejected = False
    rejection_reason = ""
    if data_quality_row is not None:
        rejected = _bool_or_false(data_quality_row.get("rejected"))
        rejection_reason = _clean_str(data_quality_row.get("rejection_reason"))
        # A missing-bar or zero-volume rejection is a data-sufficiency gate.
        # Pre-normalization unavailability is handled at the DataQualitySummary level.
        if rejected and "missing_bar_rate" in rejection_reason:
            included = False

    return TickerMeta(
        ticker=symbol,
        is_etf=is_etf,
        is_eligible=included,
        prior_close=prior_close,
        prior_20_median_dollar_volume=median_dv,
        security_type=security_type,
    )


def _build_quality_summary_from_row(
    symbol: str,
    row: pd.Series,
    effective_month: str,
) -> DataQualitySummary:
    """Build a DataQualitySummary from the locked data_quality.csv row."""
    def _int(col: str, default: int = 0) -> int:
        v = row.get(col)
        if pd.isna(v) or v is None or v == "":
            return default
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

    pre_norm = row.get("pre_normalization_metrics_available")
    if isinstance(pre_norm, bool):
        pre_norm_available = pre_norm
    elif isinstance(pre_norm, str):
        pre_norm_available = pre_norm.lower() == "true"
    else:
        # Default to False because the stored Parquet is already normalized/deduplicated.
        pre_norm_available = False

    # If this row reports missing bars, reflect them in the summary.
    expected = _int("expected_bars")
    actual = _int("actual_bars")
    missing = _int("missing_bars")
    valid_bars = max(0, actual - missing) if expected else 1
    sessions = _int("actual_sessions") or _int("expected_sessions") or 1

    return DataQualitySummary(
        ticker=symbol,
        total_rows=actual,
        duplicate_timestamps=0,
        naive_timestamps=0,
        off_grid_bars=_int("off_grid_bars"),
        invalid_ohlc_rows=_int("invalid_ohlc_rows"),
        non_finite_rows=0,
        zero_volume_bars=_int("zero_volume_bars"),
        missing_bars=missing,
        valid_bars=valid_bars,
        sessions=sessions,
        pre_normalization_metrics_available=pre_norm_available,
    )


def _evaluation_dates_for_month(
    sessions: list[Any],
    effective_month: str,
) -> set[date]:
    """Return the session dates inside the effective month."""
    year, month = int(effective_month[:4]), int(effective_month[5:7])
    return {s.session_date for s in sessions if s.session_date.year == year and s.session_date.month == month}


def load_symbol_month(
    dataset_root: Path,
    symbol_month: SymbolMonth,
    universe_row: pd.Series | None,
    data_quality_row: pd.Series | None,
    *,
    normalize: bool = True,
    ohlcv_subdir: str = "ohlcv",
) -> TickerInput:
    """Load one symbol-month into a TickerInput.

    If ``normalize`` is True, the parquet file is loaded and normalized; otherwise
    a zero-session TickerInput with a CSV-derived DataQualitySummary is returned.
    """
    symbol = symbol_month.symbol
    month = symbol_month.effective_month
    parquet_path = Path(dataset_root).expanduser().resolve() / ohlcv_subdir / symbol_month.relative_path

    meta = _build_meta_from_universe(symbol, month, universe_row, data_quality_row)

    # If the monthly PIT universe did not include this symbol, do not load bars.
    if not meta.is_eligible:
        summary = _build_quality_summary_from_row(symbol, data_quality_row, month) if data_quality_row is not None else DataQualitySummary(
            ticker=symbol,
            total_rows=0,
            duplicate_timestamps=0,
            naive_timestamps=0,
            off_grid_bars=0,
            invalid_ohlc_rows=0,
            non_finite_rows=0,
            zero_volume_bars=0,
            missing_bars=0,
            valid_bars=0,
            sessions=0,
            pre_normalization_metrics_available=False,
        )
        return TickerInput(ticker=symbol, meta=meta, sessions=[], quality_summary=summary)

    if not parquet_path.is_file():
        raise LoaderError(f"parquet file not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    # Ensure standard lowercase column names.
    df = df.rename(columns=lambda c: str(c).lower().strip())
    if "datetime" not in str(df.index.name).lower():
        # Parquet index may be named 'datetime' already; if not, try to reset.
        pass

    if normalize:
        try:
            sessions, summary = normalize_to_sessions(df, symbol)
            # For real stored Parquet, pre-normalization duplicate/malformed counts
            # are not recoverable. The caller is responsible for setting this flag
            # from the locked data_quality.csv row.
            if data_quality_row is not None:
                pre_norm = data_quality_row.get("pre_normalization_metrics_available")
                if isinstance(pre_norm, bool):
                    summary.pre_normalization_metrics_available = pre_norm
                elif isinstance(pre_norm, str):
                    summary.pre_normalization_metrics_available = pre_norm.lower() == "true"
                else:
                    summary.pre_normalization_metrics_available = False
            eval_dates = _evaluation_dates_for_month(sessions, month)
            return TickerInput(
                ticker=symbol,
                meta=meta,
                sessions=sessions,
                quality_summary=summary,
                evaluation_session_dates=eval_dates,
            )
        except NormalizationError as e:
            raise LoaderError(f"normalization failed for {symbol}/{month}: {e}") from e
    else:
        summary = _build_quality_summary_from_row(symbol, data_quality_row, month)
        return TickerInput(ticker=symbol, meta=meta, sessions=[], quality_summary=summary)


def is_symbol_month_tradeable(ticker_input: TickerInput) -> bool:
    """Return True if the symbol-month has passed data contract and sufficiency."""
    if not ticker_input.meta.is_eligible:
        return False
    if ticker_input.quality_summary is None:
        return False
    contract_ok, _ = evaluate_data_contract(ticker_input.quality_summary)
    suff_ok, _ = evaluate_data_sufficiency(ticker_input.quality_summary)
    return contract_ok and suff_ok
