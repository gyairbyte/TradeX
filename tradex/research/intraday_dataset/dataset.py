"""INTRA-001B-DATASET-V1 pipeline orchestration."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .alpaca_client import DatasetAlpacaClient
from .massive_client import MassiveDatasetClient
from .models import (
    DataQuality,
    DatasetDecision,
    DatasetState,
    OhlcvFile,
    PITObservation,
    ReferenceSnapshot,
    UniverseMember,
    now_utc_iso,
)
from .spec import DatasetPlan, _repo_relative

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def _month_from_pit(pit_date: str) -> str:
    d = pd.Timestamp(pit_date) + pd.DateOffset(days=1)
    return d.strftime("%Y-%m")


def _effective_month_start(month: str) -> pd.Timestamp:
    return pd.Timestamp(f"{month}-01")


def _month_end(month: str) -> pd.Timestamp:
    return (_effective_month_start(month) + pd.DateOffset(months=1)) - pd.Timedelta(days=1)


def _load_xnys() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


def _regular_session_grid() -> pd.DatetimeIndex:
    return pd.date_range("09:30", "15:55", freq="5min", tz="America/New_York")


def _is_regular_session(calendar: xcals.ExchangeCalendar, session_date: pd.Timestamp) -> bool:
    if session_date not in calendar.schedule.index:
        return False
    close = calendar.schedule.loc[session_date, "close"].tz_convert("America/New_York")
    return _is_regular_close(close)


def _prior_n_sessions(calendar: xcals.ExchangeCalendar, before: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    """Return the ``n`` complete regular sessions strictly before ``before`` (UTC or naive)."""
    schedule = calendar.schedule
    before_n = before.tz_convert("America/New_York").tz_localize(None).normalize() if before.tz else before.normalize()
    valid = schedule[schedule.index < before_n]
    regular = [ts for ts in valid.index if _is_regular_session(calendar, ts)]
    selected = regular[-n:] if len(regular) >= n else regular
    return [pd.Timestamp(ts, tz="America/New_York") for ts in selected]


def _sessions_in_range(calendar: xcals.ExchangeCalendar, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """Return complete regular sessions whose open/close lie within [start, end] (UTC).

    Uses the actual session open/close times instead of naive date comparisons,
    preventing the off-by-one inclusion of the next calendar day's session.
    """
    start_utc = pd.Timestamp(start).tz_convert("UTC")
    end_utc = pd.Timestamp(end).tz_convert("UTC")
    schedule = calendar.schedule
    opens = schedule["open"].dt.tz_convert("UTC")
    closes = schedule["close"].dt.tz_convert("UTC")
    mask = (closes <= end_utc) & (opens >= start_utc)
    selected = []
    for ts, close in zip(schedule[mask].index, closes[mask]):
        if _is_regular_close(close.tz_convert("America/New_York")):
            selected.append(ts)
    return [pd.Timestamp(ts, tz="America/New_York") for ts in selected]


def _is_regular_close(session_close: pd.Timestamp) -> bool:
    return session_close.hour == 16 and session_close.minute == 0


def _check_plan_hashes(plan: DatasetPlan) -> None:
    pass  # Already verified in spec.py


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    reader = csv.DictReader(text.splitlines())
    return [row for row in reader if row]


def _checkpoint_path(output_dir: Path) -> Path:
    return output_dir / "dataset_state.json"


def load_state(output_dir: Path) -> DatasetState:
    cp = _checkpoint_path(output_dir)
    if cp.exists():
        data = json.loads(cp.read_text(encoding="utf-8"))
        return DatasetState.from_dict(data)
    return DatasetState()


def save_state(output_dir: Path, state: DatasetState) -> None:
    _write_json(_checkpoint_path(output_dir), state.to_dict())


def estimate_resources(plan: DatasetPlan) -> dict[str, Any]:
    return plan.estimated_resources


def run_plan(plan: DatasetPlan, output_dir: Path, *, pre_registration_commit: str = "") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_lock = output_dir / "dataset_plan.lock.json"
    _write_json(plan_lock, plan.to_dict())
    state = load_state(output_dir)
    state.phase = "plan"
    save_state(output_dir, state)
    logger.info("Plan validated and locked at %s", plan_lock)
    logger.info("Estimated resources: %s", plan.estimated_resources)


def run_fetch_reference(
    plan: DatasetPlan,
    output_dir: Path,
    api_key: str,
    base_url: str | None = None,
) -> None:
    out = output_dir / "reference_snapshots"
    out.mkdir(parents=True, exist_ok=True)
    state = load_state(output_dir)
    state.phase = "fetch_reference"
    client = MassiveDatasetClient(api_key, base_url=base_url)

    tax_out = out / "taxonomy.json"
    if not tax_out.exists():
        mapping, rows = client.fetch_taxonomy()
        _write_json(tax_out, {"mapping": mapping, "rows": rows, "fetched_at": now_utc_iso()})
    else:
        tax_data = json.loads(tax_out.read_text(encoding="utf-8"))
        mapping = tax_data["mapping"]

    completed = set(state.pit_dates_completed)
    for pit_date in plan.monthly_pit_dates:
        if pit_date in completed:
            continue
        logger.info("Fetching reference snapshots for PIT date %s", pit_date)
        for active in (True, False):
            snap = client.fetch_reference_snapshot(
                pit_date,
                active,
                safety_max_pages=int(plan.retry_limits.get("massive_max_pages_per_snapshot", 50)),
            )
            label = "active" if active else "inactive"
            snap_path = out / f"{pit_date}_{label}.json"
            _write_json(
                snap_path,
                {
                    "pit_date": pit_date,
                    "state": label,
                    "canonical_sha256": snap.canonical_sha256,
                    "raw_sha256": snap.raw_sha256,
                    "row_count": len(snap.rows),
                    "duplicate_details": snap.duplicate_details,
                    "observations": [o.to_dict() for o in snap.observations],
                    "pages": [p.to_dict() for p in snap.pages],
                    "rows": snap.rows,
                    "fetched_at": now_utc_iso(),
                },
            )
            state.massive_request_count += len(snap.pages)
            if snap.observations[0].error:
                state.errors.append(f"{pit_date}/{label}: {snap.observations[0].error}")
                state.incomplete_requests += 1
            if snap.observations[0].pagination_complete and not snap.observations[0].error:
                pass
            else:
                state.incomplete_requests += 1
        completed.add(pit_date)
        state.pit_dates_completed = sorted(completed)
        save_state(output_dir, state)
    state.phase = "fetch_reference_done"
    save_state(output_dir, state)


def _load_taxonomy(output_dir: Path) -> dict[str, str]:
    tax_path = output_dir / "reference_snapshots" / "taxonomy.json"
    if not tax_path.exists():
        raise FileNotFoundError("Taxonomy not fetched; run fetch-reference first")
    data = json.loads(tax_path.read_text(encoding="utf-8"))
    return data["mapping"]


def _load_snapshot(output_dir: Path, pit_date: str, state: str) -> ReferenceSnapshot:
    path = output_dir / "reference_snapshots" / f"{pit_date}_{state}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    obs = data["observations"][0]
    return ReferenceSnapshot(
        pit_date=data["pit_date"],
        state=data["state"],
        rows=data["rows"],
        observations=[PITObservation(**obs)],
        pages=[],
        raw_sha256=data["raw_sha256"],
        canonical_sha256=data["canonical_sha256"],
        duplicate_details=data.get("duplicate_details", []),
    )


def _category_for_row(row: dict[str, Any], mapping: dict[str, str]) -> str:
    ttype = str(row.get("type") or "").strip().upper()
    return mapping.get(ttype, "unknown")


def _is_eligible(
    row: dict[str, Any],
    mapping: dict[str, str],
    controls: dict[str, Any],
    exclusion_records: list[dict[str, Any]],
    pit_date: str,
    effective_month: str,
    duplicate_tickers: set[str],
) -> tuple[bool, str]:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        return False, "blank_ticker"
    if ticker in duplicate_tickers:
        return False, "duplicate_symbol"
    category = _category_for_row(row, mapping)
    allowlist = {str(x).lower() for x in controls.get("stock_security_type_allowlist", [])}
    exclusions = {str(x).lower() for x in controls.get("security_type_exclusions", ["OTC", "warrant", "right", "unit", "preferred_stock", "unmapped", "unknown", "other"])}
    if category in exclusions or category not in allowlist:
        return False, f"security_type:{category}"
    exchange = str(row.get("primary_exchange") or "").strip().upper()
    allow_exchanges = {str(x).upper() for x in controls.get("exchange_allowlist", [])}
    if not exchange:
        return False, "missing_exchange"
    if exchange not in allow_exchanges:
        return False, f"exchange_not_allowed:{exchange}"
    return True, ""


def _duplicate_tickers_in_rows(rows: list[dict[str, Any]]) -> set[str]:
    ticker_counts: Counter[str] = Counter()
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker:
            ticker_counts[ticker] += 1
    return {t for t, c in ticker_counts.items() if c > 1}


def _build_active_eligible(
    snapshot: ReferenceSnapshot,
    mapping: dict[str, str],
    controls: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    """Return (eligible_rows, exclusion_records, duplicate_tickers) for an active snapshot."""
    duplicate_tickers = _duplicate_tickers_in_rows(snapshot.rows)

    eligible = []
    exclusions = []
    for row in snapshot.rows:
        ok, reason = _is_eligible(row, mapping, controls, [], snapshot.pit_date, "", duplicate_tickers)
        ticker = str(row.get("ticker") or "").strip().upper()
        if ok:
            eligible.append(row)
        else:
            exclusions.append({
                "pit_date": snapshot.pit_date,
                "effective_month": "",
                "ticker": ticker,
                "reason": reason,
                "provider_type": str(row.get("type") or ""),
                "provider_exchange": str(row.get("primary_exchange") or ""),
            })
    return eligible, exclusions, duplicate_tickers


def _ranking_timeframe_parity(
    client: DatasetAlpacaClient,
    calendar: xcals.ExchangeCalendar,
    sample_symbols: list[str],
    start: str,
    end: str,
    tolerance_pct: float,
    timeframe: str = "30Min",
    reference_timeframe: str = "5Min",
) -> tuple[bool, str]:
    """Compare ``timeframe`` regular-session close/volume to ``reference_timeframe`` aggregated to daily."""
    start_ts = pd.Timestamp(start, tz="America/New_York")
    end_ts = pd.Timestamp(end, tz="America/New_York")
    start_utc = start_ts.tz_convert("UTC")
    end_utc = end_ts.tz_convert("UTC")

    dfs_tf, meta_tf = client.get_bars(
        sample_symbols,
        start_utc,
        end_utc,
        feed="sip",
        timeframe=timeframe,
        adjustment="raw",
        sort="asc",
    )
    dfs_ref, meta_ref = client.get_bars(
        sample_symbols,
        start_utc,
        end_utc,
        feed="sip",
        timeframe=reference_timeframe,
        adjustment="raw",
        sort="asc",
    )
    if not meta_tf["pagination_complete"] or not meta_ref["pagination_complete"]:
        return False, "parity probe pagination incomplete"

    daily_tf = _aggregate_to_daily(dfs_tf, calendar)
    daily_ref = _aggregate_to_daily(dfs_ref, calendar)
    mismatches = []
    for sym in sample_symbols:
        dtf = daily_tf.get(sym.upper())
        dref = daily_ref.get(sym.upper())
        if dtf is None or dtf.empty or dref is None or dref.empty:
            mismatches.append(f"{sym}: missing aggregated daily data")
            continue
        dtf = dtf.tz_convert("America/New_York")
        dref = dref.tz_convert("America/New_York")
        for ts in dref.index:
            session_date = ts.date()
            if not calendar.is_session(session_date):
                continue
            if ts not in dtf.index:
                mismatches.append(f"{sym} {session_date}: missing {timeframe} daily bar")
                continue
            close_tf = float(dtf.loc[ts, "close"])
            close_ref = float(dref.loc[ts, "close"])
            vol_tf = float(dtf.loc[ts, "volume"])
            vol_ref = float(dref.loc[ts, "volume"])
            close_diff = abs(close_tf - close_ref) / max(close_ref, 1e-9) * 100
            vol_diff = abs(vol_tf - vol_ref) / max(vol_ref, 1e-9) * 100
            if close_diff > tolerance_pct or vol_diff > tolerance_pct:
                mismatches.append(
                    f"{sym} {session_date}: close_diff={close_diff:.4f}% vol_diff={vol_diff:.4f}%"
                )
    if mismatches:
        return False, "; ".join(mismatches[:5])
    return True, ""


def _daily_bars_for_ranking(
    client: DatasetAlpacaClient,
    symbols: list[str],
    prior_sessions: list[pd.Timestamp],
    asof: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if not prior_sessions:
        return {}, {"pagination_complete": True, "logical_calls": 0, "http_pages": 0, "http_attempts": 0, "http_429s": 0, "http_errors": 0, "response_symbols": []}
    start_utc = prior_sessions[0].tz_convert("UTC")
    end_utc = (prior_sessions[-1] + pd.Timedelta(hours=24)).tz_convert("UTC")
    return client.get_bars(
        symbols,
        start_utc,
        end_utc,
        feed="sip",
        timeframe="1Day",
        adjustment="raw",
        sort="asc",
        asof=asof,
    )


def _intraday_bars(
    client: DatasetAlpacaClient,
    symbols: list[str],
    start_utc: datetime,
    end_utc: datetime,
    asof: str,
    timeframe: str = "5Min",
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Fetch Alpaca SIP intraday bars for the given timeframe."""
    return client.get_bars(
        symbols,
        start_utc,
        end_utc,
        feed="sip",
        timeframe=timeframe,
        adjustment="raw",
        sort="asc",
        asof=asof,
    )


def _five_min_bars(
    client: DatasetAlpacaClient,
    symbols: list[str],
    start_utc: datetime,
    end_utc: datetime,
    asof: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Fetch Alpaca SIP 5Min bars (used for the final OHLCV dataset)."""
    return _intraday_bars(client, symbols, start_utc, end_utc, asof, timeframe="5Min")


def _compute_liquidity(
    dfs: dict[str, pd.DataFrame],
    calendar: xcals.ExchangeCalendar,
    prior_sessions: list[pd.Timestamp],
    min_sessions: int = 20,
) -> dict[str, dict[str, float | None]]:
    results: dict[str, dict[str, float | None]] = {}
    session_dates = [s.tz_localize(None).date() for s in prior_sessions]
    for sym, df in dfs.items():
        if df is None or df.empty:
            results[sym] = {"prior_close": None, "median_dollar_volume": None, "valid_sessions": 0}
            continue
        # Deduplicate timestamps (keep last) and drop malformed rows for ranking.
        df = df[~df.index.duplicated(keep="last")].dropna(subset=_OHLCV_COLUMNS)
        df = df.tz_convert("America/New_York")
        # Filter to regular sessions.
        regular = []
        for session_date in session_dates:
            ts = pd.Timestamp(session_date)
            if ts not in calendar.schedule.index:
                continue
            close = calendar.schedule.loc[ts, "close"].tz_convert("America/New_York")
            if not _is_regular_close(close):
                continue
            day_bars = df[df.index.date == session_date]
            if day_bars.empty:
                continue
            # 1D bars already one row per day, but use last available
            close = float(day_bars["close"].iloc[-1])
            volume = float(day_bars["volume"].sum())
            regular.append({"close": close, "dollar_volume": close * volume})
        if len(regular) < min_sessions:
            results[sym] = {"prior_close": None, "median_dollar_volume": None, "valid_sessions": len(regular)}
            continue
        prior_close = regular[-1]["close"]
        median_dv = float(pd.Series([r["dollar_volume"] for r in regular]).median())
        results[sym] = {"prior_close": prior_close, "median_dollar_volume": median_dv, "valid_sessions": len(regular)}
    return results


def run_build_universe(
    plan: DatasetPlan,
    output_dir: Path,
    api_key: str,
    secret_key: str,
    market_data_host: str = "https://data.alpaca.markets",
) -> None:
    out = output_dir / "universe"
    out.mkdir(parents=True, exist_ok=True)
    state = load_state(output_dir)
    state.phase = "build_universe"
    state.per_phase_request_counters_available = True
    controls = plan.conservative_universe_controls
    mapping = _load_taxonomy(output_dir)
    calendar = _load_xnys()
    etf_tickers = [t.upper() for t in plan.etf_stratum.get("tickers", [])]

    client = DatasetAlpacaClient(api_key, secret_key, market_data_host=market_data_host)

    completed = set(state.universe_built_for_months)
    # Load existing aggregate manifests so a resume or rerun preserves already completed months.
    universe_rows: list[dict[str, Any]] = [r for r in _load_csv_rows(out / "universe_manifest.csv") if r.get("effective_month") in completed]
    exclusion_rows: list[dict[str, Any]] = [r for r in _load_csv_rows(out / "exclusion_summary.csv") if r.get("effective_month") in completed]
    liquidity_rows: list[dict[str, Any]] = [r for r in _load_csv_rows(out / "liquidity_ranking_summary.csv") if r.get("effective_month") in completed]

    # Determine ranking timeframe and, if enabled, run a parity/sensitivity probe.
    parity_cfg = plan.liquidity_ranking.get("ranking_timeframe_parity_probe", {})
    ranking_timeframe = plan.liquidity_ranking.get("ranking_timeframe", "1D")
    parity_passed = False
    parity_message = "not_run"
    if parity_cfg.get("enabled") and ranking_timeframe != "5Min":
        parity_passed, parity_message = _ranking_timeframe_parity(
            client,
            calendar,
            parity_cfg.get("sample_symbols", ["SPY", "AAPL", "JPM"]),
            parity_cfg["sample_window"]["start"],
            parity_cfg["sample_window"]["end"],
            parity_cfg.get("tolerance_pct", 0.1),
            timeframe=ranking_timeframe,
            reference_timeframe=parity_cfg.get("reference_timeframe", "5Min"),
        )
        fallback = parity_cfg.get("fallback_on_failure") or plan.liquidity_ranking.get("fallback_on_failure")
        if not parity_passed and fallback:
            ranking_timeframe = fallback
            logger.warning("%s parity failed: %s; falling back to %s for ranking", plan.liquidity_ranking.get("ranking_timeframe", "1D"), parity_message, ranking_timeframe)
        elif parity_passed:
            logger.info("%s parity passed: %s", plan.liquidity_ranking.get("ranking_timeframe", "1D"), parity_message)
    else:
        # 1Day ranking is used under an approved amendment; no intraday parity probe is required.
        parity_passed = ranking_timeframe == "1Day"
        parity_message = "1Day ranking per approved amendment; 1Day volume is a total-liquidity proxy and is not equivalent to regular-session-only volume"

    state_data = {
        "ranking_timeframe": ranking_timeframe,
        "ranking_parity_passed": parity_passed,
        "ranking_parity_message": parity_message,
    }
    _write_json(out / "ranking_timeframe.json", state_data)

    for pit_date in plan.monthly_pit_dates:
        effective_month = _month_from_pit(pit_date)
        if effective_month in completed:
            continue
        logger.info("Building universe for effective month %s (PIT %s)", effective_month, pit_date)

        active_snap = _load_snapshot(output_dir, pit_date, "active")
        inactive_snap = _load_snapshot(output_dir, pit_date, "inactive")

        # Fail closed on incomplete Massive snapshots (active or inactive).
        for snap_label, snap in (("active", active_snap), ("inactive", inactive_snap)):
            obs = snap.observations[0]
            if obs.error or obs.max_pages_reached or not obs.pagination_complete:
                raise RuntimeError(f"{snap_label.capitalize()} snapshot for {pit_date} is incomplete")

        eligible_rows, exclusions, active_dup_tickers = _build_active_eligible(active_snap, mapping, controls)
        for ex in exclusions:
            ex["effective_month"] = effective_month
        exclusion_rows.extend(exclusions)

        # Record inactive-only tickers for lifecycle provenance but not eligible.
        active_tickers = {str(r.get("ticker") or "").strip().upper() for r in active_snap.rows}
        inactive_only = [r for r in inactive_snap.rows if str(r.get("ticker") or "").strip().upper() not in active_tickers]
        for row in inactive_only:
            exclusion_rows.append({
                "pit_date": pit_date,
                "effective_month": effective_month,
                "ticker": str(row.get("ticker") or "").strip().upper(),
                "reason": "inactive_only",
                "provider_type": str(row.get("type") or ""),
                "provider_exchange": str(row.get("primary_exchange") or ""),
            })

        tickers = [str(r.get("ticker") or "").strip().upper() for r in eligible_rows]
        first_session = calendar.date_to_session(_effective_month_start(effective_month), direction="next")
        prior_sessions = _prior_n_sessions(calendar, pd.Timestamp(first_session), plan.liquidity_ranking.get("prior_sessions_count", 20))

        liquidity_results: dict[str, dict[str, float | None]] = {}
        batch_size = int(plan.ranking_download_efficiency.get("multi_symbol_batch_size", 400))
        if ranking_timeframe not in ("1D", "1Day"):
            # Intraday responses are larger; keep per-call payload manageable.
            # 30Min has only 13 bars/session, so a 300-symbol batch stays well
            # under Alpaca's ~4k symbol URL ceiling and is still one page.
            cap = 300 if ranking_timeframe == "30Min" else 100
            batch_size = min(batch_size, cap)
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            if ranking_timeframe in ("1D", "1Day"):
                # 1Day bars are already one row per session; do not aggregate from intraday bars.
                dfs, meta = _daily_bars_for_ranking(client, batch, prior_sessions, asof=pit_date)
            else:
                # Fetch coarser intraday bars (e.g. 30Min) and aggregate to daily for ranking.
                start_utc = prior_sessions[0].tz_convert("UTC") if prior_sessions else None
                end_utc = (prior_sessions[-1] + pd.Timedelta(hours=24)).tz_convert("UTC") if prior_sessions else None
                if start_utc is None:
                    dfs, meta = {}, {}
                else:
                    dfs, meta = _intraday_bars(client, batch, start_utc, end_utc, asof=pit_date, timeframe=ranking_timeframe)
                    dfs = _aggregate_to_daily(dfs, calendar)
            meta = meta or {}
            if not meta.get("pagination_complete", False):
                raise RuntimeError(f"Ranking pagination incomplete for {effective_month} batch {i}")
            results = _compute_liquidity(dfs, calendar, prior_sessions)
            liquidity_results.update(results)
            state.alpaca_request_count += meta.get("page_count", 1)
            state.alpaca_ranking_logical_calls += meta.get("logical_calls", 1)
            state.alpaca_ranking_http_pages += meta.get("http_pages", meta.get("page_count", 1))
            state.alpaca_ranking_http_attempts += meta.get("http_attempts", meta.get("page_count", 1))
            state.alpaca_ranking_http_429s += meta.get("http_429s", 0)
            state.alpaca_ranking_http_errors += meta.get("http_errors", 0)
            state.pagination_cycles += int(meta.get("pagination_cycle_detected", False))
            response_symbols = {str(s).upper() for s in meta.get("response_symbols", [])}
            state.request_audit_rows.append({
                "phase": "build_universe",
                "effective_month": effective_month,
                "batch_index": i,
                "requested_symbols": ",".join(batch),
                "response_symbols": ",".join(sorted(response_symbols)),
                "logical_calls": meta.get("logical_calls", 1),
                "http_pages": meta.get("http_pages", meta.get("page_count", 1)),
                "http_attempts": meta.get("http_attempts", meta.get("page_count", 1)),
                "http_429s": meta.get("http_429s", 0),
                "http_errors": meta.get("http_errors", 0),
                "pagination_complete": meta.get("pagination_complete", False),
                "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                "safe_error_classification": meta.get("safe_error_classification", "unknown"),
                "http_status": meta.get("http_status", 0),
            })
            save_state(output_dir, state)

        # Build ranking
        ranking_entries = []
        for r in eligible_rows:
            ticker = str(r.get("ticker") or "").strip().upper()
            liq = liquidity_results.get(ticker, {"prior_close": None, "median_dollar_volume": None, "valid_sessions": 0})
            exchange = str(r.get("primary_exchange") or "").strip().upper()
            category = _category_for_row(r, mapping)
            ranking_entries.append({
                "ticker": ticker,
                "exchange": exchange,
                "category": category,
                "prior_close": liq["prior_close"],
                "median_dollar_volume": liq["median_dollar_volume"],
                "valid_sessions": liq["valid_sessions"],
            })

        min_close = float(plan.liquidity_ranking.get("prior_close_min_usd", 5.0))
        min_volume = float(plan.liquidity_ranking.get("prior_20_sessions_median_dollar_volume_min_usd", 50_000_000))
        qualified = [
            e for e in ranking_entries
            if e["prior_close"] is not None and e["prior_close"] >= min_close
            and e["median_dollar_volume"] is not None and e["median_dollar_volume"] >= min_volume
            and e["valid_sessions"] >= plan.liquidity_ranking.get("prior_sessions_count", 20)
        ]
        qualified.sort(key=lambda e: (-e["median_dollar_volume"], e["ticker"]))
        top_n = int(plan.liquidity_ranking.get("rank_top_n", 50))
        selected = qualified[:top_n]
        selected_tickers = {e["ticker"] for e in selected}

        for e in ranking_entries:
            liquidity_rows.append({
                "effective_month": effective_month,
                "pit_date": pit_date,
                "ticker": e["ticker"],
                "exchange": e["exchange"],
                "category": e["category"],
                "prior_close": e["prior_close"],
                "median_dollar_volume": e["median_dollar_volume"],
                "valid_sessions": e["valid_sessions"],
                "qualified": e["ticker"] in {q["ticker"] for q in qualified},
                "selected": e["ticker"] in selected_tickers,
                "rank": None,
            })

        for rank, e in enumerate(selected, start=1):
            for row in liquidity_rows:
                if row["effective_month"] == effective_month and row["ticker"] == e["ticker"]:
                    row["rank"] = rank

        # Build universe manifest rows
        for e in ranking_entries:
            ticker = e["ticker"]
            matched = [r for r in eligible_rows if str(r.get("ticker") or "").strip().upper() == ticker]
            row = matched[0] if matched else {}
            included = e["ticker"] in selected_tickers
            exclusion_reason = "" if included else "not_in_top_50"
            if e["prior_close"] is None or e["median_dollar_volume"] is None:
                exclusion_reason = "insufficient_liquidity_data"
            elif e["prior_close"] < min_close:
                exclusion_reason = "below_prior_close_threshold"
            elif e["median_dollar_volume"] < min_volume:
                exclusion_reason = "below_median_volume_threshold"
            member = UniverseMember(
                effective_month=effective_month,
                pit_date=pit_date,
                ticker=ticker,
                stratum="stock",
                reference_provider="massive",
                security_type_category=e["category"],
                primary_exchange=e["exchange"],
                duplicate_status="unique" if ticker not in active_dup_tickers else "duplicate_excluded",
                prior_close=e["prior_close"],
                valid_prior_session_count=int(e["valid_sessions"] or 0),
                median_prior_20_dollar_volume=e["median_dollar_volume"],
                liquidity_rank=next((r["rank"] for r in liquidity_rows if r["effective_month"] == effective_month and r["ticker"] == ticker), None),
                included=included,
                exclusion_reason=exclusion_reason,
                source_snapshot_sha256=active_snap.canonical_sha256,
                ohlcv_manifest_id=f"{effective_month}/{ticker}",
            )
            universe_rows.append(member.to_dict())

        # Add fixed ETF stratum
        for etf in etf_tickers:
            universe_rows.append({
                "effective_month": effective_month,
                "pit_date": pit_date,
                "ticker": etf,
                "stratum": "etf",
                "reference_provider": "v1_spec",
                "security_type_category": "etf",
                "primary_exchange": "",
                "duplicate_status": "n/a",
                "prior_close": None,
                "valid_prior_session_count": 0,
                "median_prior_20_dollar_volume": None,
                "liquidity_rank": None,
                "included": True,
                "exclusion_reason": "",
                "source_snapshot_sha256": plan.original_strategy_spec_sha256,
                "ohlcv_manifest_id": f"{effective_month}/{etf}",
            })

        completed.add(effective_month)
        state.universe_built_for_months = sorted(completed)
        save_state(output_dir, state)

    _write_csv(out / "universe_manifest.csv", universe_rows)
    _write_csv(out / "exclusion_summary.csv", exclusion_rows)
    _write_csv(out / "liquidity_ranking_summary.csv", liquidity_rows)
    state.phase = "build_universe_done"
    save_state(output_dir, state)


def _is_regular_session_minute(ts: pd.Timestamp) -> bool:
    """True for a 5-minute bar start within the XNYS 09:30-16:00 window."""
    minute = ts.hour * 60 + ts.minute
    return 570 <= minute < 960 and minute % 5 == 0


def _aggregate_to_daily(dfs: dict[str, pd.DataFrame], calendar: xcals.ExchangeCalendar) -> dict[str, pd.DataFrame]:
    """Aggregate intraday regular-session bars to daily close/volume for liquidity ranking."""
    daily: dict[str, pd.DataFrame] = {}
    for sym, df in dfs.items():
        if df is None or df.empty:
            daily[sym] = pd.DataFrame(columns=_OHLCV_COLUMNS)
            continue
        df = df.tz_convert("America/New_York")
        # Select only bars starting within the regular session and drop early-close sessions.
        on_grid = pd.Series(
            [_is_regular_session_minute(d) for d in df.index],
            index=df.index,
        )
        df = df[on_grid]
        session_dates = df.index.to_series().dt.date.unique()
        keep_dates = set()
        for d in session_dates:
            ts = pd.Timestamp(d)
            if ts not in calendar.schedule.index:
                continue
            close = calendar.schedule.loc[ts, "close"].tz_convert("America/New_York")
            if _is_regular_close(close):
                keep_dates.add(d)
        df = df[df.index.to_series().dt.date.isin(keep_dates)]
        rows = []
        for session_date, g in df.groupby(df.index.to_series().dt.date):
            if g.empty:
                continue
            rows.append({
                "datetime": pd.Timestamp(f"{session_date} 04:00", tz="America/New_York").tz_convert("UTC"),
                "open": float(g["open"].iloc[0]),
                "high": float(g["high"].max()),
                "low": float(g["low"].min()),
                "close": float(g["close"].iloc[-1]),
                "volume": float(g["volume"].sum()),
            })
        daily[sym] = pd.DataFrame(rows).set_index("datetime") if rows else pd.DataFrame(columns=_OHLCV_COLUMNS)
    return daily


def _split_for_symbol(universe_df: pd.DataFrame, effective_month: str, stratum: str | None = None) -> list[str]:
    mask = universe_df["effective_month"] == effective_month
    if stratum:
        mask = mask & (universe_df["stratum"] == stratum)
    return universe_df.loc[mask & universe_df["included"], "ticker"].tolist()


def _minute_of_day(ts: pd.Timestamp) -> int:
    return ts.hour * 60 + ts.minute


def _filter_regular_session(
    df: pd.DataFrame,
    calendar: xcals.ExchangeCalendar,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return regular-session 5Min bars and counts of removed bars.

    Bars are kept only if their start minute is on the XNYS 5-minute grid
    between 09:30 (inclusive) and 16:00 (exclusive) and the session is a
    regular (non-early) close day. Removed bars are counted by category.
    """
    if df is None or df.empty:
        return df, {"premarket": 0, "after_hours": 0, "early_close": 0, "off_grid": 0}
    df = df.tz_convert("America/New_York")
    hours = df.index.hour
    minutes_of_day = hours * 60 + df.index.minute
    in_grid = (minutes_of_day >= 570) & (minutes_of_day < 960) & (minutes_of_day % 5 == 0)
    premarket = minutes_of_day < 570
    after_hours = minutes_of_day >= 960
    # Identify early-close/non-session days and remove all bars for those dates.
    session_dates = df.index.to_series().dt.date.unique()
    early_close_dates = set()
    non_session_dates = set()
    for session_date in session_dates:
        ts = pd.Timestamp(session_date)
        if ts not in calendar.schedule.index:
            non_session_dates.add(session_date)
            continue
        close = calendar.schedule.loc[ts, "close"].tz_convert("America/New_York")
        if not _is_regular_close(close):
            early_close_dates.add(session_date)
    date_series = pd.Series(df.index.date, index=df.index)
    early_close_removed = int(date_series.isin(early_close_dates).sum())
    non_session_removed = int(date_series.isin(non_session_dates).sum())
    keep_mask = in_grid & ~date_series.isin(early_close_dates | non_session_dates)
    off_grid = ~in_grid & ~premarket & ~after_hours & ~date_series.isin(early_close_dates | non_session_dates)
    counts = {
        "premarket": int(premarket.sum()),
        "after_hours": int(after_hours.sum()),
        "early_close": early_close_removed,
        "off_grid": int(off_grid.sum()),
        "non_session": non_session_removed,
    }
    return df[keep_mask].copy(), counts


def _expected_sessions_and_bars(
    calendar: xcals.ExchangeCalendar,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> tuple[int, int]:
    sessions = _sessions_in_range(calendar, start_utc, end_utc)
    bars_per_session = 78
    return len(sessions), len(sessions) * bars_per_session


def _detect_invalid_ohlc(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    invalid = (
        (df["high"] < df["low"])
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (~df[_OHLCV_COLUMNS].apply(lambda s: pd.to_numeric(s, errors="coerce").notna()).all(axis=1))
    )
    return int(invalid.sum())


def run_fetch_ohlcv(
    plan: DatasetPlan,
    output_dir: Path,
    api_key: str,
    secret_key: str,
    market_data_host: str = "https://data.alpaca.markets",
) -> None:
    universe_df = pd.read_csv(output_dir / "universe" / "universe_manifest.csv")
    calendar = _load_xnys()
    ohlcv_dir = output_dir / "ohlcv"
    ohlcv_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(output_dir)
    state.phase = "fetch_ohlcv"
    state.per_phase_request_counters_available = True
    state.pre_normalization_metrics_available = True
    client = DatasetAlpacaClient(api_key, secret_key, market_data_host=market_data_host)

    completed = set(state.ohlcv_fetched_for_months)
    # Load existing aggregate manifests so a resume or rerun preserves already completed months.
    ohlcv_records: list[dict[str, Any]] = [r for r in _load_csv_rows(ohlcv_dir / "ohlcv_manifest.csv") if r.get("effective_month") in completed]
    quality_records: list[dict[str, Any]] = [r for r in _load_csv_rows(ohlcv_dir / "data_quality.csv") if r.get("effective_month") in completed]

    for month in sorted(universe_df["effective_month"].unique()):
        if month in completed:
            continue
        logger.info("Fetching OHLCV for effective month %s", month)
        tickers = _split_for_symbol(universe_df, month)
        if not tickers:
            completed.add(month)
            continue

        first_session = calendar.date_to_session(_effective_month_start(month), direction="next")
        prior_sessions = _prior_n_sessions(calendar, pd.Timestamp(first_session), plan.ohlcv_policy.get("warmup_sessions", 20))
        last_session = calendar.date_to_session(_month_end(month), direction="previous")
        if prior_sessions:
            start_utc = prior_sessions[0].tz_convert("UTC")
        else:
            start_utc = pd.Timestamp(first_session, tz="America/New_York").tz_convert("UTC")
        end_utc = (pd.Timestamp(last_session, tz="America/New_York") + pd.Timedelta(hours=24)).tz_convert("UTC")

        pit_date = universe_df.loc[universe_df["effective_month"] == month, "pit_date"].iloc[0]
        asof = pit_date

        expected_sessions, expected_bars = _expected_sessions_and_bars(calendar, start_utc, end_utc)

        batch_size = int(plan.ranking_download_efficiency.get("multi_symbol_batch_size", 400))
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            dfs, meta = _five_min_bars(client, batch, start_utc, end_utc, asof=asof)
            state.alpaca_request_count += meta.get("page_count", 1)
            state.alpaca_ohlcv_logical_calls += meta.get("logical_calls", 1)
            state.alpaca_ohlcv_http_pages += meta.get("http_pages", meta.get("page_count", 1))
            state.alpaca_ohlcv_http_attempts += meta.get("http_attempts", meta.get("page_count", 1))
            state.alpaca_ohlcv_http_429s += meta.get("http_429s", 0)
            state.alpaca_ohlcv_http_errors += meta.get("http_errors", 0)
            state.pagination_cycles += int(meta.get("pagination_cycle_detected", False))
            pagination_incomplete = not meta.get("pagination_complete", False)
            if pagination_incomplete:
                state.incomplete_requests += 1
                state.errors.append(f"{month} batch {i}: pagination incomplete")
            response_symbols = {str(s).upper() for s in meta.get("response_symbols", [])}
            state.request_audit_rows.append({
                "phase": "fetch_ohlcv",
                "effective_month": month,
                "batch_index": i,
                "requested_symbols": ",".join(batch),
                "response_symbols": ",".join(sorted(response_symbols)),
                "logical_calls": meta.get("logical_calls", 1),
                "http_pages": meta.get("http_pages", meta.get("page_count", 1)),
                "http_attempts": meta.get("http_attempts", meta.get("page_count", 1)),
                "http_429s": meta.get("http_429s", 0),
                "http_errors": meta.get("http_errors", 0),
                "pagination_complete": meta.get("pagination_complete", False),
                "pagination_cycle_detected": meta.get("pagination_cycle_detected", False),
                "safe_error_classification": meta.get("safe_error_classification", "unknown"),
                "http_status": meta.get("http_status", 0),
            })
            for sym in batch:
                df = dfs.get(sym.upper(), pd.DataFrame())
                requested = sym.upper()
                returned = sym.upper() if sym.upper() in response_symbols else "missing_from_response"
                symbol_mismatch = requested != returned
                if pagination_incomplete:
                    state.errors.append(f"{month}/{requested}: batch pagination incomplete")

                # Observability: count duplicates and malformed rows before deduplication.
                # Treat non-finite values (inf/-inf/NaN) as malformed and drop them after counting.
                if not df.empty:
                    df = df.replace([np.inf, -np.inf], np.nan)
                pre_dedup_rows = len(df)
                pre_dedup_duplicate_bars = int(df.index.duplicated().sum()) if not df.empty else 0
                malformed_rows = int(df[_OHLCV_COLUMNS].isna().any(axis=1).sum()) if not df.empty else 0
                duplicate_rate = (pre_dedup_duplicate_bars / pre_dedup_rows * 100) if pre_dedup_rows else 0.0
                malformed_rate = (malformed_rows / pre_dedup_rows * 100) if pre_dedup_rows else 0.0

                # Deterministic normalization: keep last duplicate and drop malformed rows.
                df_clean = df[~df.index.duplicated(keep="last")].dropna(subset=_OHLCV_COLUMNS)
                duplicate_bars_after = int(df_clean.index.duplicated().sum())

                df_filtered, counts = _filter_regular_session(df_clean, calendar)
                invalid = _detect_invalid_ohlc(df_filtered)
                actual_sessions = df_filtered.index.to_series().dt.date.nunique() if not df_filtered.empty else 0
                actual_bars = len(df_filtered)
                missing_bars = max(0, expected_bars - actual_bars)
                missing_rate = (missing_bars / expected_bars * 100) if expected_bars else 0.0
                zero_volume_bars = int((df_filtered["volume"] == 0).sum()) if "volume" in df_filtered.columns else 0
                zv_rate = (zero_volume_bars / actual_bars * 100) if actual_bars else 0.0

                rel_path = f"{month}/{sym.upper()}.parquet"
                month_dir = ohlcv_dir / month
                month_dir.mkdir(parents=True, exist_ok=True)
                file_path = month_dir / f"{sym.upper()}.parquet"
                df_filtered.to_parquet(file_path)
                file_size = file_path.stat().st_size
                sha = _sha256_file(file_path)

                record = OhlcvFile(
                    manifest_id=f"{month}/{sym.upper()}",
                    symbol=sym.upper(),
                    effective_month=month,
                    feed="sip",
                    timeframe="5Min",
                    adjustment="raw",
                    start_utc=start_utc.isoformat().replace("+00:00", "Z"),
                    end_utc=end_utc.isoformat().replace("+00:00", "Z"),
                    regular_session_bars=actual_bars,
                    regular_session_sessions=actual_sessions,
                    missing_bars=missing_bars,
                    missing_bar_rate_pct=round(missing_rate, 4),
                    zero_volume_bars=zero_volume_bars,
                    zero_volume_bar_rate_pct=round(zv_rate, 4),
                    invalid_ohlc_rows=invalid,
                    off_grid_bars=counts["off_grid"],
                    premarket_removed=counts["premarket"],
                    after_hours_removed=counts["after_hours"],
                    early_close_removed=counts["early_close"],
                    file_size_bytes=file_size,
                    sha256=sha,
                    relative_path=rel_path,
                    requested_symbol=requested,
                    returned_symbol=returned,
                    pagination_complete=meta["pagination_complete"],
                    page_count=meta["page_count"],
                    pre_normalization_metrics_available=True,
                    pre_dedup_duplicate_bars=pre_dedup_duplicate_bars,
                    duplicate_bars=duplicate_bars_after,
                    duplicate_bar_rate_pct=round(duplicate_rate, 4),
                    malformed_rows=malformed_rows,
                    malformed_row_rate_pct=round(malformed_rate, 4),
                )
                ohlcv_records.append(record.to_dict())
                split = _split_name_for_month(plan, month)
                quality = DataQuality(
                    symbol=sym.upper(),
                    effective_month=month,
                    split=split,
                    expected_sessions=expected_sessions,
                    actual_sessions=actual_sessions,
                    expected_bars=expected_bars,
                    actual_bars=actual_bars,
                    missing_bars=missing_bars,
                    missing_bar_rate_pct=round(missing_rate, 4),
                    zero_volume_bars=zero_volume_bars,
                    zero_volume_bar_rate_pct=round(zv_rate, 4),
                    invalid_ohlc_rows=invalid,
                    off_grid_bars=counts["off_grid"],
                    premarket_removed=counts["premarket"],
                    after_hours_removed=counts["after_hours"],
                    early_close_removed=counts["early_close"],
                    ohlc_consistency_violations=invalid,
                    provider_feed="sip",
                    timeframe="5Min",
                    adjustment="raw",
                    file_sha256=sha,
                    relative_path=rel_path,
                    requested_symbol=requested,
                    returned_symbol=returned,
                    symbol_mismatch=symbol_mismatch,
                    pagination_complete=meta["pagination_complete"],
                    rejected=False,
                    rejection_reason="",
                    pre_normalization_metrics_available=True,
                    pre_dedup_duplicate_bars=pre_dedup_duplicate_bars,
                    duplicate_bars=duplicate_bars_after,
                    duplicate_bar_rate_pct=round(duplicate_rate, 4),
                    malformed_rows=malformed_rows,
                    malformed_row_rate_pct=round(malformed_rate, 4),
                )
                quality_records.append(quality.to_dict())

        completed.add(month)
        state.ohlcv_fetched_for_months = sorted(completed)
        save_state(output_dir, state)

    _write_csv(ohlcv_dir / "ohlcv_manifest.csv", ohlcv_records)
    _write_csv(ohlcv_dir / "data_quality.csv", quality_records)
    state.phase = "fetch_ohlcv_done"
    save_state(output_dir, state)


def _split_name_for_month(plan: DatasetPlan, month: str) -> str:
    """Classify an effective month into development/validation/holdout by date overlap.

    Monthly classification uses the actual locked split date ranges and the
    calendar month represented by ``month`` (``YYYY-MM``), not just the first day.
    """
    ds = plan.dataset
    month_start = _effective_month_start(month)
    month_end = _month_end(month)

    def _overlaps(split: dict[str, Any]) -> bool:
        if not split:
            return False
        split_start = pd.Timestamp(split["start"])
        split_end = pd.Timestamp(split["end"])
        return month_start <= split_end and month_end >= split_start

    if _overlaps(ds.get("development", {})):
        return "development"
    if _overlaps(ds.get("validation", {})):
        return "validation"
    if _overlaps(ds.get("holdout", {})):
        return "holdout"
    return "unknown"


def _reject_reason_row(r: pd.Series, *, max_missing: float, max_zero: float, max_dup: float, max_mal: float) -> str:
    reasons: list[str] = []
    if not r["pagination_complete"]:
        reasons.append("pagination_incomplete")
    if r["symbol_mismatch"]:
        reasons.append("symbol_mismatch")
    if r["provider_feed"] != "sip":
        reasons.append("feed_mismatch")
    if r["timeframe"] != "5Min":
        reasons.append("timeframe_mismatch")
    if r["adjustment"] != "raw":
        reasons.append("adjustment_mismatch")
    if r["off_grid_bars"] > 0:
        reasons.append("off_grid_bars")
    if r["invalid_ohlc_rows"] > 0:
        reasons.append("invalid_ohlc")
    if not r["file_sha256_match"]:
        reasons.append("manifest_sha_mismatch")
    if r["missing_bar_rate_pct"] > max_missing:
        reasons.append("missing_bar_rate")
    if r["zero_volume_bar_rate_pct"] > max_zero:
        reasons.append("zero_volume_rate")
    if not pd.isna(r["duplicate_bar_rate_pct"]) and r["duplicate_bar_rate_pct"] > max_dup:
        reasons.append("duplicate_rate")
    if not pd.isna(r["malformed_row_rate_pct"]) and r["malformed_row_rate_pct"] > max_mal:
        reasons.append("malformed_row_rate")
    if not r["pre_normalization_metrics_available"] or pd.isna(r["duplicate_bar_rate_pct"]) or pd.isna(r["malformed_row_rate_pct"]):
        reasons.append("pre_normalization_metrics_unavailable")
    return "; ".join(reasons)


def _safe_max_numeric(series: pd.Series) -> float | None:
    if series.empty or series.isna().all():
        return None
    return round(float(series.max()), 4)


def run_validate(
    plan: DatasetPlan,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate data quality and enforce disposition rules.

    Disposition hierarchy:
      - Provider/provenance/manifest/timestamp/pagination/silent-substitution/symbol-identity failures → invalid.
      - Data-quality threshold breach (including unavailable pre-normalization metrics) → inconclusive.
      - Otherwise valid.

    The 5% symbol-rejection threshold is applied independently to each monthly universe.
    """
    state = load_state(output_dir)
    state.phase = "validate"
    q_path = output_dir / "ohlcv" / "data_quality.csv"
    if not q_path.exists():
        raise FileNotFoundError("OHLCV data quality file not found; run fetch-ohlcv first")
    df = pd.read_csv(q_path)
    thresholds = plan.data_quality_thresholds
    max_missing = float(thresholds.get("missing_bar_rate_per_symbol_pct_max", 5.0))
    max_zero = float(thresholds.get("zero_volume_bar_rate_per_symbol_pct_max", 10.0))
    max_dup = float(thresholds.get("duplicate_bar_rate_per_symbol_pct_max", 1.0))
    max_mal = float(thresholds.get("malformed_row_rate_per_symbol_pct_max", max_dup))
    max_rejected_pct = float(thresholds.get("symbols_rejected_for_data_quality_pct_max", 5.0))

    for col in ("pagination_complete", "symbol_mismatch", "pre_normalization_metrics_available"):
        if col in df.columns:
            df[col] = df[col].astype(bool)
        else:
            df[col] = False
    for col in ("provider_feed", "timeframe", "adjustment", "file_sha256", "relative_path"):
        if col not in df.columns:
            df[col] = ""
    for col in ("pre_dedup_duplicate_bars", "malformed_rows"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("duplicate_bar_rate_pct", "malformed_row_rate_pct"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Manifest/provenance: verify each row's file SHA-256 matches its stored manifest.
    def _row_file_sha_matches(r: pd.Series) -> bool:
        expected = r.get("file_sha256", "") or ""
        rel_path = r.get("relative_path", "") or ""
        if not expected or not rel_path:
            return False
        fpath = output_dir / "ohlcv" / rel_path
        return fpath.exists() and _sha256_file(fpath) == expected

    df["file_sha256_match"] = df.apply(_row_file_sha_matches, axis=1)

    df["rejected"] = False
    df["rejection_reason"] = ""

    invalid_mask = (
        (~df["pagination_complete"])
        | df["symbol_mismatch"]
        | (df["provider_feed"] != "sip")
        | (df["timeframe"] != "5Min")
        | (df["adjustment"] != "raw")
        | (df["off_grid_bars"] > 0)
        | (df["invalid_ohlc_rows"] > 0)
        | (~df["file_sha256_match"])
    )

    unverified_mask = (
        (~df["pre_normalization_metrics_available"])
        | df["pre_dedup_duplicate_bars"].isna()
        | df["malformed_rows"].isna()
        | df["duplicate_bar_rate_pct"].isna()
        | df["malformed_row_rate_pct"].isna()
    )

    quality_mask = (
        (df["missing_bar_rate_pct"] > max_missing)
        | (df["zero_volume_bar_rate_pct"] > max_zero)
        | ((~df["duplicate_bar_rate_pct"].isna()) & (df["duplicate_bar_rate_pct"] > max_dup))
        | ((~df["malformed_row_rate_pct"].isna()) & (df["malformed_row_rate_pct"] > max_mal))
    )

    df.loc[invalid_mask | unverified_mask | quality_mask, "rejected"] = True
    df["rejection_reason"] = df.apply(
        lambda r: _reject_reason_row(r, max_missing=max_missing, max_zero=max_zero, max_dup=max_dup, max_mal=max_mal),
        axis=1,
    )
    _write_csv(q_path, df.to_dict("records"))

    # Persisted provider-error/cycle state makes the whole dataset invalid.
    any_invalid_state = bool(
        state.pagination_cycles > 0
        or state.http_error_count > 0
        or state.incomplete_requests > 0
    )

    # Per-monthly-universe rejection accounting.
    monthly_rejections: dict[str, dict[str, int | float]] = {}
    any_invalid = False
    any_inconclusive = False
    any_unverified = False
    for month, group in df.groupby("effective_month"):
        total = len(group)
        invalid = int(invalid_mask[group.index].sum())
        unverified = int(unverified_mask[group.index].sum())
        quality_rejected = int((quality_mask[group.index] & ~invalid_mask[group.index] & ~unverified_mask[group.index]).sum())
        rejected = invalid + unverified + quality_rejected
        rejected_pct = (rejected / total * 100) if total else 0.0
        monthly_rejections[str(month)] = {
            "total_symbols": total,
            "invalid_symbols": invalid,
            "unverified_symbols": unverified,
            "data_quality_rejected": quality_rejected,
            "rejected_pct": round(rejected_pct, 4),
            "breaches_5pct_threshold": rejected_pct > max_rejected_pct,
        }
        if invalid > 0:
            any_invalid = True
        if unverified > 0:
            any_unverified = True
        if rejected_pct > max_rejected_pct:
            any_inconclusive = True

    total_symbols = int(df.groupby("effective_month").size().sum())
    overall_invalid = int(invalid_mask.sum())
    overall_unverified = int(unverified_mask.sum())
    overall_quality_rejected = int((quality_mask & ~invalid_mask & ~unverified_mask).sum())
    overall_rejected = overall_invalid + overall_unverified + overall_quality_rejected
    overall_rejected_pct = (overall_rejected / total_symbols * 100) if total_symbols else 0.0

    if any_invalid or any_invalid_state:
        disposition = "invalid"
        reason = f"Provider/provenance/pagination/symbol-identity/manifest failures in {overall_invalid} symbol-months"
        if any_invalid_state:
            reason += f"; persisted provider errors/cycles/incomplete requests in state (cycles={state.pagination_cycles}, http_errors={state.http_error_count}, incomplete={state.incomplete_requests})"
    elif any_inconclusive or any_unverified:
        disposition = "inconclusive"
        reason = "One or more monthly universes exceeded the 5% data-quality rejection threshold or pre-normalization metrics are unavailable"
    else:
        disposition = "valid"
        reason = f"All monthly universes within thresholds; {overall_quality_rejected} of {total_symbols} symbol-months rejected for data quality"

    summary = {
        "disposition": disposition,
        "reason": reason,
        "total_symbol_months": total_symbols,
        "overall_invalid_symbol_months": overall_invalid,
        "overall_unverified_symbol_months": overall_unverified,
        "overall_data_quality_rejected": overall_quality_rejected,
        "overall_symbols_rejected_pct": round(overall_rejected_pct, 4),
        "monthly_rejections": monthly_rejections,
        "max_missing_rate_pct": _safe_max_numeric(df["missing_bar_rate_pct"]),
        "max_zero_volume_rate_pct": _safe_max_numeric(df["zero_volume_bar_rate_pct"]),
        "max_duplicate_rate_pct": _safe_max_numeric(df["duplicate_bar_rate_pct"]),
        "max_malformed_row_rate_pct": _safe_max_numeric(df["malformed_row_rate_pct"]),
    }
    _write_json(output_dir / "validation_summary.json", summary)
    state.validated = True
    save_state(output_dir, state)
    return summary


def run_finalize(
    plan: DatasetPlan,
    output_dir: Path,
    artifact_dir: Path,
    *,
    starting_main_sha: str = "",
    branch: str = "",
    live_run_head: str = "",
    pre_registration_commit: str = "",
    runtime_seconds: float | None = None,
    runtime_note: str = "",
) -> DatasetDecision:
    state = load_state(output_dir)
    state.phase = "finalize"

    universe_df = pd.read_csv(output_dir / "universe" / "universe_manifest.csv")
    validation = json.loads((output_dir / "validation_summary.json").read_text(encoding="utf-8"))

    monthly_counts = (
        universe_df[(universe_df["stratum"] == "stock") & (universe_df["included"])]
        .groupby("effective_month")["ticker"]
        .nunique()
        .to_dict()
    )
    etf_count = int((universe_df["stratum"] == "etf").sum() / len(plan.monthly_pit_dates)) if not universe_df.empty else len(plan.etf_stratum.get("tickers", []))
    unique_stocks = universe_df[(universe_df["stratum"] == "stock") & (universe_df["included"])]["ticker"].nunique()
    total_symbol_months = len(universe_df[(universe_df["stratum"] == "stock") & (universe_df["included"])])

    storage_bytes = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())

    ranking_info = json.loads((output_dir / "universe" / "ranking_timeframe.json").read_text(encoding="utf-8"))

    # Runtime: prefer the accumulated state runtime; fall back to the passed value.
    final_runtime = state.runtime_seconds if state.runtime_seconds is not None else runtime_seconds
    final_runtime_note = runtime_note
    if state.runtime_seconds is None and runtime_seconds is not None:
        final_runtime_note = "Runtime recorded for finalize phase only"
    elif state.runtime_seconds is None:
        final_runtime_note = "Historical runtime unavailable"

    # Pre-normalization metrics availability is derived from the data quality manifest.
    dq_path = output_dir / "ohlcv" / "data_quality.csv"
    pre_normalization_metrics_available = False
    if dq_path.exists():
        dq_df = pd.read_csv(dq_path)
        if not dq_df.empty:
            pre_normalization_metrics_available = bool(
                dq_df["pre_normalization_metrics_available"].astype(bool).all()
                and dq_df["duplicate_bar_rate_pct"].notna().all()
                and dq_df["malformed_row_rate_pct"].notna().all()
            )

    # Per-phase Alpaca counters are None when the state was not recorded with detailed accounting.
    if state.per_phase_request_counters_available:
        per_phase = {
            "alpaca_ranking_logical_calls": state.alpaca_ranking_logical_calls,
            "alpaca_ranking_http_pages": state.alpaca_ranking_http_pages,
            "alpaca_ranking_http_attempts": state.alpaca_ranking_http_attempts,
            "alpaca_ranking_http_429s": state.alpaca_ranking_http_429s,
            "alpaca_ranking_http_errors": state.alpaca_ranking_http_errors,
            "alpaca_ohlcv_logical_calls": state.alpaca_ohlcv_logical_calls,
            "alpaca_ohlcv_http_pages": state.alpaca_ohlcv_http_pages,
            "alpaca_ohlcv_http_attempts": state.alpaca_ohlcv_http_attempts,
            "alpaca_ohlcv_http_429s": state.alpaca_ohlcv_http_429s,
            "alpaca_ohlcv_http_errors": state.alpaca_ohlcv_http_errors,
        }
    else:
        per_phase = {k: None for k in (
            "alpaca_ranking_logical_calls", "alpaca_ranking_http_pages", "alpaca_ranking_http_attempts",
            "alpaca_ranking_http_429s", "alpaca_ranking_http_errors",
            "alpaca_ohlcv_logical_calls", "alpaca_ohlcv_http_pages", "alpaca_ohlcv_http_attempts",
            "alpaca_ohlcv_http_429s", "alpaca_ohlcv_http_errors",
        )}

    decision = DatasetDecision(
        task_id=plan.task_id,
        dataset_id=plan.dataset_id,
        disposition=validation["disposition"],
        reason=validation.get("reason", ""),
        starting_main_sha=starting_main_sha,
        branch=branch,
        live_run_head=live_run_head,
        pre_registration_commit=pre_registration_commit,
        original_strategy_spec_sha256=plan.original_strategy_spec_sha256,
        amendment_v3_sha256=plan.amendment_v3_sha256,
        v4_decision_doc_sha256=plan.v4_decision_doc_sha256,
        alpaca_v2_probe_spec_sha256=plan.alpaca_v2_probe_spec_sha256,
        monthly_stock_counts={str(k): int(v) for k, v in monthly_counts.items()},
        etf_count=etf_count,
        unique_selected_stock_count=int(unique_stocks),
        total_selected_symbol_month_count=int(total_symbol_months),
        dataset_coverage_start=str(plan.dataset.get("dataset_start", "2025-01-02")),
        dataset_coverage_end=str(plan.dataset.get("dataset_end", "2025-12-31")),
        massive_http_requests=state.massive_request_count,
        massive_incomplete_snapshots=state.incomplete_requests,
        alpaca_http_requests=state.alpaca_request_count or None,
        alpaca_ranking_logical_calls=per_phase["alpaca_ranking_logical_calls"],
        alpaca_ranking_http_pages=per_phase["alpaca_ranking_http_pages"],
        alpaca_ranking_http_attempts=per_phase["alpaca_ranking_http_attempts"],
        alpaca_ranking_http_429s=per_phase["alpaca_ranking_http_429s"],
        alpaca_ranking_http_errors=per_phase["alpaca_ranking_http_errors"],
        alpaca_ohlcv_logical_calls=per_phase["alpaca_ohlcv_logical_calls"],
        alpaca_ohlcv_http_pages=per_phase["alpaca_ohlcv_http_pages"],
        alpaca_ohlcv_http_attempts=per_phase["alpaca_ohlcv_http_attempts"],
        alpaca_ohlcv_http_429s=per_phase["alpaca_ohlcv_http_429s"],
        alpaca_ohlcv_http_errors=per_phase["alpaca_ohlcv_http_errors"],
        http_errors=state.http_error_count,
        http_429s=state.http_429_count,
        pagination_cycles=state.pagination_cycles,
        incomplete_requests=state.incomplete_requests,
        runtime_seconds=final_runtime,
        runtime_note=final_runtime_note,
        local_storage_bytes=storage_bytes,
        ranking_timeframe=ranking_info.get("ranking_timeframe", "1D"),
        ranking_feed="sip",
        ranking_timeframe_parity_passed=ranking_info.get("ranking_parity_passed", False),
        parity_fallback_used=ranking_info.get("ranking_timeframe", "1D") != plan.liquidity_ranking.get("ranking_timeframe", "1D"),
        data_quality_disposition=validation["disposition"],
        missing_bar_rate_max_pct=validation.get("max_missing_rate_pct") or 0.0,
        zero_volume_rate_max_pct=validation.get("max_zero_volume_rate_pct") or 0.0,
        duplicate_rate_max_pct=validation.get("max_duplicate_rate_pct") or 0.0,
        symbols_rejected_pct=validation.get("overall_symbols_rejected_pct", 0.0),
        next_assignment="devin/intra-001-c-research-engine",
        per_phase_request_counters_available=state.per_phase_request_counters_available,
        pre_normalization_metrics_available=pre_normalization_metrics_available,
    )
    state.finalized = True
    save_state(output_dir, state)

    _write_safe_artifacts(plan, output_dir, artifact_dir, decision)
    return decision


def _write_safe_artifacts(
    plan: DatasetPlan,
    output_dir: Path,
    artifact_dir: Path,
    decision: DatasetDecision,
) -> None:
    run_id = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    out = Path(artifact_dir).expanduser().resolve() / run_id
    out.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}

    def cp(name: str, src: Path) -> None:
        if src.exists():
            dst = out / name
            shutil.copy2(src, dst)
            files[name] = _sha256_file(dst)

    # Copy generated artifacts from output dir
    cp("dataset_plan.lock.json", output_dir / "dataset_plan.lock.json")
    cp("universe_manifest.csv", output_dir / "universe" / "universe_manifest.csv")
    cp("exclusion_summary.csv", output_dir / "universe" / "exclusion_summary.csv")
    cp("liquidity_ranking_summary.csv", output_dir / "universe" / "liquidity_ranking_summary.csv")
    cp("ranking_timeframe.json", output_dir / "universe" / "ranking_timeframe.json")
    cp("ohlcv_manifest.csv", output_dir / "ohlcv" / "ohlcv_manifest.csv")
    cp("data_quality.csv", output_dir / "ohlcv" / "data_quality.csv")
    cp("validation_summary.json", output_dir / "validation_summary.json")

    # Reference snapshot summary
    snap_dir = output_dir / "reference_snapshots"
    snap_rows = []
    if snap_dir.exists():
        for f in sorted(snap_dir.glob("*.json")):
            if f.name == "taxonomy.json":
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            for obs in data.get("observations", []):
                snap_rows.append({
                    "pit_date": data.get("pit_date", ""),
                    "state": data.get("state", ""),
                    "row_count": data.get("row_count", 0),
                    "raw_sha256": data.get("raw_sha256", ""),
                    "canonical_sha256": data.get("canonical_sha256", ""),
                    "pagination_complete": obs.get("pagination_complete", False),
                    "page_count": obs.get("page_count", 0),
                    "error": obs.get("error", ""),
                })
    _write_csv(out / "reference_snapshot_summary.csv", snap_rows)
    files["reference_snapshot_summary.csv"] = _sha256_file(out / "reference_snapshot_summary.csv")

    if (snap_dir / "taxonomy.json").exists():
        tax_data = json.loads((snap_dir / "taxonomy.json").read_text(encoding="utf-8"))
        mapping_rows = []
        for code, category in sorted(tax_data.get("mapping", {}).items()):
            mapping_rows.append({
                "provider_code": code,
                "tradex_category": category,
            })
        _write_csv(out / "security_type_mapping.csv", mapping_rows)
    else:
        _write_csv(out / "security_type_mapping.csv", [])
    files["security_type_mapping.csv"] = _sha256_file(out / "security_type_mapping.csv")

    # Strategy and amendment references
    _write_json(out / "strategy_spec_reference.json", {
        "path": _repo_relative(plan.original_strategy_spec_path),
        "sha256": plan.original_strategy_spec_sha256,
    })
    files["strategy_spec_reference.json"] = _sha256_file(out / "strategy_spec_reference.json")
    _write_json(out / "amendment_reference.json", {
        "path": _repo_relative(plan.amendment_v3_path),
        "sha256": plan.amendment_v3_sha256,
    })
    files["amendment_reference.json"] = _sha256_file(out / "amendment_reference.json")

    # Request audit
    state = load_state(output_dir)

    def _per_phase_value(key: str) -> int | None:
        return getattr(state, key) if state.per_phase_request_counters_available else None

    request_rows = []
    request_rows.append({
        "provider": "massive",
        "request_count": state.massive_request_count,
        "http_error_count": state.http_error_count,
        "http_429_count": state.http_429_count,
        "pagination_cycles": 0,
        "incomplete_requests": state.incomplete_requests,
        "phase": "all",
        "notes": "Massive PIT reference snapshots",
    })
    request_rows.append({
        "provider": "alpaca",
        "phase": "ranking",
        "logical_calls": _per_phase_value("alpaca_ranking_logical_calls"),
        "http_pages": _per_phase_value("alpaca_ranking_http_pages"),
        "http_attempts": _per_phase_value("alpaca_ranking_http_attempts"),
        "http_429_count": _per_phase_value("alpaca_ranking_http_429s"),
        "http_error_count": _per_phase_value("alpaca_ranking_http_errors"),
        "pagination_cycles": state.pagination_cycles if state.per_phase_request_counters_available else None,
        "incomplete_requests": 0,
        "notes": "1Day liquidity ranking" if state.per_phase_request_counters_available else "unavailable (legacy/recomputed state)",
    })
    request_rows.append({
        "provider": "alpaca",
        "phase": "ohlcv",
        "logical_calls": _per_phase_value("alpaca_ohlcv_logical_calls"),
        "http_pages": _per_phase_value("alpaca_ohlcv_http_pages"),
        "http_attempts": _per_phase_value("alpaca_ohlcv_http_attempts"),
        "http_429_count": _per_phase_value("alpaca_ohlcv_http_429s"),
        "http_error_count": _per_phase_value("alpaca_ohlcv_http_errors"),
        "pagination_cycles": 0,
        "incomplete_requests": state.incomplete_requests if state.per_phase_request_counters_available else None,
        "notes": "5Min OHLCV dataset" if state.per_phase_request_counters_available else "unavailable (legacy/recomputed state)",
    })
    _write_csv(out / "request_audit.csv", request_rows)
    files["request_audit.csv"] = _sha256_file(out / "request_audit.csv")

    # Decision
    _write_json(out / "decision.json", decision.to_dict())
    files["decision.json"] = _sha256_file(out / "decision.json")

    # Manifest.lock
    manifest_rows = []
    ohlcv_manifest = output_dir / "ohlcv" / "ohlcv_manifest.csv"
    if ohlcv_manifest.exists():
        for row in csv.DictReader(ohlcv_manifest.read_text(encoding="utf-8").splitlines()):
            manifest_rows.append({
                "manifest_id": row["manifest_id"],
                "symbol": row["symbol"],
                "effective_month": row["effective_month"],
                "feed": row["feed"],
                "timeframe": row["timeframe"],
                "adjustment": row["adjustment"],
                "sha256": row["sha256"],
                "file_size_bytes": row["file_size_bytes"],
                "relative_path": row["relative_path"],
                "pagination_complete": row["pagination_complete"],
            })
    _write_json(out / "manifest.lock.json", {"schema_version": "1.0", "files": manifest_rows})
    files["manifest.lock.json"] = _sha256_file(out / "manifest.lock.json")

    # README
    lines = [
        "INTRA-001B-DATASET-V1 safe artifact bundle",
        f"Run ID: {run_id}",
        f"Task: {decision.task_id}",
        f"Disposition: {decision.disposition}",
        f"Branch: {decision.branch}",
        f"Live run head: {decision.live_run_head}",
        f"Pre-registration commit: {decision.pre_registration_commit}",
        f"Starting main SHA: {decision.starting_main_sha}",
        f"Ran at: {decision.ran_at}",
        "",
        "This bundle contains manifest-locked research-only artifacts.",
        "The full normalized OHLCV dataset is stored in the private dataset root, not in this repo.",
    ]
    (out / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files["README.txt"] = _sha256_file(out / "README.txt")

    # Report.md must be generated before the manifest and checksum so it can be covered by them.
    report = _generate_report(plan, decision, output_dir)
    (out / "report.md").write_text(report, encoding="utf-8")
    files["report.md"] = _sha256_file(out / "report.md")

    # Write artifact manifest (excludes itself and checksums.sha256 to avoid circular hashes)
    manifest_path = out / "artifact_manifest.json"
    manifest_files = {name: h for name, h in files.items() if name not in {"artifact_manifest.json", "checksums.sha256"}}
    _write_json(manifest_path, {"schema_version": "1.0", "files": dict(sorted(manifest_files.items()))})
    files["artifact_manifest.json"] = _sha256_file(manifest_path)

    # Write checksums (excludes itself; includes report, manifest, and all payload files)
    checksum_path = out / "checksums.sha256"
    checksum_files = {name: h for name, h in files.items() if name != "checksums.sha256"}
    lines = [f"{h}  {name}\n" for name, h in sorted(checksum_files.items())]
    checksum_path.write_text("".join(lines), encoding="utf-8")
    files["checksums.sha256"] = _sha256_file(checksum_path)

    # Validate expected artifacts
    expected = set(plan.safe_artifact_policy.get("expected_safe_artifacts", []))
    actual = set(files.keys())
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        raise RuntimeError(f"Safe artifact contract violation: missing={sorted(missing)} extra={sorted(extra)}")


def _generate_report(plan: DatasetPlan, decision: DatasetDecision, output_dir: Path) -> str:
    lines = [
        "# INTRA-001B-DATASET-V1 One-Year Dataset Build Report",
        "",
        f"- **Task ID:** {decision.task_id}",
        f"- **Dataset ID:** {decision.dataset_id}",
        f"- **Disposition:** {decision.disposition}",
        f"- **Reason:** {decision.reason}",
        f"- **Branch:** {decision.branch}",
        f"- **Live run head:** {decision.live_run_head}",
        f"- **Pre-registration commit:** {decision.pre_registration_commit}",
        f"- **Starting main SHA:** {decision.starting_main_sha}",
        f"- **Ran at:** {decision.ran_at}",
        "",
        "## Locked data contract",
        "",
        f"- Original strategy spec: `{_repo_relative(plan.original_strategy_spec_path)}` (SHA-256 `{plan.original_strategy_spec_sha256}`)",
        f"- Amendment v3: `{_repo_relative(plan.amendment_v3_path)}` (SHA-256 `{plan.amendment_v3_sha256}`)",
        f"- V4 decision doc: `{_repo_relative(plan.v4_decision_doc_path)}` (SHA-256 `{plan.v4_decision_doc_sha256}`)",
        f"- OHLCV provider: `{plan.provider_roles.get('authoritative_ohlcv_provider')}` feed `{plan.provider_roles.get('authoritative_ohlcv_feed')}`",
        f"- Reference provider: `{plan.provider_roles.get('reference_provider')}` with `{plan.provider_roles.get('reference_provider_status')}`",
        f"- Dataset: `{plan.dataset.get('dataset_start')}` through `{plan.dataset.get('dataset_end')}`",
        f"- Monthly PIT dates: {', '.join(plan.monthly_pit_dates)}",
        "",
        "## Universe",
        "",
        f"- Unique selected stocks: {decision.unique_selected_stock_count}",
        f"- Total stock symbol-months: {decision.total_selected_symbol_month_count}",
        f"- Fixed ETF count: {decision.etf_count}",
        "",
        "### Monthly stock counts",
        "",
    ]
    for m, c in sorted(decision.monthly_stock_counts.items()):
        lines.append(f"- {m}: {c}")
    def _fmt(value: float | None) -> str:
        return "unavailable" if value is None else str(value)

    lines.extend([
        "",
        "## Data quality",
        "",
        f"- Disposition: {decision.data_quality_disposition}",
        f"- Max missing-bar rate: {decision.missing_bar_rate_max_pct}%",
        f"- Max zero-volume rate: {decision.zero_volume_rate_max_pct}%",
        f"- Max duplicate rate: {(_fmt(decision.duplicate_rate_max_pct) + '%') if decision.pre_normalization_metrics_available else 'unavailable (pre-normalization metrics not recovered)'}",
        f"- Pre-normalization metrics available: {decision.pre_normalization_metrics_available}",
        f"- Symbols rejected for data quality: {decision.symbols_rejected_pct}%",
        "",
        "### Monthly rejection summary",
        "",
        "| Month | Total | Invalid | Unverified | Data-quality rejected | Rejected % |",
        "|-------|-------|---------|------------|----------------------|------------|",
    ])
    validation = json.loads((output_dir / "validation_summary.json").read_text(encoding="utf-8"))
    for month, stats in sorted(validation.get("monthly_rejections", {}).items()):
        lines.append(
            f"| {month} | {stats['total_symbols']} | {stats.get('invalid_symbols', 0)} | "
            f"{stats.get('unverified_symbols', 0)} | {stats['data_quality_rejected']} | {stats['rejected_pct']}% |"
        )
    lines.extend([
        "",
        "## Resource usage",
        "",
        f"- Massive HTTP requests: {decision.massive_http_requests}",
        f"- Massive incomplete snapshots: {decision.massive_incomplete_snapshots}",
        f"- Per-phase Alpaca counters available: {decision.per_phase_request_counters_available}",
        f"- Alpaca ranking logical calls: {_fmt(decision.alpaca_ranking_logical_calls)}",
        f"- Alpaca ranking HTTP pages: {_fmt(decision.alpaca_ranking_http_pages)}",
        f"- Alpaca ranking HTTP attempts: {_fmt(decision.alpaca_ranking_http_attempts)}",
        f"- Alpaca ranking HTTP 429s: {_fmt(decision.alpaca_ranking_http_429s)}",
        f"- Alpaca ranking HTTP errors: {_fmt(decision.alpaca_ranking_http_errors)}",
        f"- Alpaca OHLCV logical calls: {_fmt(decision.alpaca_ohlcv_logical_calls)}",
        f"- Alpaca OHLCV HTTP pages: {_fmt(decision.alpaca_ohlcv_http_pages)}",
        f"- Alpaca OHLCV HTTP attempts: {_fmt(decision.alpaca_ohlcv_http_attempts)}",
        f"- Alpaca OHLCV HTTP 429s: {_fmt(decision.alpaca_ohlcv_http_429s)}",
        f"- Alpaca OHLCV HTTP errors: {_fmt(decision.alpaca_ohlcv_http_errors)}",
        f"- HTTP errors (total): {decision.http_errors}",
        f"- HTTP 429s (total): {decision.http_429s}",
        f"- Pagination cycles: {decision.pagination_cycles}",
        f"- Incomplete requests: {decision.incomplete_requests}",
        f"- Original aggregate Alpaca HTTP requests (ranking + OHLCV): {_fmt(decision.alpaca_http_requests)}",
        f"- Runtime (seconds): {_fmt(decision.runtime_seconds)} {f'— {decision.runtime_note}' if decision.runtime_note else ''}".strip(),
        f"- Local storage (bytes): {decision.local_storage_bytes}",
        "",
        "## Ranking methodology",
        "",
        f"- Ranking timeframe: {decision.ranking_timeframe}",
        f"- Ranking parity passed: {decision.ranking_timeframe_parity_passed}",
        f"- Parity fallback used: {decision.parity_fallback_used}",
        "",
        "## Limitations",
        "",
        "- Massive/Polygon does not surface an explicit OTC marker; conservative exclusion is performed through the exchange allowlist and security-type allowlist.",
        "- Duplicate symbols in inactive snapshots are excluded from the active universe.",
        "- The 2025-only dataset is shorter than the original 2022-2025 contract; sample minimums and gates are unchanged.",
        "- Alpaca SIP 1Day volume is a total-liquidity proxy that includes pre-market and after-hours volume; it is not exact regular-session volume. The locked ranking formula uses this proxy.",
        f"- Pre-normalization duplicate/malformed metrics for this bundle: {'available' if decision.pre_normalization_metrics_available else 'unavailable (recomputed from normalized parquet; original 2026-08-08-200945 run normalized before recording)'}. The corrected pipeline now preserves and counts these values before deduplication for future runs.",
        "- The five whole-market ~78-bar discrepancies in the original data_quality.csv were caused by an off-by-one expected-session construction in `_sessions_in_range`: it included the first regular session of the next calendar month when that day was a trading day and then counted 78 bars for that not-yet-open session. The corrected implementation uses session open/close UTC comparisons. Affected months and their extra expected-but-absent sessions: March 2025 = 2025-04-01; April 2025 = 2025-05-01; June 2025 = 2025-07-01; July 2025 = 2025-08-01; September 2025 = 2025-10-01.",
        "",
        "## Next step",
        "",
        f"`{decision.next_assignment}` — build the research engine and run development/validation/holdout evaluation under a separate, explicitly approved PR.",
        "",
        "---",
        "This report is a research artifact only. It does not authorize production changes.",
    ])
    return "\n".join(lines) + "\n"
