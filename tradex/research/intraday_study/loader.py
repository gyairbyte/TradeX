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

    # Observed data-quality rejections (e.g. missing_bar_rate) and provider contract
    # failures (symbol mismatch, pagination incomplete, hash mismatch) disable trading
    # for that symbol-month.  Pre-normalization unavailability is a global evidence
    # limitation that keeps the split disposition `inconclusive`; it does not, by
    # itself, make the symbol-month ineligible.
    rejected = False
    contract_fail = False
    if data_quality_row is not None:
        if _bool_or_false(data_quality_row.get("symbol_mismatch")):
            contract_fail = True
        if _bool_or_false(data_quality_row.get("pagination_complete")) is False:
            contract_fail = True
        if _bool_or_false(data_quality_row.get("file_sha256_match")) is False:
            contract_fail = True

        if _bool_or_false(data_quality_row.get("rejected")):
            reason_text = _clean_str(data_quality_row.get("rejection_reason"))
            reasons = [r.strip().lower() for r in reason_text.split(";") if r.strip()]
            non_pre_norm = [
                r for r in reasons if r != "pre_normalization_metrics_unavailable"
            ]
            rejected = bool(non_pre_norm)

    return TickerMeta(
        ticker=symbol,
        is_etf=is_etf,
        is_eligible=included and not rejected and not contract_fail,
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
    pre_norm_available = _bool_or_none(pre_norm) if pre_norm is not None else False
    if pre_norm_available is None:
        # Default to False because the stored Parquet is already normalized/deduplicated.
        pre_norm_available = False

    # Use the locked data-quality row for counts.  expected_sessions is the calendar
    # denominator for the per-symbol missing-bar-rate check.
    actual = _int("actual_bars")
    missing = _int("missing_bars")
    valid_bars = max(0, actual - missing)
    sessions = _int("expected_sessions")
    if sessions == 0:
        sessions = _int("actual_sessions")

    return DataQualitySummary(
        ticker=symbol,
        total_rows=actual,
        duplicate_timestamps=_int("pre_dedup_duplicate_bars"),
        naive_timestamps=0,
        off_grid_bars=_int("off_grid_bars"),
        invalid_ohlc_rows=_int("invalid_ohlc_rows"),
        non_finite_rows=_int("malformed_rows"),
        zero_volume_bars=_int("zero_volume_bars"),
        missing_bars=missing,
        valid_bars=valid_bars,
        sessions=sessions,
        pre_normalization_metrics_available=pre_norm_available,
        effective_month=effective_month,
        pagination_complete=_bool_or_none(row.get("pagination_complete")),
        symbol_mismatch=_bool_or_none(row.get("symbol_mismatch")),
        file_sha256_match=_bool_or_none(row.get("file_sha256_match")),
        requested_symbol=_clean_str(row.get("requested_symbol")),
        returned_symbol=_clean_str(row.get("returned_symbol")),
    )


def _bool_or_none(value: Any) -> bool | None:
    if pd.isna(value) or value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _apply_data_quality_flags_to_summary(
    summary: DataQualitySummary,
    row: pd.Series,
    effective_month: str,
) -> None:
    """Overlay the locked data_quality.csv contract/sufficiency flags onto a normalized summary."""
    pre_norm = row.get("pre_normalization_metrics_available")
    pre_norm_available = _bool_or_none(pre_norm) if pre_norm is not None else False
    summary.pre_normalization_metrics_available = bool(pre_norm_available) if pre_norm_available is not None else False

    summary.effective_month = effective_month
    summary.pagination_complete = _bool_or_none(row.get("pagination_complete"))
    summary.symbol_mismatch = _bool_or_none(row.get("symbol_mismatch"))
    summary.file_sha256_match = _bool_or_none(row.get("file_sha256_match"))
    summary.requested_symbol = _clean_str(row.get("requested_symbol"))
    summary.returned_symbol = _clean_str(row.get("returned_symbol"))

    # When pre-normalization metrics are available, prefer the locked builder counts
    # for duplicate/malformed rows over recomputation from the stored Parquet.
    if summary.pre_normalization_metrics_available is True:
        pre_dup = row.get("pre_dedup_duplicate_bars")
        if pre_dup is not None and not pd.isna(pre_dup):
            try:
                summary.duplicate_timestamps = max(0, int(float(pre_dup)))
            except (TypeError, ValueError):
                pass
        malformed = row.get("malformed_rows")
        if malformed is not None and not pd.isna(malformed):
            try:
                summary.non_finite_rows = max(0, int(float(malformed)))
            except (TypeError, ValueError):
                pass


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

    if data_quality_row is None:
        raise LoaderError(f"missing data_quality row for {symbol}/{month}")
    if universe_row is None:
        raise LoaderError(f"missing universe_manifest row for {symbol}/{month}")

    meta = _build_meta_from_universe(symbol, month, universe_row, data_quality_row)

    # If the monthly PIT universe did not include this symbol or it is data-quality
    # rejected, do not load bars.  The quality summary is still returned so the
    # split-level data-sufficiency/contract evaluation sees the symbol-month.
    if not meta.is_eligible:
        summary = _build_quality_summary_from_row(symbol, data_quality_row, month)
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
            _apply_data_quality_flags_to_summary(summary, data_quality_row, month)
            eval_dates = _evaluation_dates_for_month(sessions, month)
            return TickerInput(
                ticker=symbol,
                meta=meta,
                sessions=sessions,
                quality_summary=summary,
                evaluation_session_dates=eval_dates,
                parquet_loaded=True,
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
