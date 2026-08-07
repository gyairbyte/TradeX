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

import pandas as pd

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.data.fetcher import (
    ProviderAuthenticationError,
    ProviderResponseError,
    ProviderTransientError,
    _get_schwab_client,
    _normalize_schwab_candles,
)

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


def _expected_primary_sessions_and_bars(
    calendar: Any,
    start_date: date,
    end_date: date,
    exclude_early_close: bool,
) -> tuple[int, int]:
    if end_date < start_date:
        return 0, 0
    sessions = list(calendar.sessions_in_range(start_date, end_date))
    if exclude_early_close:
        sessions = [s for s in sessions if _is_full_session(calendar, s.date())]
    # Full sessions contribute 78 bars; early-close sessions contribute half.
    bar_count = 0
    for s in sessions:
        d = s.date()
        if _is_full_session(calendar, d):
            bar_count += 78
        elif _is_early_close(calendar, d):
            bar_count += 39
    return len(sessions), bar_count


def _classify_timestamp_semantics(
    df_ny: pd.DataFrame,
    calendar: Any,
    exclude_early_close: bool,
) -> str:
    """Classify whether returned regular-session timestamps are bar-start or bar-end."""
    if df_ny.empty:
        return "undetermined"

    # Use all regular-session bars (including early close if not excluded).
    session_labels = []
    for ts in df_ny.index:
        d = ts.date()
        if not calendar.is_session(d):
            continue
        open_t = calendar.session_open(d).tz_convert("America/New_York").time()
        close_t = calendar.session_close(d).tz_convert("America/New_York").time()
        t = ts.time()
        if open_t <= t <= close_t:
            session_labels.append((d, t, open_t, close_t))

    if not session_labels:
        return "undetermined"

    # Group by session and check first/last timestamps for full sessions.
    bar_start_votes = 0
    bar_end_votes = 0
    by_session: dict[date, list] = {}
    for d, t, open_t, close_t in session_labels:
        by_session.setdefault(d, []).append((t, open_t, close_t))

    for d, times in by_session.items():
        if _is_early_close(calendar, d):
            continue
        times.sort()
        first_t = times[0][0]
        last_t = times[-1][0]
        # Allow first bar at 9:30 (bar-start) or 9:35 (bar-end).
        if first_t == dt_time(9, 30):
            bar_start_votes += 1
        elif first_t == dt_time(9, 35):
            bar_end_votes += 1
        if last_t == dt_time(15, 55):
            bar_start_votes += 1
        elif last_t == dt_time(16, 0):
            bar_end_votes += 1

    if bar_start_votes > 0 and bar_end_votes == 0:
        return "bar_start"
    if bar_end_votes > 0 and bar_start_votes == 0:
        return "bar_end"
    if bar_start_votes > 0 and bar_end_votes > 0:
        return "inconsistent"
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


def _candle_is_valid(candle: dict) -> bool:
    """Check raw candle validity without normalizing."""
    try:
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


def _count_duplicate_timestamps(candles: list[dict]) -> int:
    if not candles:
        return 0
    counts = Counter(str(c.get("datetime")) for c in candles)
    return sum(c - 1 for c in counts.values() if c > 1)


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
) -> ProbeRequestRecord:
    start_ny = start_utc.astimezone(ZoneInfo(spec.timezone))
    end_ny = end_utc.astimezone(ZoneInfo(spec.timezone))

    raw_count = len(candles)
    duplicate_timestamps = _count_duplicate_timestamps(candles)
    invalid_ohlc_rows = sum(0 if _candle_is_valid(c) else 1 for c in candles)

    df = _normalize_schwab_candles(candles)
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

    primary_bars = 0
    early_close_bars = 0
    extended_hours_bars = 0
    non_five_minute_intervals = 0
    if not df_ny.empty:
        for ts in df_ny.index:
            d = ts.date()
            if not calendar.is_session(d):
                extended_hours_bars += 1
                continue
            open_t = calendar.session_open(d).tz_convert(spec.timezone)
            close_t = calendar.session_close(d).tz_convert(spec.timezone)
            if ts < open_t or ts > close_t:
                extended_hours_bars += 1
            elif _is_early_close(calendar, d):
                early_close_bars += 1
            else:
                primary_bars += 1

        # Intra-session non-five-minute interval detection.
        by_session: dict[date, list[datetime]] = {}
        for ts in df_ny.index:
            d = ts.date()
            if not calendar.is_session(d):
                continue
            by_session.setdefault(d, []).append(ts)
        for d, times in by_session.items():
            times.sort()
            for i in range(1, len(times)):
                delta = (times[i] - times[i - 1]).total_seconds()
                if abs(delta - 300) > 1:
                    non_five_minute_intervals += 1

    zero_volume_bars = 0
    if not df.empty and "volume" in df.columns:
        zero_volume_bars = int((df["volume"] == 0).sum())
    duplicate_rate = (duplicate_timestamps / raw_count * 100) if raw_count else 0.0
    zero_volume_rate = (zero_volume_bars / normalized_count * 100) if normalized_count else 0.0
    missing_bars = max(0, expected_bars - primary_bars)
    coverage_pct = (primary_bars / expected_bars * 100) if expected_bars else 0.0

    timestamp_semantics = _classify_timestamp_semantics(df_ny, calendar, spec.exclude_early_close_sessions_from_primary_coverage)
    date_bound = _classify_date_bound(
        df_ny, start_date, end_date, coverage_pct, spec.minimum_regular_session_coverage_pct, out_of_range
    )

    threshold_passed = (
        coverage_pct >= spec.minimum_regular_session_coverage_pct
        and duplicate_rate <= spec.maximum_duplicate_bar_rate_pct
        and zero_volume_rate <= spec.maximum_zero_volume_bar_rate_pct
        and invalid_ohlc_rows == 0
        and non_five_minute_intervals == 0
    )
    threshold_result = "passed" if threshold_passed else "failed"

    payload_hash = _sha256_candles(candles, resp) if resp else ""
    requested_hash = _sha256_dataframe(requested_range_df)

    unique_regular_sessions = 0
    if not df_ny.empty:
        session_dates = {ts.date() for ts in df_ny.index if calendar.is_session(ts.date())}
        unique_regular_sessions = len(session_dates)

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
        returned_regular_session_bars=primary_bars + early_close_bars,
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


def _run_single_request(
    client: Any,
    plan_item: dict[str, Any],
    spec: IntradayProbeSpec,
    calendar: Any,
    output_dir: Path,
    sleeper: Callable[[float], None],
    settings: TradeXSettings,
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
    )

    # Write private per-request artifacts outside the repository.
    request_dir = output_dir / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    df = _normalize_schwab_candles(candles)
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

    if spec.provider != "schwab":
        raise ValueError(f"Probe provider must be 'schwab'; got {spec.provider!r}")

    if client is None:
        client = _get_schwab_client(settings=settings)

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

    repeatability_rows = _build_repeatability_rows(records)
    method_parity_rows = _build_method_parity_rows(records, requested_dfs)
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
    )

    return ProbeReport(
        records=records,
        decision=decision,
        method_parity_rows=method_parity_rows,
        repeatability_rows=repeatability_rows,
        chunk_overlap_rows=chunk_overlap_rows,
        summary_rows=summary_rows,
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
        match = (
            a.http_status == b.http_status == 200
            and a.requested_range_normalized_sha256 == b.requested_range_normalized_sha256
            and a.raw_candle_count == b.raw_candle_count
            and a.threshold_result == b.threshold_result
        )
        rows.append({
            "base_probe_id": base,
            "symbol": a.symbol,
            "method": a.method,
            "date_range": f"{a.requested_eastern_start} to {a.requested_eastern_end}",
            "repeat_hash_match": match,
            "rep1_http_status": a.http_status,
            "rep2_http_status": b.http_status,
            "rep1_candle_count": a.raw_candle_count,
            "rep2_candle_count": b.raw_candle_count,
            "rep1_hash": a.requested_range_normalized_sha256,
            "rep2_hash": b.requested_range_normalized_sha256,
            "rep1_threshold": a.threshold_result,
            "rep2_threshold": b.threshold_result,
        })
    return rows


def _build_method_parity_rows(records: list[ProbeRequestRecord], dfs: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
) -> ProbeDecision:
    """Apply the locked decision policy."""
    blockers: list[str] = []
    limitations: list[str] = []

    full_methods_ok: set[str] = set()
    for rec in records:
        if _probe_kind(rec.probe_id) != "full":
            continue
        if rec.threshold_result == "passed" and rec.date_bound_classification in ("honored_exactly", "superset_with_complete_requested_range"):
            full_methods_ok.add(rec.method)

    bounded_ok_by_window: dict[str, set[str]] = {}
    for rec in records:
        if _probe_kind(rec.probe_id) != "bounded":
            continue
        # The window key is the probe_id with the trailing "-<method>-rep<N>" removed.
        base = rec.probe_id.rsplit("-rep", 1)[0]
        window = base.rsplit("-", 1)[0]
        if rec.threshold_result == "passed":
            bounded_ok_by_window.setdefault(window, set()).add(rec.method)

    repeatability_passed = all(r["repeat_hash_match"] for r in repeatability_rows) if repeatability_rows else False
    method_parity_passed = all(r["classification"] == "identical" for r in parity_rows) if parity_rows else False
    chunk_overlap_passed = all(r["classification"] == "match" for r in overlap_rows) if overlap_rows else False

    direct_full_range_supported = bool(full_methods_ok) and repeatability_passed and method_parity_passed
    chunked_historical_windows_supported = (
        all(bool(s) for s in bounded_ok_by_window.values())
        and repeatability_passed
        and chunk_overlap_passed
        and method_parity_passed
    )

    selected_method = "none"
    if method_parity_passed:
        if "convenience_every_five_minutes" in full_methods_ok or "convenience_every_five_minutes" in {m for s in bounded_ok_by_window.values() for m in s}:
            selected_method = "convenience_every_five_minutes"
        elif "raw_price_history_five_minutes" in full_methods_ok or "raw_price_history_five_minutes" in {m for s in bounded_ok_by_window.values() for m in s}:
            selected_method = "raw_price_history_five_minutes"
    else:
        if full_methods_ok:
            selected_method = "raw_price_history_five_minutes" if len(full_methods_ok) == 1 and "raw_price_history_five_minutes" in full_methods_ok else "none"

    if direct_full_range_supported:
        windowing = "direct_full_range"
    elif chunked_historical_windows_supported:
        windowing = "bounded_monthly_chunks"
    else:
        windowing = "none"

    approved = bool(direct_full_range_supported or chunked_historical_windows_supported) and selected_method != "none"

    if not approved:
        blockers.append("Schwab did not satisfy the locked coverage, repeatability, method parity, or chunk-overlap requirements.")
    if not method_parity_passed and parity_rows:
        blockers.append("Convenience and raw methods produced different requested-range candles for at least one window.")
    if not chunk_overlap_passed and overlap_rows:
        blockers.append("Chunk overlap mismatch prevents deterministic stitching.")

    timestamp_semantics = _aggregate_timestamp_semantics(records)
    timestamp_normalization_required = timestamp_semantics in ("bar_start", "bar_end")

    outcome = _outcome_from_support(direct_full_range_supported, chunked_historical_windows_supported, records)
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
        approved_as_complete_intra_001_data_source=False,
        date_filtering_required=True,
        timestamp_semantics=timestamp_semantics,
        timestamp_normalization_required=timestamp_normalization_required,
        repeatability_passed=repeatability_passed,
        method_parity_passed=method_parity_passed,
        chunk_overlap_passed=chunk_overlap_passed,
        coverage_threshold_passed=bool(full_methods_ok) or bool(bounded_ok_by_window),
        remaining_universe_source_required=True,
        remaining_security_master_required=True,
        remaining_delisted_symbol_support_required=True,
        remaining_volume_provenance_disclosure_required=True,
        blockers=blockers,
        limitations=limitations,
        recommended_next_assignment=recommended,
        production_behavior_changed=False,
    )


def _aggregate_timestamp_semantics(records: list[ProbeRequestRecord]) -> str:
    values = [r.timestamp_semantics_classification for r in records if r.http_status == 200]
    if not values:
        return "undetermined"
    if all(v == "bar_start" for v in values):
        return "bar_start"
    if all(v == "bar_end" for v in values):
        return "bar_end"
    if any(v == "inconsistent" for v in values):
        return "inconsistent"
    return "undetermined"


def _outcome_from_support(direct: bool, chunked: bool, records: list[ProbeRequestRecord]) -> str:
    if direct:
        return "supported_direct"
    if chunked:
        return "supported_chunked"
    if any(r.http_status in (401, 403) for r in records):
        return "inconclusive"
    if all(r.http_status != 200 for r in records):
        return "inconclusive"
    return "not_supported"
