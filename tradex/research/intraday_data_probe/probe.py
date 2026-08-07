"""Execute the INTRA-001B Schwab five-minute historical-coverage probe."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import (
    ProviderAuthenticationError,
    ProviderResponseError,
    ProviderTransientError,
    _get_schwab_client,
    _normalize_schwab_candles,
)

from .alpaca_client import AlpacaRestClient, make_alpaca_client
from .models import ProbeDecision, ProbeReport, ProbeRequestRecord
from .spec import IntradayProbeSpec


def _format_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")


def _format_ny(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_candles(candles: list[dict], resp: Any) -> str:
    if hasattr(resp, "content") and isinstance(resp.content, bytes):
        return _sha256_bytes(resp.content)
    payload = json.dumps(
        {"candles": candles} if candles else {"candles": []},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _dataframe_to_canonical_bytes(df: pd.DataFrame) -> bytes:
    """Return deterministic UTF-8 CSV bytes for a canonical OHLCV DataFrame."""
    if df.empty:
        return b""
    ordered = ["open", "high", "low", "close", "volume"]
    cols = [c for c in ordered if c in df.columns]
    out = df[cols].copy()
    out.index.name = "datetime"
    csv = out.to_csv(
        index=True,
        date_format="%Y-%m-%dT%H:%M:%S%z",
        float_format="%.10g",
        encoding="utf-8",
    )
    return csv.encode("utf-8")


def _sha256_dataframe(df: pd.DataFrame) -> str:
    return _sha256_bytes(_dataframe_to_canonical_bytes(df))


def _eastern_bounds(
    start_date: date, end_date: date, tz_name: str = "America/New_York"
) -> tuple[datetime, datetime]:
    """Return (start, end) as timezone-aware Eastern and UTC datetimes."""
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(start_date, dt_time.min, tzinfo=tz)
    end_local = datetime.combine(end_date, dt_time(23, 59, 59, 999999), tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _load_calendar(exchange_calendar: str) -> Any:
    import exchange_calendars as xcals

    return xcals.get_calendar(exchange_calendar)


def _is_full_session(calendar: Any, session_date: date) -> bool:
    close = calendar.session_close(session_date).tz_convert("America/New_York")
    return close.time() == dt_time(16, 0)


def _is_early_close(calendar: Any, session_date: date) -> bool:
    return calendar.is_session(session_date) and not _is_full_session(calendar, session_date)


def _session_grid_times(calendar: Any, session_date: date) -> pd.DatetimeIndex:
    """Return the expected bar-start timestamps for a single session (UTC)."""
    open_utc = calendar.session_open(session_date).tz_convert(UTC)
    close_utc = calendar.session_close(session_date).tz_convert(UTC)
    return pd.date_range(start=open_utc, end=close_utc, freq="5min", inclusive="left")


def _expected_primary_sessions_and_bars(
    calendar: Any,
    start_date: date,
    end_date: date,
    exclude_early_close: bool,
) -> tuple[int, int]:
    """Count sessions and expected five-minute bars using the exact XNYS grid."""
    if end_date < start_date:
        return 0, 0
    sessions = list(calendar.sessions_in_range(start_date, end_date))
    if exclude_early_close:
        sessions = [s for s in sessions if _is_full_session(calendar, s.date())]
    bar_count = 0
    for s in sessions:
        bar_count += len(_session_grid_times(calendar, s.date()))
    return len(sessions), bar_count


def _session_bar_end_grid(calendar: Any, session_date: date) -> pd.DatetimeIndex:
    """Return the bar-end timestamp grid (open+5min .. close) for a session, in UTC."""
    open_utc = calendar.session_open(session_date).tz_convert(UTC)
    close_utc = calendar.session_close(session_date).tz_convert(UTC)
    # The bar-start grid has left-inclusive ticks at open, open+5, ..., close-5.
    # Bar-end timestamps are exactly one interval later: open+5, ..., close.
    bar_start_grid = pd.date_range(start=open_utc, end=close_utc, freq="5min", inclusive="left")
    return bar_start_grid + pd.Timedelta(minutes=5)


def _classify_timestamp_semantics(
    df_ny: pd.DataFrame,
    calendar: Any,
    session_grids: dict[date, dict[str, Any]],
    tz: ZoneInfo,
    *,
    exclude_early_close: bool,
) -> str:
    """Classify whether returned regular-session timestamps are bar-start or bar-end.

    Uses the same eligible regular-session grid used for coverage.  Only full
    sessions vote; early closes and extended-hours rows do not determine the
    classification.  A 16:00 close timestamp by itself does not count as a bar-end vote.
    Returns one of: bar_start, bar_end, ambiguous, undetermined.
    """
    if df_ny.empty:
        return "undetermined"

    session_votes: list[str] = []
    for d, info in session_grids.items():
        if exclude_early_close and not info["is_full"]:
            continue
        if not calendar.is_session(d):
            continue

        open_ny = info["open_utc"].astimezone(tz)
        close_ny = info["close_utc"].astimezone(tz)
        open_t = open_ny.time()
        close_t = close_ny.time()

        # Select timestamps within the regular session (inclusive), ignoring pre/post market.
        idx = df_ny.index
        mask = (idx.time >= open_t) & (idx.time <= close_t) & (idx.date == d)
        session_ts = idx[mask]
        if len(session_ts) == 0:
            continue

        bar_start_grid = info["grid"]
        bar_end_grid = _session_bar_end_grid(calendar, d)
        start_set = set(bar_start_grid)
        end_set = set(bar_end_grid)
        on_grid_union = start_set | end_set

        on_grid_count = sum(1 for ts in session_ts if ts in on_grid_union)
        has_open = info["open_utc"] in set(session_ts)
        has_close = info["close_utc"] in set(session_ts)

        expected_bars = len(start_set)
        if expected_bars == 0:
            continue

        # Require at least 90% of the expected grid to participate in the vote.
        threshold = max(1, int(expected_bars * 0.9))
        if on_grid_count < threshold:
            session_votes.append("undetermined")
            continue

        # Bar-start sessions begin at the open and end at close-5min.
        # Bar-end sessions begin at open+5min and end at the close.
        # A lone 16:00 timestamp alongside a bar-start grid is the close extra
        # and does not flip the vote to bar-end.
        if has_open and not has_close:
            session_votes.append("bar_start")
        elif has_close and not has_open:
            session_votes.append("bar_end")
        elif has_open and has_close and len(session_ts) == expected_bars + 1:
            # All bar-start timestamps plus the close extra (16:00).
            session_votes.append("bar_start")
        else:
            session_votes.append("ambiguous")

    if not session_votes:
        return "undetermined"
    if all(v == "bar_start" for v in session_votes):
        return "bar_start"
    if all(v == "bar_end" for v in session_votes):
        return "bar_end"
    if any(v == "ambiguous" for v in session_votes):
        return "ambiguous"
    if any(v == "bar_start" for v in session_votes) and any(v == "bar_end" for v in session_votes):
        return "ambiguous"
    return "undetermined"


def _classify_date_bound(
    df_ny: pd.DataFrame,
    start_date: date,
    end_date: date,
    coverage_pct: float,
    threshold: float,
    out_of_range_count: int,
) -> str:
    if df_ny.empty:
        return "empty"
    in_range = (df_ny.index.date >= start_date) & (df_ny.index.date <= end_date)
    in_range_count = int(in_range.sum())
    total = len(df_ny)
    out_of_range = total - in_range_count

    if in_range_count == 0:
        return "clipped_to_recent_history" if out_of_range > 0 else "empty"

    meets = coverage_pct >= threshold
    if out_of_range > 0:
        return "superset_with_complete_requested_range" if meets else "clipped_but_contains_partial_requested_range"
    if meets:
        return "honored_exactly"

    # Heuristic: if data is anchored near the end of the requested window but not the start,
    # label it as recent-history clipping.
    max_date = df_ny.index.date.max()
    min_date = df_ny.index.date.min()
    if max_date and max_date >= end_date - timedelta(days=180) and min_date and min_date > start_date + timedelta(days=30):
        return "clipped_to_recent_history"
    return "clipped_but_contains_partial_requested_range"


def _candle_is_valid(candle: dict, provider: str = "schwab") -> bool:
    """Check raw candle validity without normalizing."""
    try:
        if provider == "alpaca":
            o = candle.get("o")
            h = candle.get("h")
            l = candle.get("l")
            c = candle.get("c")
            v = candle.get("v")
        else:
            o = candle.get("open")
            h = candle.get("high")
            l = candle.get("low")
            c = candle.get("close")
            v = candle.get("volume")
        for val in (o, h, l, c, v):
            if val is None:
                return False
            if isinstance(val, float) and not (__import__("math").isfinite(val)):
                return False
            try:
                float(val)
            except (TypeError, ValueError):
                return False
        o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
        if h < l or h < max(o, c) or l > min(o, c):
            return False
        return not v < 0
    except Exception:  # noqa: BLE001
        return False


def _count_duplicate_timestamps(candles: list[dict], provider: str = "schwab") -> int:
    if not candles:
        return 0
    if provider == "alpaca":
        key = "t"
    else:
        key = "datetime"
    counts = Counter(str(c.get(key)) for c in candles)
    return sum(c - 1 for c in counts.values() if c > 1)


def _parse_raw_timestamps(candles: list[dict], provider: str) -> list[pd.Timestamp]:
    """Parse raw candle timestamps to UTC Timestamps."""
    ts_list: list[pd.Timestamp] = []
    for c in candles:
        if provider == "alpaca":
            val = c.get("t")
            if val is None:
                continue
            ts = pd.to_datetime(val, utc=True)
        else:
            val = c.get("datetime")
            if val is None:
                continue
            ts = pd.to_datetime(val, unit="ms", utc=True)
        if pd.isna(ts):
            continue
        ts_list.append(ts)
    return ts_list


def _regular_session_duplicate_timestamps(
    candles: list[dict], provider: str, primary_utc_set: set[datetime]
) -> int:
    """Count duplicate raw timestamps that fall on the eligible regular-session grid."""
    ts_list = [ts for ts in _parse_raw_timestamps(candles, provider) if ts in primary_utc_set]
    counts = Counter(ts_list)
    return sum(c - 1 for c in counts.values() if c > 1)


def _regular_session_invalid_ohlc_count(df_primary: pd.DataFrame) -> int:
    """Count rows in the primary regular-session DataFrame with invalid OHLCV relationships."""
    if df_primary.empty:
        return 0
    ohlc = df_primary[["open", "high", "low", "close"]]
    invalid = (
        (ohlc["high"] < ohlc.max(axis=1))
        | (ohlc["low"] > ohlc.min(axis=1))
        | (ohlc["high"] < ohlc["low"])
        | (df_primary["volume"] < 0)
    )
    return int(invalid.sum())


def _normalize_candles(candles: list[dict], provider: str = "schwab") -> pd.DataFrame:
    """Convert provider-specific raw bars to the canonical OHLCV DataFrame."""
    if provider == "alpaca":
        from .alpaca_client import _normalize_alpaca_bars
        return _normalize_alpaca_bars(candles)
    return _normalize_schwab_candles(candles)


def _analyze_request(
    resp: Any,
    status: int,
    candles: list[dict],
    symbol: str,
    method: str,
    start_utc: datetime,
    end_utc: datetime,
    start_date: date,
    end_date: date,
    calendar: Any,
    spec: IntradayProbeSpec,
    probe_id: str,
    repetition: int,
    retry_after: float | None,
    safe_error: str,
    provider: str = "schwab",
    page_info: dict[str, Any] | None = None,
) -> ProbeRequestRecord:
    start_ny = start_utc.astimezone(ZoneInfo(spec.timezone))
    end_ny = end_utc.astimezone(ZoneInfo(spec.timezone))

    raw_count = len(candles)
    duplicate_timestamps = _count_duplicate_timestamps(candles, provider=provider)
    invalid_ohlc_rows = sum(0 if _candle_is_valid(c, provider=provider) else 1 for c in candles)

    df = _normalize_candles(candles, provider=provider)
    normalized_count = len(df)
    df_ny = df.tz_convert(spec.timezone) if not df.empty else df

    out_of_range = 0
    requested_range_df = df.loc[start_utc:end_utc] if not df.empty else df
    if not df.empty:
        out_of_range = int(((df.index < start_utc) | (df.index > end_utc)).sum())

    # Coverage using regular-session classification.
    expected_sessions, expected_bars = _expected_primary_sessions_and_bars(
        calendar, start_date, end_date, spec.exclude_early_close_sessions_from_primary_coverage
    )

    # Build the exact bar-start and bar-end grids for every session in the requested date range.
    tz = ZoneInfo(spec.timezone)
    session_grids: dict[date, dict[str, Any]] = {}
    for s in calendar.sessions_in_range(start_date, end_date):
        d = s.date()
        open_utc = calendar.session_open(d).tz_convert(UTC)
        close_utc = calendar.session_close(d).tz_convert(UTC)
        close_ny = close_utc.tz_convert(tz)
        is_full = close_ny.time() == dt_time(16, 0)
        grid = set(pd.date_range(start=open_utc, end=close_utc, freq="5min", inclusive="left"))
        bar_end_grid = set(_session_bar_end_grid(calendar, d))
        session_grids[d] = {
            "open_utc": open_utc,
            "close_utc": close_utc,
            "is_full": is_full,
            "grid": grid,
            "bar_end_grid": bar_end_grid,
        }

    primary: set[datetime] = set()
    early_close: set[datetime] = set()
    extended: set[datetime] = set()
    non_five: set[datetime] = set()
    if not df.empty:
        for ts_utc in df.index:
            ts_ny = ts_utc.astimezone(tz)
            d = ts_ny.date()
            info = session_grids.get(d)
            if info is None:
                extended.add(ts_utc)
                continue
            open_ny_time = info["open_utc"].astimezone(tz).time()
            close_ny_time = info["close_utc"].astimezone(tz).time()
            ts_time = ts_ny.time()
            # Pre/post-market rows are extended hours and must not create intra-session gap counts.
            if ts_time < open_ny_time or ts_time > close_ny_time:
                extended.add(ts_utc)
                continue
            if ts_time == close_ny_time:
                # A close timestamp is extra (e.g. 16:00 under bar-start semantics) and
                # must not be counted as a regular grid bar.
                extended.add(ts_utc)
                continue
            if ts_utc in info["grid"]:
                if info["is_full"] or not spec.exclude_early_close_sessions_from_primary_coverage:
                    primary.add(ts_utc)
                else:
                    early_close.add(ts_utc)
            elif ts_utc in info["bar_end_grid"]:
                # Bar-end grid match: not the requested bar-start coverage, but not an off-grid error.
                continue
            else:
                # Within market hours but not on either expected five-minute grid.
                non_five.add(ts_utc)

    primary_bars = len(primary)
    early_close_bars = len(early_close)
    extended_hours_bars = len(extended)
    non_five_minute_intervals = len(non_five)

    # Restrict zero-volume, duplicate and invalid-OHLC quality metrics to the eligible
    # regular-session expected-grid bars.
    df_primary = df.loc[df.index.isin(primary)] if not df.empty else df
    regular_session_zero_volume_bars = 0
    if not df_primary.empty and "volume" in df_primary.columns:
        regular_session_zero_volume_bars = int((df_primary["volume"] == 0).sum())
    regular_session_invalid_ohlc_rows = _regular_session_invalid_ohlc_count(df_primary)
    regular_session_duplicate_timestamps = _regular_session_duplicate_timestamps(candles, provider, primary)

    zero_volume_bars = 0
    if not df.empty and "volume" in df.columns:
        zero_volume_bars = int((df["volume"] == 0).sum())
    duplicate_rate = (duplicate_timestamps / raw_count * 100) if raw_count else 0.0
    zero_volume_rate = (zero_volume_bars / normalized_count * 100) if normalized_count else 0.0
    returned_regular = primary_bars
    missing_bars = max(0, expected_bars - returned_regular)
    coverage_pct = (returned_regular / expected_bars * 100) if expected_bars else 0.0

    regular_session_zero_volume_rate_pct = (
        (regular_session_zero_volume_bars / returned_regular * 100) if returned_regular else 0.0
    )
    regular_session_duplicate_bar_rate_pct = (
        (regular_session_duplicate_timestamps / returned_regular * 100) if returned_regular else 0.0
    )

    timestamp_semantics = _classify_timestamp_semantics(
        df_ny, calendar, session_grids, tz, exclude_early_close=spec.exclude_early_close_sessions_from_primary_coverage
    )
    date_bound = _classify_date_bound(
        df_ny, start_date, end_date, coverage_pct, spec.minimum_regular_session_coverage_pct, out_of_range
    )

    threshold_passed = (
        coverage_pct >= spec.minimum_regular_session_coverage_pct
        and regular_session_duplicate_bar_rate_pct <= spec.maximum_duplicate_bar_rate_pct
        and regular_session_zero_volume_rate_pct <= spec.maximum_zero_volume_bar_rate_pct
        and regular_session_invalid_ohlc_rows == 0
    )
    threshold_result = "passed" if threshold_passed else "failed"

    payload_hash = _sha256_candles(candles, resp) if resp else ""
    requested_hash = _sha256_dataframe(requested_range_df)

    unique_regular_sessions = len({ts_utc.astimezone(tz).date() for ts_utc in primary})

    page_count = page_info.get("page_count", 1) if page_info else 1
    pagination_complete = page_info.get("pagination_complete", False) if page_info else False
    repeated_page_token = page_info.get("repeated_page_token", False) if page_info else False
    pagination_cycle_detected = page_info.get("pagination_cycle_detected", False) if page_info else False
    page_bar_counts = tuple(page_info.get("page_bar_counts", []) if page_info else [])
    token_sequence_sha256 = page_info.get("token_sequence_sha256", "") if page_info else ""

    return ProbeRequestRecord(
        probe_id=probe_id,
        symbol=symbol,
        method=method,
        repetition=repetition,
        requested_eastern_start=_format_ny(start_ny) or "",
        requested_eastern_end=_format_ny(end_ny) or "",
        requested_utc_start=_format_utc(start_utc) or "",
        requested_utc_end=_format_utc(end_utc) or "",
        http_status=status,
        safe_error_classification=safe_error,
        raw_candle_count=raw_count,
        normalized_candle_count=normalized_count,
        raw_earliest_timestamp=_format_utc(df.index.min() if not df.empty else None),
        raw_latest_timestamp=_format_utc(df.index.max() if not df.empty else None),
        requested_range_earliest=_format_utc(requested_range_df.index.min() if not requested_range_df.empty else None),
        requested_range_latest=_format_utc(requested_range_df.index.max() if not requested_range_df.empty else None),
        out_of_range_candles=out_of_range,
        unique_regular_sessions=unique_regular_sessions,
        expected_eligible_sessions=expected_sessions,
        expected_regular_session_bars=expected_bars,
        returned_regular_session_bars=returned_regular,
        primary_session_bars=primary_bars,
        early_close_session_bars=early_close_bars,
        extended_hours_bars=extended_hours_bars,
        regular_session_coverage_pct=coverage_pct,
        missing_regular_session_bars=missing_bars,
        duplicate_timestamps=duplicate_timestamps,
        duplicate_bar_rate_pct=duplicate_rate,
        zero_volume_bars=zero_volume_bars,
        zero_volume_rate_pct=zero_volume_rate,
        invalid_ohlc_rows=invalid_ohlc_rows,
        non_five_minute_intervals=non_five_minute_intervals,
        candle_payload_sha256=payload_hash,
        requested_range_normalized_sha256=requested_hash,
        date_bound_classification=date_bound,
        timestamp_semantics_classification=timestamp_semantics,
        threshold_result=threshold_result,
        retry_after_seconds=retry_after,
        notes="",
        page_count=page_count,
        next_page_token_present=page_info.get("next_page_token_present", False) if page_info else False,
        pagination_complete=pagination_complete,
        repeated_page_token=repeated_page_token,
        pagination_cycle_detected=pagination_cycle_detected,
        page_bar_counts=page_bar_counts,
        token_sequence_sha256=token_sequence_sha256,
        regular_session_zero_volume_bars=regular_session_zero_volume_bars,
        regular_session_zero_volume_rate_pct=regular_session_zero_volume_rate_pct,
        regular_session_invalid_ohlc_rows=regular_session_invalid_ohlc_rows,
        regular_session_duplicate_timestamps=regular_session_duplicate_timestamps,
        regular_session_duplicate_bar_rate_pct=regular_session_duplicate_bar_rate_pct,
    )


def _execute_request(
    client: Any,
    symbol: str,
    method: str,
    start_utc: datetime,
    end_utc: datetime,
    spec: IntradayProbeSpec,
    sleeper: Callable[[float], None],
) -> tuple[Any, int, list[dict], str, float | None]:
    """Execute one request with one retry for 429/5xx. Returns (resp, status, candles, safe_error, retry_after)."""
    safe_error = "none"
    retry_after: float | None = None

    for attempt in range(spec.maximum_persistent_retry_count + 1):
        safe_error = "none"
        if attempt > 0 and retry_after is not None:
            sleeper(retry_after)

        try:
            if method == "convenience_every_five_minutes":
                resp = client.get_price_history_every_five_minutes(
                    symbol,
                    start_datetime=start_utc,
                    end_datetime=end_utc,
                    need_extended_hours_data=spec.need_extended_hours_data,
                )
            elif method == "raw_price_history_five_minutes":
                resp = client.get_price_history(
                    symbol,
                    frequency_type=client.PriceHistory.FrequencyType.MINUTE,
                    frequency=client.PriceHistory.Frequency.EVERY_FIVE_MINUTES,
                    start_datetime=start_utc,
                    end_datetime=end_utc,
                    need_extended_hours_data=spec.need_extended_hours_data,
                )
            else:
                raise ProviderResponseError(f"Unknown probe method: {method}")
        except Exception as exc:  # noqa: BLE001
            classified = _classify_exception(exc, symbol, method)
            status = getattr(exc, "status_code", None) or 0
            if isinstance(classified, ProviderTransientError) and attempt < spec.maximum_persistent_retry_count:
                retry_after = spec.request_delay_seconds
                safe_error = f"transient_{status}"
                continue
            raise classified

        status = int(getattr(resp, "status_code", 0) or 0)
        if status in (401, 403):
            raise ProviderAuthenticationError(f"Schwab authentication failed for {symbol} ({method}) (HTTP {status})")
        if status == 429 or (isinstance(status, int) and status >= 500):
            if attempt < spec.maximum_persistent_retry_count:
                headers = getattr(resp, "headers", {})
                raw_retry = headers.get("Retry-After") if headers else None
                try:
                    retry_after = min(float(raw_retry), 30.0) if raw_retry else spec.request_delay_seconds
                except (TypeError, ValueError):
                    retry_after = spec.request_delay_seconds
                safe_error = f"transient_{status}"
                continue
            safe_error = f"http_{status}"
            return resp, status, [], safe_error, retry_after
        if status == 400:
            safe_error = f"http_{status}"
            return resp, status, [], safe_error, retry_after
        if status != 200:
            safe_error = f"http_{status}"
            return resp, status, [], safe_error, retry_after

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            safe_error = "invalid_response"
            return resp, status, [], safe_error, retry_after

        candles = data.get("candles", []) if isinstance(data, dict) else []
        return resp, status, candles, safe_error, retry_after

    return None, 0, [], safe_error, retry_after


def _classify_exception(exc: Exception, symbol: str, method: str) -> Exception:
    from tradex.data.fetcher import _classify_exception as fetcher_classify

    return fetcher_classify(exc, symbol, "5m")


def _probe_kind(probe_id: str) -> str:
    if probe_id.startswith("full-"):
        return "full"
    if probe_id.startswith("overlap-"):
        return "overlap"
    return "bounded"


_METHOD_PARITY_CONFLICTS = {"same_timestamps_different_values", "different_timestamps"}


def _window_id_from_probe_id(probe_id: str, window_ids: set[str]) -> str | None:
    """Return the locked window.id for a bounded probe_id, or None if not found."""
    base = probe_id.rsplit("-rep", 1)[0]
    for wid in window_ids:
        if base.startswith(f"{wid}-"):
            return wid
    # Fallback for the canonical {window.id}-{symbol}-{method} shape.
    parts = base.rsplit("-", 2)
    if len(parts) >= 3 and parts[0] in window_ids:
        return parts[0]
    return None


def _request_plan(spec: IntradayProbeSpec) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for method in spec.methods:
        for symbol in spec.full_range_probe["symbols"]:
            for rep in range(1, spec.repeat_count + 1):
                plan.append({
                    "probe_id": f"full-{symbol}-{method}-rep{rep}",
                    "symbol": symbol,
                    "method": method,
                    "start_date": date.fromisoformat(spec.full_range_probe["start_date"]),
                    "end_date": date.fromisoformat(spec.full_range_probe["end_date"]),
                    "repetition": rep,
                    "kind": "full",
                })

    for window in spec.bounded_window_probes:
        for symbol in spec.symbols:
            for method in spec.methods:
                for rep in range(1, spec.repeat_count + 1):
                    plan.append({
                        "probe_id": f"{window.id}-{symbol}-{method}-rep{rep}",
                        "symbol": symbol,
                        "method": method,
                        "start_date": date.fromisoformat(window.start_date),
                        "end_date": date.fromisoformat(window.end_date),
                        "repetition": rep,
                        "kind": "bounded",
                    })

    for suffix, start, end in (
        ("left", spec.overlap_probe.left_start_date, spec.overlap_probe.left_end_date),
        ("right", spec.overlap_probe.right_start_date, spec.overlap_probe.right_end_date),
    ):
        for method in spec.methods:
            for rep in range(1, spec.repeat_count + 1):
                plan.append({
                    "probe_id": f"overlap-{suffix}-{spec.overlap_probe.symbol}-{method}-rep{rep}",
                    "symbol": spec.overlap_probe.symbol,
                    "method": method,
                    "start_date": date.fromisoformat(start),
                    "end_date": date.fromisoformat(end),
                    "repetition": rep,
                    "kind": "overlap",
                })

    return plan


def _execute_alpaca_request(
    client: AlpacaRestClient,
    symbol: str,
    method: str,
    start_utc: datetime,
    end_utc: datetime,
    spec: IntradayProbeSpec,
    sleeper: Callable[[float], None],
) -> tuple[int, list[dict], str, float | None, dict[str, Any]]:
    """Execute one Alpaca bars request, following all pagination pages.

    Returns (http_status, candles, safe_error, retry_after_seconds, page_info).
    """
    status, bars, page_info = client.get_bars(
        symbol,
        start_utc,
        end_utc,
        feed=method,
        timeframe=spec.bar_interval,
        adjustment=spec.adjustment or "raw",
        asof=spec.asof or "",
        sort=spec.sort or "asc",
        limit=spec.page_limit or 10000,
        sleeper=sleeper,
    )
    safe_error = page_info.get("safe_error_classification") or _safe_error_class(status)
    retry_after = page_info.get("retry_after_seconds")
    return status, bars, safe_error, retry_after, page_info


def _safe_error_class(status: int) -> str:
    if status == 429:
        return "http_429"
    if status >= 500:
        return f"http_{status}"
    if status == 400:
        return "http_400"
    if status == 401:
        return "http_401"
    if status == 403:
        return "http_403"
    if status != 200:
        return f"http_{status}"
    return "none"


def _run_single_schwab_request(
    client: Any,
    plan_item: dict[str, Any],
    spec: IntradayProbeSpec,
    calendar: Any,
    output_dir: Path,
    sleeper: Callable[[float], None],
) -> ProbeRequestRecord:
    start_utc, end_utc = _eastern_bounds(plan_item["start_date"], plan_item["end_date"], spec.timezone)

    resp, status, candles, safe_error, retry_after = _execute_request(
        client,
        plan_item["symbol"],
        plan_item["method"],
        start_utc,
        end_utc,
        spec,
        sleeper,
    )

    record = _analyze_request(
        resp,
        status,
        candles,
        plan_item["symbol"],
        plan_item["method"],
        start_utc,
        end_utc,
        plan_item["start_date"],
        plan_item["end_date"],
        calendar,
        spec,
        plan_item["probe_id"],
        plan_item["repetition"],
        retry_after,
        safe_error,
        provider="schwab",
        page_info={
            "page_count": 1,
            "next_page_token_present": False,
            "pagination_complete": True,
            "repeated_page_token": False,
            "pagination_cycle_detected": False,
            "page_bar_counts": [len(candles)],
            "token_hashes": [],
            "token_sequence_sha256": "",
        },
    )

    # Write private per-request artifacts outside the repository.
    request_dir = output_dir / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    df = _normalize_candles(candles, provider="schwab")
    requested_range_df = df.loc[start_utc:end_utc] if not df.empty else df
    if not requested_range_df.empty:
        requested_range_df.to_csv(
            request_dir / f"{plan_item['probe_id']}.csv",
            date_format="%Y-%m-%dT%H:%M:%S%z",
            float_format="%.10g",
        )
    try:
        payload = resp.content if (resp and hasattr(resp, "content")) else None
        if payload is None and resp:
            payload = json.dumps(resp.json(), sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
        if payload:
            (request_dir / f"{plan_item['probe_id']}_payload.json").write_bytes(payload)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Failed to write request payload for %s", plan_item['probe_id'])

    return record


def _run_single_alpaca_request(
    client: AlpacaRestClient,
    plan_item: dict[str, Any],
    spec: IntradayProbeSpec,
    calendar: Any,
    output_dir: Path,
    sleeper: Callable[[float], None],
) -> ProbeRequestRecord:
    start_utc, end_utc = _eastern_bounds(plan_item["start_date"], plan_item["end_date"], spec.timezone)

    status, candles, safe_error, retry_after, page_info = _execute_alpaca_request(
        client,
        plan_item["symbol"],
        plan_item["method"],
        start_utc,
        end_utc,
        spec,
        sleeper,
    )

    if status == 401:
        raise ProviderAuthenticationError(
            f"Alpaca authentication failed for {plan_item['symbol']} ({plan_item['method']})"
        )

    record = _analyze_request(
        None,
        status,
        candles,
        plan_item["symbol"],
        plan_item["method"],
        start_utc,
        end_utc,
        plan_item["start_date"],
        plan_item["end_date"],
        calendar,
        spec,
        plan_item["probe_id"],
        plan_item["repetition"],
        retry_after,
        safe_error,
        provider="alpaca",
        page_info=page_info,
    )

    # Write private per-request artifacts outside the repository.
    request_dir = output_dir / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    df = _normalize_candles(candles, provider="alpaca")
    requested_range_df = df.loc[start_utc:end_utc] if not df.empty else df
    if not requested_range_df.empty:
        requested_range_df.to_csv(
            request_dir / f"{plan_item['probe_id']}.csv",
            date_format="%Y-%m-%dT%H:%M:%S%z",
            float_format="%.10g",
        )
    try:
        payload = json.dumps(
            {"bars": candles, "page_info": page_info},
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        if payload:
            (request_dir / f"{plan_item['probe_id']}_payload.json").write_bytes(payload)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Failed to write request payload for %s", plan_item['probe_id'])

    return record


def _run_single_request(
    client: Any,
    plan_item: dict[str, Any],
    spec: IntradayProbeSpec,
    calendar: Any,
    output_dir: Path,
    sleeper: Callable[[float], None],
    settings: TradeXSettings,
) -> ProbeRequestRecord:
    if spec.provider == "alpaca":
        return _run_single_alpaca_request(client, plan_item, spec, calendar, output_dir, sleeper)
    return _run_single_schwab_request(client, plan_item, spec, calendar, output_dir, sleeper)


def _alpaca_rest_version() -> str:
    try:
        import requests as _requests
        return f"requests=={_requests.__version__}"
    except Exception:  # noqa: BLE001
        return "requests"


def run_probe(
    spec: IntradayProbeSpec,
    strategy_spec_sha256: str,
    probe_spec_sha256: str,
    output_dir: str | Path,
    pre_registration_commit: str,
    schwab_py_version: str,
    *,
    client: Any | None = None,
    settings: TradeXSettings | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> ProbeReport:
    """Execute the locked probe and return a structured report."""
    settings = settings or load_runtime_settings()
    sleeper = sleeper or time.sleep
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if spec.provider == "schwab":
        if client is None:
            client = _get_schwab_client(settings=settings)
    elif spec.provider == "alpaca":
        if client is None:
            client = make_alpaca_client(settings=settings)
    else:
        raise ValueError(f"Probe provider must be 'schwab' or 'alpaca'; got {spec.provider!r}")

    calendar = _load_calendar(spec.exchange_calendar)
    plan = _request_plan(spec)

    records: list[ProbeRequestRecord] = []
    for item in plan:
        record = _run_single_request(
            client, item, spec, calendar, output_dir, sleeper, settings
        )
        records.append(record)
        if item != plan[-1]:
            sleeper(spec.request_delay_seconds)

    # Cache of requested-range DataFrames keyed by probe_id (without repetition).
    requested_dfs: dict[str, pd.DataFrame] = {}
    for rec in records:
        base_id = rec.probe_id.rsplit("-rep", 1)[0]
        # Reuse the first repetition's requested-range CSV if it exists.
        if base_id not in requested_dfs:
            csv_path = output_dir / "requests" / f"{rec.probe_id}.csv"
            if csv_path.exists():
                df = pd.read_csv(
                    csv_path,
                    index_col="datetime",
                    parse_dates=["datetime"],
                    dtype={"open": float, "high": float, "low": float, "close": float, "volume": float},
                )
                df.index = pd.to_datetime(df.index, utc=True)
                requested_dfs[base_id] = df

    feed_comparison_rows: list[dict[str, Any]] = []
    provider_contract_rows: list[dict[str, Any]] = []
    if spec.provider == "alpaca" and isinstance(client, AlpacaRestClient):
        feed_comparison_rows = _build_alpaca_feed_comparison_rows(records, requested_dfs, spec=spec)
        _, provider_contract_rows = _evaluate_alpaca_provider_contract(client, spec, records=records, feed_comparison_rows=feed_comparison_rows)

    repeatability_rows = _build_repeatability_rows(records)
    method_parity_rows = _build_method_parity_rows(records, requested_dfs, spec=spec)
    chunk_overlap_rows = _build_chunk_overlap_rows(records, requested_dfs)
    summary_rows = _build_summary_rows(records)

    decision = _build_decision(
        spec,
        records,
        repeatability_rows,
        method_parity_rows,
        chunk_overlap_rows,
        strategy_spec_sha256,
        probe_spec_sha256,
        pre_registration_commit,
        schwab_py_version,
        feed_comparison_rows=feed_comparison_rows,
        provider_contract_rows=provider_contract_rows,
    )

    return ProbeReport(
        records=records,
        decision=decision,
        method_parity_rows=method_parity_rows,
        repeatability_rows=repeatability_rows,
        chunk_overlap_rows=chunk_overlap_rows,
        summary_rows=summary_rows,
        feed_comparison_rows=feed_comparison_rows,
        provider_contract_rows=provider_contract_rows,
    )


def _build_repeatability_rows(records: list[ProbeRequestRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped: dict[str, list[ProbeRequestRecord]] = {}
    for rec in records:
        base = rec.probe_id.rsplit("-rep", 1)[0]
        grouped.setdefault(base, []).append(rec)
    for base, reps in grouped.items():
        if len(reps) < 2:
            continue
        a, b = reps[0], reps[1]
        pagination_state_match = (
            a.pagination_complete == b.pagination_complete is True
            and a.repeated_page_token == b.repeated_page_token is False
            and a.pagination_cycle_detected == b.pagination_cycle_detected is False
            and a.page_count == b.page_count
        )
        match = (
            a.http_status == b.http_status == 200
            and a.requested_range_normalized_sha256 == b.requested_range_normalized_sha256
            and a.primary_session_bars == b.primary_session_bars
            and a.threshold_result == b.threshold_result
            and pagination_state_match
        )
        rows.append({
            "base_probe_id": base,
            "symbol": a.symbol,
            "method": a.method,
            "date_range": f"{a.requested_eastern_start} to {a.requested_eastern_end}",
            "repeat_hash_match": match,
            "rep1_http_status": a.http_status,
            "rep2_http_status": b.http_status,
            "rep1_primary_session_bars": a.primary_session_bars,
            "rep2_primary_session_bars": b.primary_session_bars,
            "rep1_hash": a.requested_range_normalized_sha256,
            "rep2_hash": b.requested_range_normalized_sha256,
            "rep1_threshold": a.threshold_result,
            "rep2_threshold": b.threshold_result,
            "rep1_page_count": a.page_count,
            "rep2_page_count": b.page_count,
            "rep1_pagination_complete": a.pagination_complete,
            "rep2_pagination_complete": b.pagination_complete,
            "rep1_repeated_page_token": a.repeated_page_token,
            "rep2_repeated_page_token": b.repeated_page_token,
            "rep1_pagination_cycle_detected": a.pagination_cycle_detected,
            "rep2_pagination_cycle_detected": b.pagination_cycle_detected,
        })
    return rows


def _build_method_parity_rows(
    records: list[ProbeRequestRecord],
    dfs: dict[str, pd.DataFrame],
    *,
    spec: IntradayProbeSpec | None = None,
) -> list[dict[str, Any]]:
    """Compare Schwab convenience vs raw methods, or Alpaca feeds if applicable."""
    rows: list[dict[str, Any]] = []
    if spec is not None and spec.provider == "alpaca":
        return rows

    grouped: dict[tuple[str, int], list[ProbeRequestRecord]] = {}
    for rec in records:
        # Base id without the trailing -rep<N> suffix, then without the method name.
        base = rec.probe_id.rsplit("-rep", 1)[0]
        window_symbol = base.rsplit("-", 1)[0]
        grouped.setdefault((window_symbol, rec.repetition), []).append(rec)

    for (window_symbol, rep), reps in grouped.items():
        by_method: dict[str, ProbeRequestRecord] = {r.method: r for r in reps}
        if len(by_method) < 2:
            continue
        convenience = by_method.get("convenience_every_five_minutes")
        raw = by_method.get("raw_price_history_five_minutes")
        if convenience is None or raw is None:
            continue
        rows.append(_compare_methods(window_symbol, convenience.symbol, rep, convenience, raw, dfs))
    return rows


def _primary_grid_for_range(
    calendar: Any, start_date: date, end_date: date, exclude_early_close: bool
) -> pd.DatetimeIndex:
    """Return the expected bar-start UTC timestamps for the requested date range."""
    timestamps: list[pd.Timestamp] = []
    for s in calendar.sessions_in_range(start_date, end_date):
        d = s.date()
        if exclude_early_close and not _is_full_session(calendar, d):
            continue
        timestamps.extend(_session_grid_times(calendar, d))
    return pd.DatetimeIndex(timestamps, tz="UTC")


def _build_alpaca_feed_comparison_rows(
    records: list[ProbeRequestRecord],
    dfs: dict[str, pd.DataFrame],
    *,
    spec: IntradayProbeSpec,
) -> list[dict[str, Any]]:
    """Compare SIP (candidate) and IEX (comparison) on paired regular-session expected-grid timestamps."""
    rows: list[dict[str, Any]] = []
    if spec.provider != "alpaca" or not spec.candidate_feed or not spec.comparison_feed:
        return rows

    calendar = _load_calendar(spec.exchange_calendar)
    grouped: dict[tuple[str, int], list[ProbeRequestRecord]] = {}
    for rec in records:
        base = rec.probe_id.rsplit("-rep", 1)[0]
        window_symbol = base.rsplit("-", 1)[0]
        grouped.setdefault((window_symbol, rec.repetition), []).append(rec)

    for (window_symbol, rep), reps in grouped.items():
        by_method = {r.method: r for r in reps}
        candidate = by_method.get(spec.candidate_feed)
        comparison = by_method.get(spec.comparison_feed)
        if candidate is None or comparison is None:
            continue
        base_cand = candidate.probe_id.rsplit("-rep", 1)[0]
        base_comp = comparison.probe_id.rsplit("-rep", 1)[0]
        df_cand_full = dfs.get(base_cand)
        df_comp_full = dfs.get(base_comp)

        start_date = date.fromisoformat(candidate.requested_eastern_start.split("T")[0])
        end_date = date.fromisoformat(candidate.requested_eastern_end.split("T")[0])
        expected_grid = _primary_grid_for_range(
            calendar, start_date, end_date, spec.exclude_early_close_sessions_from_primary_coverage
        )

        df_cand = df_cand_full.reindex(expected_grid) if df_cand_full is not None else pd.DataFrame()
        df_comp = df_comp_full.reindex(expected_grid) if df_comp_full is not None else pd.DataFrame()
        cand_in = df_cand.dropna(how="any").index
        comp_in = df_comp.dropna(how="any").index
        paired_ts = cand_in.intersection(comp_in)

        total_sip_volume = None
        total_iex_volume = None
        total_volume_ratio = None
        median_volume_ratio = None
        ohlc_diff_flag = None
        ohlc_diff_count = None

        status_ok = candidate.http_status == comparison.http_status == 200
        if not status_ok:
            classification = "one_feed_error" if (candidate.http_status == 200 or comparison.http_status == 200) else "not_comparable"
        elif (df_cand_full is None or df_cand_full.empty) and (df_comp_full is None or df_comp_full.empty):
            classification = "not_comparable"
        elif df_cand_full is None or df_cand_full.empty or df_comp_full is None or df_comp_full.empty:
            classification = "one_feed_empty"
        elif len(paired_ts) == 0:
            classification = "no_overlap"
        else:
            ohlc_cand = df_cand.loc[paired_ts, ["open", "high", "low", "close"]]
            ohlc_comp = df_comp.loc[paired_ts, ["open", "high", "low", "close"]]
            ohlc_diff_mask = ~np.isclose(ohlc_cand.values, ohlc_comp.values)
            ohlc_diff_count = int(ohlc_diff_mask.any(axis=1).sum())
            ohlc_diff_flag = ohlc_diff_count > 0

            vol_cand = df_cand.loc[paired_ts, "volume"]
            vol_comp = df_comp.loc[paired_ts, "volume"]
            total_sip_volume = round(float(vol_cand.sum()), 4)
            total_iex_volume = round(float(vol_comp.sum()), 4)
            if total_sip_volume > 0:
                total_volume_ratio = round(total_iex_volume / total_sip_volume, 6)

            valid_mask = vol_cand > 0
            if valid_mask.any():
                ratios = (vol_comp[valid_mask] / vol_cand[valid_mask]).dropna()
                if not ratios.empty:
                    median_volume_ratio = round(float(ratios.median()), 6)

            if ohlc_diff_count == 0 and total_volume_ratio == 1.0:
                classification = "identical"
            elif ohlc_diff_count == 0:
                classification = "same_timestamps_different_values"
            else:
                classification = "different_ohlc"

        paired_count = len(paired_ts)
        expected_count = len(expected_grid)
        overlap_pct = (paired_count / expected_count * 100) if expected_count else None

        rows.append({
            "window": window_symbol,
            "symbol": candidate.symbol,
            "repetition": rep,
            "candidate_probe_id": candidate.probe_id,
            "comparison_probe_id": comparison.probe_id,
            "candidate_hash": candidate.requested_range_normalized_sha256,
            "comparison_hash": comparison.requested_range_normalized_sha256,
            "candidate_bars": len(df_cand_full) if df_cand_full is not None else 0,
            "comparison_bars": len(df_comp_full) if df_comp_full is not None else 0,
            "expected_grid_timestamp_count": expected_count,
            "paired_timestamp_count": paired_count,
            "overlap_pct": overlap_pct,
            "total_sip_volume": total_sip_volume,
            "total_iex_volume": total_iex_volume,
            "total_volume_iex_sip_ratio": total_volume_ratio,
            "median_paired_volume_iex_sip_ratio": median_volume_ratio,
            "ohlc_diff_flag": ohlc_diff_flag,
            "ohlc_diff_count": ohlc_diff_count,
            "classification": classification,
        })
    return rows


def _evaluate_alpaca_provider_contract(
    client: AlpacaRestClient,
    spec: IntradayProbeSpec,
    records: list[ProbeRequestRecord] | None = None,
    feed_comparison_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    """Probe non-OHLCV contract endpoints and return booleans + matrix rows.

    Each row carries an ``evidence_type`` of ``live_evidence``,
    ``documented_capability``, or ``unproven``.
    """
    records = records or []
    feed_comparison_rows = feed_comparison_rows or []
    candidate_records = [r for r in records if r.method == spec.candidate_feed]
    comparison_records = [r for r in records if r.method == spec.comparison_feed]

    any_candidate_data = any(r.http_status == 200 and r.raw_candle_count > 0 for r in candidate_records)
    all_candidate_bar_start = all(
        r.timestamp_semantics_classification == spec.candidate_approval_timestamp_semantics
        for r in candidate_records
        if r.http_status == 200 and r.raw_candle_count > 0
    ) if candidate_records else False
    iex_data_available = any(r.http_status == 200 and r.raw_candle_count > 0 for r in comparison_records)

    # Assets API: active and inactive listings.
    try:
        active_status, active_assets = client.get_assets(status="active", asset_class="us_equity")
    except Exception:  # noqa: BLE001
        active_status, active_assets = 0, {}
    active_count = len(active_assets) if isinstance(active_assets, list) else 0

    try:
        inactive_status, inactive_assets = client.get_assets(status="inactive", asset_class="us_equity")
    except Exception:  # noqa: BLE001
        inactive_status, inactive_assets = 0, {}
    inactive_count = len(inactive_assets) if isinstance(inactive_assets, list) else 0

    # Corporate actions endpoint.
    try:
        ca_symbols = list(spec.symbols[:3])
        ca_start = spec.full_range_probe["start_date"]
        ca_end = spec.full_range_probe["end_date"]
        ca_status, ca_data = client.get_corporate_actions(
            symbols=ca_symbols, start=ca_start, end=ca_end
        )
    except Exception:  # noqa: BLE001
        ca_status, ca_data = 0, {}
    ca_reachable = ca_status == 200

    # Volume provenance from paired SIP/IEX diagnostics.
    sip_iex_compared = any(
        r.get("classification") in ("identical", "same_timestamps_different_values", "different_ohlc")
        for r in feed_comparison_rows
    )
    volume_provenance_disclosure_complete = False
    consolidated_volume_supported = False
    if sip_iex_compared and any(r.get("ohlc_diff_flag") is False for r in feed_comparison_rows):
        # SIP and IEX returned aligned timestamps; volume differs, proving venue/consolidated distinction.
        consolidated_volume_supported = True
        volume_provenance_disclosure_complete = False  # Explicit Alpaca disclosure not captured.

    booleans: dict[str, bool] = {
        "point_in_time_universe_supported": False,
        "historical_security_type_supported": False,
        "stock_etf_classification_supported": False,
        "inactive_asset_listing_supported": active_status == 200,
        "current_inactive_asset_master_supported": inactive_status == 200 and isinstance(inactive_assets, list),
        "delisted_symbol_handling_supported": False,
        "corporate_action_endpoint_supported": ca_reachable,
        "corporate_action_historical_completeness_supported": False,
        "symbol_mapping_asof_supported": bool(spec.asof),
        "consolidated_volume_supported": consolidated_volume_supported,
        "iex_historical_available": iex_data_available,
        "monthly_pit_reproducible": False,
        "ohlcv_five_minute_history_supported": any_candidate_data,
        "regular_session_history_supported": any_candidate_data and all_candidate_bar_start,
        "timestamp_semantics_supported": all_candidate_bar_start,
        "adjustment_raw_supported": False,  # Parameter sent; actual adjustment basis not verified.
        "volume_provenance_disclosure_complete": volume_provenance_disclosure_complete,
    }

    rows: list[dict[str, Any]] = [
        {
            "requirement": "ohlcv_five_minute_history",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 200 if any_candidate_data else 0,
            "supported": booleans["ohlcv_five_minute_history_supported"],
            "evidence_type": "live_evidence" if any_candidate_data else "unproven",
            "limitation": "",
            "source": "probe bars requests",
        },
        {
            "requirement": "regular_session_history",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 200 if any_candidate_data else 0,
            "supported": booleans["regular_session_history_supported"],
            "evidence_type": "live_evidence" if any_candidate_data else "unproven",
            "limitation": "Requires bar-start timestamps and complete regular-session coverage.",
            "source": "probe bars requests",
        },
        {
            "requirement": "timestamp_convention",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 200 if any_candidate_data else 0,
            "supported": booleans["timestamp_semantics_supported"],
            "evidence_type": "live_evidence" if any_candidate_data else "unproven",
            "limitation": "Classified from returned timestamps; documentation not audited.",
            "source": "probe bars requests",
        },
        {
            "requirement": "adjustment_raw",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 200 if any_candidate_data else 0,
            "supported": booleans["adjustment_raw_supported"],
            "evidence_type": "documented_capability" if any_candidate_data else "unproven",
            "limitation": "Parameter was sent; actual adjustment basis not independently verified.",
            "source": "probe request parameters",
        },
        {
            "requirement": "consolidated_volume_provenance",
            "endpoint": "GET /v2/stocks/{symbol}/bars?feed=sip|iex",
            "http_status": 200 if sip_iex_compared else 0,
            "supported": booleans["volume_provenance_disclosure_complete"],
            "evidence_type": "live_evidence" if sip_iex_compared else "unproven",
            "limitation": "Paired SIP/IEX volume differs; explicit consolidated/venue disclosure not captured.",
            "source": "probe feed comparison",
        },
        {
            "requirement": "venue_volume_iex_historical",
            "endpoint": "GET /v2/stocks/{symbol}/bars?feed=iex",
            "http_status": 200 if iex_data_available else 0,
            "supported": booleans["iex_historical_available"],
            "evidence_type": "live_evidence" if iex_data_available else "unproven",
            "limitation": "IEX is a diagnostic comparison feed only.",
            "source": "probe bars requests",
        },
        {
            "requirement": "point_in_time_universe",
            "endpoint": "GET /v2/assets",
            "http_status": active_status,
            "supported": booleans["point_in_time_universe_supported"],
            "evidence_type": "live_evidence" if active_status == 200 else "unproven",
            "limitation": "Active snapshot is not a historical point-in-time universe.",
            "source": f"active_assets_count={active_count}",
        },
        {
            "requirement": "monthly_pit_reproducibility",
            "endpoint": "GET /v2/assets",
            "http_status": active_status,
            "supported": booleans["monthly_pit_reproducible"],
            "evidence_type": "unproven",
            "limitation": "No historical PIT membership endpoint was exercised.",
            "source": "",
        },
        {
            "requirement": "current_active_asset_master",
            "endpoint": "GET /v2/assets?status=active",
            "http_status": active_status,
            "supported": booleans["inactive_asset_listing_supported"],
            "evidence_type": "live_evidence" if active_status == 200 else "unproven",
            "limitation": "Current listing only.",
            "source": f"active_assets_count={active_count}",
        },
        {
            "requirement": "current_inactive_asset_master",
            "endpoint": "GET /v2/assets?status=inactive",
            "http_status": inactive_status,
            "supported": booleans["current_inactive_asset_master_supported"],
            "evidence_type": "live_evidence" if inactive_status == 200 else "unproven",
            "limitation": "Inactive listing is current, not historical PIT.",
            "source": f"inactive_assets_count={inactive_count}",
        },
        {
            "requirement": "delisted_symbol_handling",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 0,
            "supported": booleans["delisted_symbol_handling_supported"],
            "evidence_type": "unproven",
            "limitation": "asof parameter maps symbol at asof date; does not reconstruct historical security master.",
            "source": "",
        },
        {
            "requirement": "symbol_mapping_asof",
            "endpoint": "GET /v2/stocks/{symbol}/bars",
            "http_status": 200 if any_candidate_data else 0,
            "supported": booleans["symbol_mapping_asof_supported"],
            "evidence_type": "documented_capability" if any_candidate_data else "unproven",
            "limitation": "asof is a query parameter, not a historical security master.",
            "source": f"asof={spec.asof}",
        },
        {
            "requirement": "security_type_stock_etf",
            "endpoint": "GET /v2/assets",
            "http_status": active_status,
            "supported": booleans["stock_etf_classification_supported"],
            "evidence_type": "unproven",
            "limitation": "asset_class=us_equity does not distinguish stocks from ETFs.",
            "source": "",
        },
        {
            "requirement": "security_type_warrant_right_unit_preferred",
            "endpoint": "GET /v2/assets",
            "http_status": active_status,
            "supported": False,
            "evidence_type": "unproven",
            "limitation": "asset_class=us_equity does not expose warrant/right/unit/preferred classification.",
            "source": "",
        },
        {
            "requirement": "historical_security_type",
            "endpoint": "GET /v2/assets",
            "http_status": active_status,
            "supported": booleans["historical_security_type_supported"],
            "evidence_type": "unproven",
            "limitation": "Assets API returns current classification only.",
            "source": "",
        },
        {
            "requirement": "corporate_action_endpoint_reachable",
            "endpoint": "GET /v1/corporate-actions",
            "http_status": ca_status,
            "supported": booleans["corporate_action_endpoint_supported"],
            "evidence_type": "live_evidence" if ca_reachable else "unproven",
            "limitation": "Reachability does not imply historical completeness.",
            "source": f"corporate_actions_response_type={type(ca_data).__name__}",
        },
        {
            "requirement": "corporate_action_historical_completeness",
            "endpoint": "GET /v1/corporate-actions",
            "http_status": ca_status,
            "supported": booleans["corporate_action_historical_completeness_supported"],
            "evidence_type": "unproven",
            "limitation": "Coverage and timeliness not audited in this probe.",
            "source": "",
        },
        {
            "requirement": "no_provider_mixing",
            "endpoint": "probe audit",
            "http_status": 0,
            "supported": True,
            "evidence_type": "live_evidence",
            "limitation": "Only Alpaca endpoints were called.",
            "source": "probe request log",
        },
        {
            "requirement": "manifest_feasibility",
            "endpoint": "probe audit",
            "http_status": 0,
            "supported": False,
            "evidence_type": "unproven",
            "limitation": "Single-provider contract not satisfied; data-source mixing decision required.",
            "source": "",
        },
    ]

    return booleans, rows


def _compare_methods(
    window: str,
    symbol: str,
    repetition: int,
    conv: ProbeRequestRecord,
    raw: ProbeRequestRecord,
    dfs: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    base_conv = conv.probe_id.rsplit("-rep", 1)[0]
    base_raw = raw.probe_id.rsplit("-rep", 1)[0]
    df_conv = dfs.get(base_conv)
    df_raw = dfs.get(base_raw)

    status_ok = conv.http_status == raw.http_status == 200
    if not status_ok:
        classification = "one_method_error" if (conv.http_status == 200 or raw.http_status == 200) else "not_comparable"
    elif (df_conv is None or df_conv.empty) and (df_raw is None or df_raw.empty):
        # No requested-range data from either method: nothing to compare.
        classification = "not_comparable"
    elif df_conv is None or df_conv.empty or df_raw is None or df_raw.empty:
        classification = "one_method_empty"
    elif len(df_conv) != len(df_raw) or not df_conv.index.equals(df_raw.index):
        classification = "different_timestamps"
    elif df_conv[["open", "high", "low", "close", "volume"]].equals(df_raw[["open", "high", "low", "close", "volume"]]):
        classification = "identical"
    else:
        classification = "same_timestamps_different_values"

    return {
        "window": window,
        "symbol": symbol,
        "repetition": repetition,
        "convenience_probe_id": conv.probe_id,
        "raw_probe_id": raw.probe_id,
        "convenience_hash": conv.requested_range_normalized_sha256,
        "raw_hash": raw.requested_range_normalized_sha256,
        "classification": classification,
    }


def _build_chunk_overlap_rows(records: list[ProbeRequestRecord], dfs: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Map base probe_id to record for overlap windows.
    by_base: dict[str, ProbeRequestRecord] = {}
    for rec in records:
        base = rec.probe_id.rsplit("-rep", 1)[0]
        by_base[base] = rec

    left_bases = [b for b in by_base if b.startswith("overlap-left-")]
    for left_base in left_bases:
        # overlap-left-SYMBOL-METHOD-repN -> base, right mirror.
        parts = left_base.split("-")
        if len(parts) < 4:
            continue
        symbol = parts[2]
        method = parts[3]
        right_base = left_base.replace("overlap-left-", "overlap-right-", 1)
        right_rec = by_base.get(right_base)
        left_rec = by_base[left_base]
        if right_rec is None:
            continue
        left_df = dfs.get(left_base)
        right_df = dfs.get(right_base)
        # Overlap dates are from right_start_date to left_end_date.
        overlap_start_date = date.fromisoformat(right_rec.requested_eastern_start.split("T")[0])
        overlap_end_date = date.fromisoformat(left_rec.requested_eastern_end.split("T")[0])
        overlap_start, overlap_end = _eastern_bounds(overlap_start_date, overlap_end_date, "America/New_York")
        if left_df is None or right_df is None or left_df.empty or right_df.empty:
            classification = "not_comparable"
        else:
            left_overlap = left_df.loc[overlap_start:overlap_end]
            right_overlap = right_df.loc[overlap_start:overlap_end]
            if len(left_overlap) != len(right_overlap) or not left_overlap.index.equals(right_overlap.index):
                classification = "mismatch"
            elif left_overlap[["open", "high", "low", "close", "volume"]].equals(
                right_overlap[["open", "high", "low", "close", "volume"]]
            ):
                classification = "match"
            else:
                classification = "mismatch"
        rows.append({
            "symbol": symbol,
            "method": method,
            "left_probe_id": left_rec.probe_id,
            "right_probe_id": right_rec.probe_id,
            "overlap_start": _format_utc(overlap_start),
            "overlap_end": _format_utc(overlap_end),
            "left_overlap_bars": len(left_df.loc[overlap_start:overlap_end]) if left_df is not None else 0,
            "right_overlap_bars": len(right_df.loc[overlap_start:overlap_end]) if right_df is not None else 0,
            "left_overlap_hash": _sha256_dataframe(left_df.loc[overlap_start:overlap_end]) if left_df is not None else "",
            "right_overlap_hash": _sha256_dataframe(right_df.loc[overlap_start:overlap_end]) if right_df is not None else "",
            "classification": classification,
        })
    return rows


def _build_summary_rows(records: list[ProbeRequestRecord]) -> list[dict[str, Any]]:
    by_id: dict[str, ProbeRequestRecord] = {}
    for rec in records:
        by_id[rec.probe_id] = rec
    return [r.to_dict() for r in records]


def _build_decision(
    spec: IntradayProbeSpec,
    records: list[ProbeRequestRecord],
    repeatability_rows: list[dict[str, Any]],
    parity_rows: list[dict[str, Any]],
    overlap_rows: list[dict[str, Any]],
    strategy_spec_sha256: str,
    probe_spec_sha256: str,
    pre_registration_commit: str,
    schwab_py_version: str,
    *,
    feed_comparison_rows: list[dict[str, Any]] | None = None,
    provider_contract_rows: list[dict[str, Any]] | None = None,
) -> ProbeDecision:
    """Apply the locked at-least-one-request-method decision policy."""
    feed_comparison_rows = feed_comparison_rows or []
    provider_contract_rows = provider_contract_rows or []
    is_alpaca = spec.provider == "alpaca"

    blockers: list[str] = []
    limitations: list[str] = [
        "This is an as-of observation using the locked symbol set and sample windows; provider behavior/entitlements may change.",
        "The probe does not resolve point-in-time universe, security-master, delisted-symbol, or volume-provenance requirements unless explicitly verified.",
    ]

    window_ids = {w.id for w in spec.bounded_window_probes}
    expected_full_symbols = set(spec.full_range_probe["symbols"])
    expected_bounded_keys = {(w.id, s) for w in spec.bounded_window_probes for s in spec.symbols}

    # For Alpaca we may only approve the candidate feed; Schwab still picks among all methods.
    if is_alpaca and spec.candidate_feed:
        selectable_methods = [spec.candidate_feed]
    else:
        selectable_methods = list(spec.methods)

    def _record_passes(rec: ProbeRequestRecord) -> bool:
        pagination_ok = (
            rec.pagination_complete
            and not rec.repeated_page_token
            and not rec.pagination_cycle_detected
        )
        quality_ok = (
            rec.threshold_result == "passed"
            and rec.regular_session_invalid_ohlc_rows == 0
            and rec.regular_session_zero_volume_rate_pct <= spec.maximum_zero_volume_bar_rate_pct
            and rec.regular_session_duplicate_bar_rate_pct <= spec.maximum_duplicate_bar_rate_pct
        )
        timestamp_ok = (
            not is_alpaca
            or rec.timestamp_semantics_classification == spec.candidate_approval_timestamp_semantics
        )
        return (
            rec.http_status == 200
            and rec.raw_candle_count > 0
            and quality_ok
            and pagination_ok
            and timestamp_ok
            and rec.date_bound_classification in ("honored_exactly", "superset_with_complete_requested_range")
        )

    full_passing_symbols: dict[str, set[str]] = {m: set() for m in spec.methods}
    bounded_passing_keys: dict[str, set[tuple[str, str]]] = {m: set() for m in spec.methods}
    for rec in records:
        if not _record_passes(rec):
            continue
        kind = _probe_kind(rec.probe_id)
        if kind == "full":
            full_passing_symbols[rec.method].add(rec.symbol)
        elif kind == "bounded":
            wid = _window_id_from_probe_id(rec.probe_id, window_ids)
            if wid:
                bounded_passing_keys[rec.method].add((wid, rec.symbol))

    repeatability_by_method: dict[str, list[bool]] = {m: [] for m in spec.methods}
    for r in repeatability_rows:
        m = r.get("method")
        if m in repeatability_by_method:
            repeatability_by_method[m].append(r["repeat_hash_match"])

    overlap_by_method: dict[str, list[bool]] = {m: [] for m in spec.methods}
    for r in overlap_rows:
        m = r.get("method")
        if m in overlap_by_method:
            overlap_by_method[m].append(r["classification"] == "match")

    def _repeatable(method: str) -> bool:
        rows = repeatability_by_method.get(method, [])
        return all(rows) if rows else False

    def _chunk_overlap_ok(method: str) -> bool:
        rows = overlap_by_method.get(method, [])
        return all(rows) if rows else False

    def _parity_conflict(prefix: str) -> bool:
        if is_alpaca:
            return False  # Comparison feed is diagnostic, not approval-critical.
        return any(
            (p.get("window") or "").startswith(prefix) and p.get("classification") in _METHOD_PARITY_CONFLICTS
            for p in parity_rows
        )

    direct_candidates = [
        m for m in selectable_methods
        if expected_full_symbols <= full_passing_symbols[m] and _repeatable(m)
    ]
    chunked_candidates = [
        m for m in selectable_methods
        if expected_bounded_keys <= bounded_passing_keys[m] and _repeatable(m) and _chunk_overlap_ok(m)
    ]

    selected_method = "none"
    selected_feed = ""
    windowing = "none"
    direct_full_range_supported = False
    chunked_historical_windows_supported = False

    def _preferred_method(candidates: list[str]) -> str:
        if is_alpaca and spec.candidate_feed in candidates:
            return spec.candidate_feed
        if "convenience_every_five_minutes" in candidates:
            return "convenience_every_five_minutes"
        if "raw_price_history_five_minutes" in candidates:
            return "raw_price_history_five_minutes"
        return candidates[0]

    direct_parity_conflict = bool(direct_candidates and _parity_conflict("full-"))
    chunked_parity_conflict = bool(chunked_candidates and _parity_conflict("window-"))
    if direct_candidates and not direct_parity_conflict:
        direct_full_range_supported = True
    if chunked_candidates and not chunked_parity_conflict:
        chunked_historical_windows_supported = True

    # Prefer direct full range when both access patterns pass; they are evaluated independently.
    if direct_full_range_supported:
        windowing = "direct_full_range"
        selected_method = _preferred_method(direct_candidates)
    elif chunked_historical_windows_supported:
        windowing = "bounded_monthly_chunks"
        selected_method = _preferred_method(chunked_candidates)

    if is_alpaca:
        selected_feed = selected_method if selected_method != "none" else ""

    approved = bool(direct_full_range_supported or chunked_historical_windows_supported) and selected_method != "none"
    coverage_threshold_passed = approved

    date_filtering_required = any(
        r.out_of_range_candles > 0 or r.date_bound_classification == "superset_with_complete_requested_range"
        for r in records
    )

    # Only consider overlap for selectable (candidate) methods.
    relevant_overlap = [r for r in overlap_rows if r.get("method") in selectable_methods] if is_alpaca else overlap_rows
    if relevant_overlap and not all(r["classification"] == "match" for r in relevant_overlap):
        if any(r["classification"] == "mismatch" for r in relevant_overlap):
            blockers.append("Chunk overlap mismatch prevents deterministic stitching.")
        else:
            period = "configured"
            if relevant_overlap and relevant_overlap[0].get("overlap_start"):
                period = str(relevant_overlap[0]["overlap_start"])[:7]
            blockers.append(
                f"Chunk overlap could not be verified because the {period} overlap windows contained no requested-range data; deterministic stitching could not be verified."
            )

    if not approved:
        if direct_parity_conflict or chunked_parity_conflict:
            if direct_parity_conflict:
                blockers.append(
                    "Comparable methods produced different requested-range candles for at least one full-range window, so no method could be selected."
                )
            if chunked_parity_conflict:
                blockers.append(
                    "Comparable methods produced different requested-range candles for at least one comparable bounded window, so no method could be selected."
                )
        elif not direct_candidates and not chunked_candidates:
            blockers.append(
                "Full-range and bounded-window coverage did not meet the required thresholds; the provider returned insufficient or empty five-minute history."
            )
        else:
            blockers.append(
                "Repeatability, chunk-overlap, timestamp-semantics, or pagination requirements were not met for the access methods that otherwise had sufficient coverage."
            )

    candidate_records = [r for r in records if r.method == spec.candidate_feed] if is_alpaca else records

    timestamp_semantics = _aggregate_timestamp_semantics(candidate_records)
    candidate_timestamp_semantics = timestamp_semantics
    timestamp_normalization_required = timestamp_semantics in ("bar_start", "bar_end")

    repeatability_passed = all(r["repeat_hash_match"] for r in repeatability_rows) if repeatability_rows else False
    method_parity_passed = not any(
        p.get("classification") in _METHOD_PARITY_CONFLICTS for p in parity_rows
    ) if parity_rows else True
    chunk_overlap_passed = all(r["classification"] == "match" for r in relevant_overlap) if relevant_overlap else False

    timestamp_semantics_passed = (
        all(
            r.timestamp_semantics_classification == spec.candidate_approval_timestamp_semantics
            for r in candidate_records
            if r.http_status == 200 and r.raw_candle_count > 0
        )
        if candidate_records else False
    )

    pagination_verified = (
        all(
            r.pagination_complete and not r.repeated_page_token and not r.pagination_cycle_detected and r.page_count >= 1
            for r in candidate_records
            if r.http_status == 200 and r.raw_candle_count > 0
        )
        if candidate_records else False
    )

    pagination_repeatability_passed = (
        all(r["repeat_hash_match"] for r in repeatability_rows if r.get("method") in selectable_methods)
        if repeatability_rows else False
    )

    candidate_zero_volume_threshold_passed = (
        all(
            r.regular_session_zero_volume_rate_pct <= spec.maximum_zero_volume_bar_rate_pct
            for r in candidate_records
            if r.http_status == 200 and r.raw_candle_count > 0
        )
        if candidate_records else False
    )
    candidate_invalid_ohlc_threshold_passed = (
        all(r.regular_session_invalid_ohlc_rows == 0 for r in candidate_records if r.http_status == 200 and r.raw_candle_count > 0)
        if candidate_records else False
    )
    candidate_duplicate_threshold_passed = (
        all(
            r.regular_session_duplicate_bar_rate_pct <= spec.maximum_duplicate_bar_rate_pct
            for r in candidate_records
            if r.http_status == 200 and r.raw_candle_count > 0
        )
        if candidate_records else False
    )

    volume_provenance_disclosure_complete = any(
        r.get("ohlc_diff_flag") is False and r.get("total_volume_iex_sip_ratio") is not None
        for r in feed_comparison_rows
    ) if feed_comparison_rows else False

    monthly_pit_membership_reproducible = False
    corporate_action_historical_completeness_supported = any(
        r.get("requirement") == "corporate_action_historical_completeness" and r.get("supported") is True
        for r in provider_contract_rows
    )
    current_inactive_asset_master_supported = any(
        r.get("requirement") == "current_inactive_asset_master" and r.get("supported") is True
        for r in provider_contract_rows
    )

    # Complete-provider approval for Alpaca: every matrix row must be supported.
    single_provider_contract_satisfied = False
    if is_alpaca:
        single_provider_contract_satisfied = bool(
            approved
            and timestamp_semantics_passed
            and pagination_verified
            and pagination_repeatability_passed
            and candidate_zero_volume_threshold_passed
            and candidate_invalid_ohlc_threshold_passed
            and candidate_duplicate_threshold_passed
            and provider_contract_rows
            and all(bool(r.get("supported")) for r in provider_contract_rows)
        )
    approved_as_complete = bool(approved and (not is_alpaca or single_provider_contract_satisfied))

    outcome = _outcome_from_support(
        direct_full_range_supported,
        chunked_historical_windows_supported,
        records,
        is_alpaca=is_alpaca,
        complete_contract_met=approved_as_complete,
    )

    if is_alpaca:
        if outcome == "supported_complete":
            recommended = "devin/intra-001b-intraday-snapshot"
        elif outcome == "supported_ohlcv_only":
            recommended = "gary-decision-intra-001-provider-mixing"
        else:
            recommended = "devin/intra-001b-next-provider"
    else:
        recommended = (
            "devin/intra-001b-intraday-snapshot"
            if approved
            else "devin/intra-001b-alternative-ohlcv-source"
        )

    return ProbeDecision(
        task_id=spec.task_id,
        outcome=outcome,
        provider=spec.provider,
        schwab_py_version=schwab_py_version,
        strategy_spec_sha256=strategy_spec_sha256,
        probe_spec_sha256=probe_spec_sha256,
        pre_registration_commit=pre_registration_commit,
        direct_full_range_supported=direct_full_range_supported,
        chunked_historical_windows_supported=chunked_historical_windows_supported,
        selected_request_method=selected_method,
        selected_windowing_policy=windowing,
        approved_for_intra_001_five_minute_ohlcv=approved,
        approved_as_complete_intra_001_data_source=approved_as_complete,
        date_filtering_required=date_filtering_required,
        timestamp_semantics=timestamp_semantics,
        timestamp_normalization_required=timestamp_normalization_required,
        repeatability_passed=repeatability_passed,
        method_parity_passed=method_parity_passed,
        chunk_overlap_passed=chunk_overlap_passed,
        candidate_timestamp_semantics=candidate_timestamp_semantics,
        coverage_threshold_passed=coverage_threshold_passed,
        remaining_universe_source_required=not any(
            r.get("requirement") == "point_in_time_universe" and r.get("supported") for r in provider_contract_rows
        ) if is_alpaca else True,
        remaining_security_master_required=not any(
            r.get("requirement") == "historical_security_type" and r.get("supported") for r in provider_contract_rows
        ) if is_alpaca else True,
        remaining_delisted_symbol_support_required=not any(
            r.get("requirement") == "delisted_symbol_handling" and r.get("supported") for r in provider_contract_rows
        ) if is_alpaca else True,
        remaining_volume_provenance_disclosure_required=not volume_provenance_disclosure_complete if is_alpaca else True,
        blockers=blockers,
        limitations=limitations,
        recommended_next_assignment=recommended,
        production_behavior_changed=False,
        alpaca_client_or_rest_version=_alpaca_rest_version() if is_alpaca else "",
        candidate_feed=spec.candidate_feed or "",
        comparison_feed=spec.comparison_feed or "",
        selected_feed=selected_feed,
        pagination_verified=pagination_verified,
        consolidated_volume_supported=any(
            r.get("requirement") == "consolidated_volume_provenance" and r.get("supported") for r in provider_contract_rows
        ),
        iex_historical_available=any(
            r.get("requirement") == "venue_volume_iex_historical" and r.get("supported") for r in provider_contract_rows
        ),
        point_in_time_universe_supported=any(
            r.get("requirement") == "point_in_time_universe" and r.get("supported") for r in provider_contract_rows
        ),
        historical_security_type_supported=any(
            r.get("requirement") == "historical_security_type" and r.get("supported") for r in provider_contract_rows
        ),
        stock_etf_classification_supported=any(
            r.get("requirement") == "security_type_stock_etf" and r.get("supported") for r in provider_contract_rows
        ),
        inactive_asset_listing_supported=any(
            r.get("requirement") == "current_active_asset_master" and r.get("supported") for r in provider_contract_rows
        ),
        delisted_symbol_handling_supported=any(
            r.get("requirement") == "delisted_symbol_handling" and r.get("supported") for r in provider_contract_rows
        ),
        corporate_action_endpoint_supported=any(
            r.get("requirement") == "corporate_action_endpoint_reachable" and r.get("supported") for r in provider_contract_rows
        ),
        symbol_mapping_asof_supported=any(
            r.get("requirement") == "symbol_mapping_asof" and r.get("supported") for r in provider_contract_rows
        ),
        no_provider_mixing_contract_satisfied=True,
        probe_did_not_mix_providers=True,
        single_provider_contract_satisfied=single_provider_contract_satisfied,
        methodology_decision_required=is_alpaca and outcome == "supported_ohlcv_only",
        methodology_decision_reason=(
            "OHLCV data are available but complete single-provider contract cannot be satisfied; provider-mixing decision required."
            if is_alpaca and outcome == "supported_ohlcv_only"
            else ""
        ),
        timestamp_semantics_passed=timestamp_semantics_passed,
        pagination_repeatability_passed=pagination_repeatability_passed,
        candidate_zero_volume_threshold_passed=candidate_zero_volume_threshold_passed,
        candidate_invalid_ohlc_threshold_passed=candidate_invalid_ohlc_threshold_passed,
        candidate_duplicate_threshold_passed=candidate_duplicate_threshold_passed,
        volume_provenance_disclosure_complete=volume_provenance_disclosure_complete,
        monthly_pit_membership_reproducible=monthly_pit_membership_reproducible,
        corporate_action_historical_completeness_supported=corporate_action_historical_completeness_supported,
        current_inactive_asset_master_supported=current_inactive_asset_master_supported,
    )


def _aggregate_timestamp_semantics(records: list[ProbeRequestRecord]) -> str:
    values = [r.timestamp_semantics_classification for r in records if r.http_status == 200 and r.raw_candle_count > 0]
    if not values:
        return "undetermined"
    if all(v == "bar_start" for v in values):
        return "bar_start"
    if all(v == "bar_end" for v in values):
        return "bar_end"
    if any(v == "ambiguous" for v in values):
        return "ambiguous"
    if any(v == "bar_start" for v in values) and any(v == "bar_end" for v in values):
        return "ambiguous"
    return "undetermined"


def _outcome_from_support(
    direct: bool,
    chunked: bool,
    records: list[ProbeRequestRecord],
    *,
    is_alpaca: bool = False,
    complete_contract_met: bool = False,
) -> str:
    if not is_alpaca:
        if direct:
            return "supported_direct"
        if chunked:
            return "supported_chunked"
        if any(r.http_status in (401, 403) for r in records):
            return "inconclusive"
        if all(r.http_status != 200 for r in records):
            return "inconclusive"
        return "not_supported"

    # Alpaca assignment expects one of supported_complete / supported_ohlcv_only /
    # not_supported / inconclusive / invalid.
    if any(r.http_status == 401 for r in records):
        return "inconclusive"
    if all(r.http_status not in (200, 201) for r in records) and any(r.http_status == 403 for r in records):
        return "inconclusive"
    if direct or chunked:
        if complete_contract_met:
            return "supported_complete"
        return "supported_ohlcv_only"
    if all(r.http_status != 200 for r in records):
        return "inconclusive"
    return "not_supported"
