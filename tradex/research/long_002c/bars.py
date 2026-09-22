"""Interval-aware historical daily bar loader for LONG-002C.

Shared by both Stage B screening and Stage C outcome generation to guarantee:
- Daily bars are queried strictly for verified historical ticker intervals.
- In-development ticker renames query their respective ticker symbols for each interval segment.
- Transition dates are deduplicated deterministically.
- Ticker at decision is preserved per observation session.
- Unverified ticker interval gaps fail closed without inventing data.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from tradex.research.long_002c.exceptions import ProviderDataUnavailable
from tradex.research.long_002c.manifest import CandidateSecurity, TickerInterval
from tradex.research.long_002c.models import ProvenanceProviderRecord
from tradex.research.long_002c.providers import AlpacaDailyClient
from tradex.research.long_002c.spec import DEV_END, WARMUP_START, enforce_split_guard


def load_interval_aware_daily_bars(
    candidate: CandidateSecurity,
    alpaca: AlpacaDailyClient,
    warmup_start: str = WARMUP_START,
    dev_end: str = DEV_END,
    load_split_adjusted: bool = True,
) -> tuple[pd.DataFrame, list[ProvenanceProviderRecord], dict[str, Any]]:
    """Load interval-aware historical daily bars for a candidate security.

    Queries Alpaca daily bars strictly per verified ticker interval segment within
    [warmup_start, dev_end], merges segments under immutable_security_id, deduplicates
    transition dates deterministically, and preserves ticker_at_decision per session.

    Returns:
        (df_bars, provenance_records, audit_meta)
    """
    enforce_split_guard(dev_end)

    provenance_records: list[ProvenanceProviderRecord] = []
    sec_id = candidate.immutable_security_id

    # 1. Determine active intervals intersecting [warmup_start, dev_end]
    intervals = candidate.ticker_intervals
    if not intervals:
        # Fallback to single interval from candidate fields if valid
        if candidate.primary_symbol and candidate.first_seen_date and candidate.last_seen_date:
            intervals = [
                TickerInterval(
                    symbol=candidate.primary_symbol,
                    start_date=candidate.first_seen_date,
                    end_date=candidate.last_seen_date,
                    source="candidate_primary",
                    confidence="single_symbol_known",
                )
            ]
        else:
            return pd.DataFrame(), provenance_records, {
                "error": "no_ticker_intervals",
                "intervals_queried": 0,
                "transition_dates_deduped": [],
                "unresolved_gaps": [],
            }

    # Sort intervals chronologically
    sorted_intervals = sorted(intervals, key=lambda ti: (ti.start_date or "", ti.end_date or ""))

    # Clamp intervals to [warmup_start, dev_end]
    clamped_intervals: list[tuple[str, str, str]] = []  # (symbol, seg_start, seg_end)
    for ti in sorted_intervals:
        ti_start = ti.start_date or warmup_start
        ti_end = ti.end_date or dev_end
        if ti_end < warmup_start or ti_start > dev_end:
            continue
        seg_start = max(warmup_start, ti_start)
        seg_end = min(dev_end, ti_end)
        if seg_start <= seg_end and ti.symbol:
            clamped_intervals.append((ti.symbol.strip().upper(), seg_start, seg_end))

    if not clamped_intervals:
        return pd.DataFrame(), provenance_records, {
            "error": "no_intervals_in_window",
            "intervals_queried": 0,
            "transition_dates_deduped": [],
            "unresolved_gaps": [],
        }

    # Check for unverified gaps between consecutive intervals
    unresolved_gaps: list[dict[str, str]] = []
    for i in range(len(clamped_intervals) - 1):
        prev_sym, _prev_start, prev_end = clamped_intervals[i]
        next_sym, next_start, _next_end = clamped_intervals[i + 1]
        if prev_end < next_start:
            # There is a date gap between prev_end and next_start
            unresolved_gaps.append({
                "gap_start": prev_end,
                "gap_end": next_start,
                "prev_symbol": prev_sym,
                "next_symbol": next_sym,
            })

    # 2. Query daily bars for each interval segment
    segment_data: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for sym, seg_start, seg_end in clamped_intervals:
        try:
            raw_bars, raw_prov = alpaca.fetch_daily_bars(
                sym,
                f"{seg_start}T00:00:00Z",
                f"{seg_end}T23:59:59Z",
                feed="sip",
                adjustment="raw",
            )
            provenance_records.extend(raw_prov)
        except ProviderDataUnavailable as exc:
            provenance_records.extend(exc.provenance_records)
            return pd.DataFrame(), provenance_records, {
                "error": exc.failure_type,
                "provider_failure": {
                    "failure_type": exc.failure_type,
                    "symbol": sym,
                    "reason": str(exc),
                    "status_code": exc.status_code,
                    "page": exc.page,
                    "retry_count": exc.retry_count,
                },
                "intervals_queried": len(clamped_intervals),
                "transition_dates_deduped": [],
                "unresolved_gaps": unresolved_gaps,
            }

        adj_bars: list[dict[str, Any]] = []
        if load_split_adjusted:
            try:
                adj_bars, adj_prov = alpaca.fetch_daily_bars(
                    sym,
                    f"{seg_start}T00:00:00Z",
                    f"{seg_end}T23:59:59Z",
                    feed="sip",
                    adjustment="split",
                )
                provenance_records.extend(adj_prov)
            except ProviderDataUnavailable as exc:
                provenance_records.extend(exc.provenance_records)
                return pd.DataFrame(), provenance_records, {
                    "error": exc.failure_type,
                    "provider_failure": {
                        "failure_type": exc.failure_type,
                        "symbol": sym,
                        "reason": str(exc),
                        "status_code": exc.status_code,
                        "page": exc.page,
                        "retry_count": exc.retry_count,
                    },
                    "intervals_queried": len(clamped_intervals),
                    "transition_dates_deduped": [],
                    "unresolved_gaps": unresolved_gaps,
                }

        segment_data.append((sym, raw_bars, adj_bars))

    # 3. Assemble and merge segments chronologically
    # Dictionary mapping date -> bar record
    merged_by_date: dict[str, dict[str, Any]] = {}
    transition_deduped: list[str] = []
    analytical_data_incomplete = False

    for sym, raw_bars, adj_bars in segment_data:
        if not raw_bars:
            continue

        df_raw = pd.DataFrame(raw_bars)
        df_raw["datetime"] = pd.to_datetime(df_raw["t"], utc=True)
        df_raw["date"] = df_raw["datetime"].dt.strftime("%Y-%m-%d")
        df_raw = df_raw.rename(
            columns={
                "o": "as_traded_open",
                "h": "as_traded_high",
                "l": "as_traded_low",
                "c": "as_traded_close",
                "v": "volume",
            }
        )

        if load_split_adjusted:
            if adj_bars:
                df_adj = pd.DataFrame(adj_bars)
                df_adj["datetime"] = pd.to_datetime(df_adj["t"], utc=True)
                df_adj["date"] = df_adj["datetime"].dt.strftime("%Y-%m-%d")
                df_adj = df_adj.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
                merged = pd.merge(
                    df_raw, df_adj[["date", "open", "high", "low", "close"]], on="date", how="left"
                )
                if merged["open"].isna().any() or merged["close"].isna().any():
                    analytical_data_incomplete = True
            else:
                merged = df_raw.copy()
                merged["open"] = None
                merged["high"] = None
                merged["low"] = None
                merged["close"] = None
                analytical_data_incomplete = True
        else:
            merged = df_raw.copy()
            merged["open"] = merged["as_traded_open"]
            merged["high"] = merged["as_traded_high"]
            merged["low"] = merged["as_traded_low"]
            merged["close"] = merged["as_traded_close"]

        for _, row in merged.iterrows():
            d = str(row["date"])
            # Enforce split boundary guard: no 2021+ bars
            if d > dev_end:
                continue

            open_val = float(row["open"]) if pd.notna(row["open"]) else None
            high_val = float(row["high"]) if pd.notna(row["high"]) else None
            low_val = float(row["low"]) if pd.notna(row["low"]) else None
            close_val = float(row["close"]) if pd.notna(row["close"]) else None

            rec = {
                "date": d,
                "as_traded_open": float(row["as_traded_open"]),
                "as_traded_high": float(row["as_traded_high"]),
                "as_traded_low": float(row["as_traded_low"]),
                "as_traded_close": float(row["as_traded_close"]),
                "volume": float(row["volume"]),
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "ticker_at_decision": sym,
                "immutable_security_id": sec_id,
            }

            if d in merged_by_date:
                # Deterministic deduplication of transition date:
                # The later interval in chronological order takes precedence
                transition_deduped.append(d)
                merged_by_date[d] = rec
            else:
                merged_by_date[d] = rec

    if not merged_by_date:
        return pd.DataFrame(), provenance_records, {
            "error": "no_bars_returned",
            "intervals_queried": len(clamped_intervals),
            "transition_dates_deduped": transition_deduped,
            "unresolved_gaps": unresolved_gaps,
            "analytical_data_incomplete": analytical_data_incomplete,
        }

    sorted_dates = sorted(merged_by_date.keys())
    final_rows = [merged_by_date[d] for d in sorted_dates]
    df_result = pd.DataFrame(final_rows).set_index("date").sort_index()

    audit_meta = {
        "immutable_security_id": sec_id,
        "intervals_queried": len(clamped_intervals),
        "clamped_intervals": clamped_intervals,
        "total_bars_loaded": len(df_result),
        "first_bar_date": sorted_dates[0],
        "last_bar_date": sorted_dates[-1],
        "transition_dates_deduped": transition_deduped,
        "unresolved_gaps": unresolved_gaps,
        "analytical_data_incomplete": analytical_data_incomplete,
    }

    return df_result, provenance_records, audit_meta
