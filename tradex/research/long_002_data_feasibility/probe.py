"""LONG-002B bounded provider-probe orchestrator.

Each data family is evaluated against the locked `minimum_usable_contract`
from the preregistered probe spec. A family is promoted only when the
recorded evidence satisfies every required boolean; otherwise it is
downgraded to `not_supported` with its unmet minimums listed as blockers.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .clients import (
    BudgetError,
    Long002AlpacaClient,
    Long002EdgarClient,
    Long002MassiveClient,
    Long002ProviderAuthError,
    Long002ProviderEntitlementError,
    Long002ProviderResponseError,
    Long002ProviderTransientError,
    Long002ProviderUnsupportedError,
    RequestBudget,
    resolve_credentials,
)
from .evaluator import FamilyEvidence, evaluate_family, evaluate_overall
from .models import DataFamilyResult, FeasibilityReport, ProviderRequestRecord
from .spec import load_probe_spec, sha256_of_file


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, Long002ProviderAuthError):
        return "authentication"
    if isinstance(exc, Long002ProviderEntitlementError):
        return "entitlement"
    if isinstance(exc, Long002ProviderUnsupportedError):
        return "unsupported_capability"
    if isinstance(exc, Long002ProviderTransientError):
        return "transient"
    if isinstance(exc, Long002ProviderResponseError):
        return "response"
    return "unknown"


def _classify_http_status(status: int | None) -> str:
    if status is None:
        return "network_error"
    if status == 200:
        return "none"
    if status == 401:
        return "authentication"
    if status == 403:
        return "entitlement"
    if status == 404:
        return "response"
    if status == 429:
        return "http_429"
    if status >= 500:
        return "response"
    return f"http_{status}"


def _record(
    family: str,
    provider: str,
    symbol: str | None,
    as_of_date: str | None,
    endpoint_pattern: str,
    status: int | None,
    error: str,
    retry: int,
    summary: dict[str, Any],
    provenance: dict[str, Any],
) -> ProviderRequestRecord:
    return ProviderRequestRecord(
        family=family,
        provider=provider,
        symbol=symbol,
        as_of_date=as_of_date,
        endpoint_pattern=endpoint_pattern,
        http_status=status,
        error_classification=error,
        retry_count=retry,
        request_timestamp_utc=_now_utc(),
        response_summary=summary,
        provenance=provenance,
    )


def _safe_bar_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Return a safe summary for a daily-bar response without raw OHLCV."""
    bars = summary.get("bars", [])
    safe: dict[str, Any] = {
        "provider": summary.get("provider"),
        "symbol": summary.get("symbol") or summary.get("ticker"),
        "http_status": summary.get("http_status") or summary.get("status"),
        "error": summary.get("error"),
        "error_classification": summary.get("error_classification"),
        "bar_count": summary.get("bar_count", summary.get("results_count", len(bars))),
        "page_count": summary.get("page_count"),
        "pagination_complete": summary.get("pagination_complete"),
        "feed": summary.get("feed"),
        "adjustment": summary.get("adjustment") if "adjustment" in summary else summary.get("adjusted"),
        "retry_count": summary.get("retry_count", 0),
    }
    if bars:
        safe["first_bar_timestamp"] = bars[0].get("t") if isinstance(bars[0], dict) else None
        safe["last_bar_timestamp"] = bars[-1].get("t") if isinstance(bars[-1], dict) else None
        safe["bar_payload_sha256"] = hashlib.sha256(
            json.dumps(bars, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    return safe


def _safe_identity_summary(detail: dict[str, Any]) -> dict[str, Any]:
    """Return a safe summary for a per-ticker identity lookup."""
    row = detail.get("row") or {}
    safe = {
        "provider": detail.get("provider"),
        "ticker": detail.get("ticker"),
        "pit_date": detail.get("pit_date"),
        "http_status": detail.get("status"),
        "error": detail.get("error"),
        "type": detail.get("type") or row.get("type"),
        "primary_exchange": detail.get("primary_exchange") or row.get("primary_exchange"),
        "cik": detail.get("cik") or row.get("cik"),
        "active": row.get("active") if isinstance(row, dict) else None,
        "row_found": bool(row),
    }
    if row:
        safe["row_sha256"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    return safe


def _safe_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    """Return a safe summary for split/dividend event endpoints."""
    return {
        "provider": event.get("provider"),
        "ticker": event.get("ticker"),
        "event_type": event.get("event_type"),
        "http_status": event.get("status"),
        "error": event.get("error"),
        "event_count": event.get("event_count", 0),
    }


def _bar_dataframe(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize a raw bar payload to a UTC-indexed DataFrame."""
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(bars)
    df = df.rename(columns={"t": "datetime", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    df = df.dropna(subset=["datetime"]).set_index("datetime").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    return df


def _validate_bar(bar: dict[str, Any]) -> tuple[bool, str]:
    """Check a single raw bar for malformed OHLCV."""
    ts = bar.get("t")
    if not isinstance(ts, (str, int)):
        return False, "missing_timestamp"
    try:
        if isinstance(ts, int):
            pd.to_datetime(ts, unit="ms", utc=True)
        else:
            pd.to_datetime(ts, utc=True)
    except Exception:  # noqa: BLE001
        return False, "unparseable_timestamp"
    for key in ("o", "h", "l", "c", "v"):
        val = bar.get(key)
        if val is None:
            return False, f"missing_{key}"
        try:
            num = float(val)
        except (TypeError, ValueError):
            return False, f"non_numeric_{key}"
        if not math.isfinite(num):
            return False, f"non_finite_{key}"
    o = float(bar["o"])
    h = float(bar["h"])
    l = float(bar["l"])
    c = float(bar["c"])
    v = float(bar["v"])
    if h < l or c < l or c > h or o < l or o > h:
        return False, "structural_ohlcv_violation"
    if v < 0:
        return False, "negative_volume"
    return True, "ok"


def _expected_xnys_session_dates(start_date: str, end_date: str) -> set[datetime]:
    """Return the set of XNYS session dates in a date range (inclusive)."""
    try:
        import exchange_calendars as xc
    except ImportError:  # pragma: no cover - covered by environment
        return set()
    cal = xc.get_calendar("XNYS")
    sessions = cal.sessions_in_range(start_date, end_date)
    return set(sessions.date) if hasattr(sessions, "date") else set(sessions.to_series().dt.date)


def _trailing_sessions(last_date: datetime, n: int = 252) -> set[datetime]:
    """Return the last n XNYS sessions ending on last_date."""
    try:
        import exchange_calendars as xc
    except ImportError:  # pragma: no cover
        return set()
    cal = xc.get_calendar("XNYS")
    start = (last_date - timedelta(days=int(n * 1.8))).strftime("%Y-%m-%d")
    end = last_date.strftime("%Y-%m-%d")
    sessions = cal.sessions_in_range(start, end)
    if sessions.empty:
        return set()
    dates = list(sessions.date if hasattr(sessions, "date") else sessions.to_series().dt.date)
    return set(dates[-n:])


def _bar_dates(bars: list[dict[str, Any]]) -> set[datetime]:
    """Extract the set of UTC bar dates."""
    dates: set[datetime] = set()
    for bar in bars:
        ts = bar.get("t")
        if not ts:
            continue
        try:
            dt = pd.to_datetime(ts, unit="ms" if isinstance(ts, int) else None, utc=True).date()
        except Exception:  # noqa: BLE001, S112
            continue
        dates.add(dt)
    return dates


def _compute_bar_quality(
    bars: list[dict[str, Any]],
    full_start: str,
    full_end: str,
    *,
    dev_start: str = "2020-01-01",
    dev_end: str = "2020-12-31",
) -> dict[str, Any]:
    """Compute completeness, duplicate, malformed, and zero-volume metrics."""
    malformed = 0
    malformed_reasons: dict[str, int] = {}
    for bar in bars:
        ok, reason = _validate_bar(bar)
        if not ok:
            malformed += 1
            malformed_reasons[reason] = malformed_reasons.get(reason, 0) + 1

    df = _bar_dataframe(bars)
    duplicate_count = int(df.index.duplicated().sum())
    zero_volume_count = int((df["volume"] == 0).sum()) if not df.empty and "volume" in df.columns else 0

    bar_dates = _bar_dates(bars)
    dev_expected = _expected_xnys_session_dates(dev_start, dev_end)
    dev_actual = {d for d in bar_dates if dev_start <= str(d) <= dev_end}
    dev_missing = len(dev_expected - dev_actual) if dev_expected else 0
    dev_completeness = 1.0 - (dev_missing / len(dev_expected)) if dev_expected else 1.0

    prior_bars = [b for b in bars if _bar_date(b) and str(_bar_date(b)) < dev_start]
    prior_count = len(prior_bars)

    all_expected = _expected_xnys_session_dates(full_start, full_end)
    all_actual = {d for d in bar_dates if full_start <= str(d) <= full_end}
    all_missing = len(all_expected - all_actual) if all_expected else 0
    all_completeness = 1.0 - (all_missing / len(all_expected)) if all_expected else 1.0

    trailing_completeness = 0.0
    if not df.empty:
        last_date = df.index[-1].to_pydatetime()
        trailing_expected = _trailing_sessions(last_date, n=252)
        trailing_actual = {d for d in bar_dates if d in trailing_expected}
        if trailing_expected:
            trailing_completeness = len(trailing_actual) / len(trailing_expected)

    return {
        "total_bars": len(bars),
        "malformed_count": malformed,
        "malformed_reasons": malformed_reasons,
        "duplicate_count": duplicate_count,
        "zero_volume_count": zero_volume_count,
        "dev_expected_sessions": len(dev_expected),
        "dev_actual_sessions": len(dev_actual),
        "dev_completeness": round(dev_completeness, 4),
        "prior_bars": prior_count,
        "all_expected_sessions": len(all_expected),
        "all_actual_sessions": len(all_actual),
        "all_completeness": round(all_completeness, 4),
        "trailing_completeness": round(trailing_completeness, 4),
    }


def _bar_date(bar: dict[str, Any]) -> datetime | None:
    ts = bar.get("t")
    if not ts:
        return None
    try:
        if isinstance(ts, int):
            return pd.to_datetime(ts, unit="ms", utc=True).date()
        return pd.to_datetime(ts, utc=True).date()
    except Exception:  # noqa: BLE001
        return None


def _lookup_close_on_or_before(df: pd.DataFrame, target_date_str: str, max_lookback_days: int = 5) -> float | None:
    """Return the close for the PIT decision date, rejecting materially stale bars.

    The target is treated as end-of-day on `target_date_str` so a daily bar whose
    session timestamp falls on that calendar day is included. If the most recent
    bar on or before the target is older than `max_lookback_days`, it is not a
    valid PIT close for the decision date and `None` is returned.
    """
    if df.empty:
        return None
    target_eod = pd.Timestamp(target_date_str, tz="UTC") + pd.Timedelta(hours=23, minutes=59, seconds=59)
    subset = df[df.index <= target_eod]
    if subset.empty:
        return None
    latest = subset.index[-1]
    lookback = pd.Timestamp(target_date_str, tz="UTC") - pd.Timedelta(days=max_lookback_days)
    if latest < lookback:
        return None
    return float(subset["close"].iloc[-1])


def _extract_acceptance_datetime_for_accn(submissions: dict[str, Any], accn: str) -> str | None:
    """Match an accession number to its SEC acceptance timestamp."""
    if not isinstance(submissions, dict):
        return None
    recent = submissions.get("filings", {}).get("recent", {})
    accns = recent.get("accessionNumber", [])
    try:
        idx = accns.index(accn)
    except ValueError:
        return None
    times = recent.get("acceptanceDateTime", [])
    if idx < len(times):
        return times[idx]
    return None


def _extract_filed_shares_fact(
    facts: dict[str, Any],
    as_of: str = "2020-12-31",
    submissions: dict[str, Any] | None = None,
    *,
    require_acceptance: bool = True,
) -> dict[str, Any] | None:
    """Return the most recent PIT shares fact that is available by `as_of`.

    A shares fact is only considered PIT-available when:
      - the reporting period `end` is on or before `as_of`;
      - the SEC `filed` date is on or before `as_of`; and
      - the matched `acceptanceDateTime` for the fact's accession number is on
        or before `as_of` (when `require_acceptance` is True).

    This prevents pairing a future-released shares figure (e.g. filed in January
    for a December period end) with a stale historical close.
    """
    if not isinstance(facts, dict):
        return None
    # Acceptance time is an instant; a fact accepted at any point on the as_of
    # calendar day is available by end of that day.
    as_of_eod = pd.Timestamp(as_of, tz="UTC") + pd.Timedelta(hours=23, minutes=59, seconds=59)
    concepts = ("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding")
    best: dict[str, Any] | None = None
    for concept in concepts:
        concept_data = facts.get("facts", {}).get("dei", {}).get(concept) if concept == "EntityCommonStockSharesOutstanding" else None
        if concept_data is None and concept == "CommonStockSharesOutstanding":
            concept_data = facts.get("facts", {}).get("us-gaap", {}).get(concept)
        if not concept_data:
            continue
        units = concept_data.get("units", {})
        for unit, entries in units.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                end = entry.get("end")
                val = entry.get("val")
                filed = entry.get("filed")
                accn = entry.get("accn")
                if not end or not filed:
                    continue
                if str(end) > as_of or str(filed) > as_of:
                    continue
                if not isinstance(val, (int, float)) or val <= 0:
                    continue
                if require_acceptance:
                    acc_time = _extract_acceptance_datetime_for_accn(submissions or {}, accn)
                    if not acc_time:
                        continue
                    if pd.Timestamp(acc_time, tz="UTC") > as_of_eod:
                        continue
                if best is None or str(end) > str(best["end"]) or (str(end) == str(best["end"]) and str(filed) > str(best["filed"])):
                    best = {
                        "concept": concept,
                        "unit": unit,
                        "end": end,
                        "filed": filed,
                        "accn": accn,
                        "value": val,
                    }
    return best


def _fundamentals_have_filed_facts(facts: dict[str, Any]) -> bool:
    """Return True if any fact has a filed timestamp."""
    if not isinstance(facts, dict):
        return False
    for taxonomy in ("us-gaap", "dei", "ifrs"):
        for concept_data in facts.get("facts", {}).get(taxonomy, {}).values():
            if not isinstance(concept_data, dict):
                continue
            for entries in concept_data.get("units", {}).values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("filed"):
                        return True
    return False


def _probe_daily_market_data(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe daily market data with full-year range and integrity checks."""
    result = DataFamilyResult(family="daily_market_data")
    evidence = FamilyEvidence(family="daily_market_data")

    # Focus the history probe on a few representative active names.
    priority = {"AAPL", "GOOGL", "FDX"}
    probe_symbols = [i for i in panel if i["identifier"] in priority] or panel[:3]

    full_start = "2015-01-01"
    full_end = "2020-12-31"
    dev_start = "2020-01-01"
    dev_end = "2020-12-31"

    any_attempted = False
    massive_attempted = False
    selected = None
    role: str | None = None
    raw_bars: dict[str, list[dict[str, Any]]] = {}

    for provider in providers:
        if provider == "massive/polygon":
            if not creds.get("massive_api_key"):
                result.records.append(_record(
                    "daily_market_data", "massive/polygon", None, None,
                    "v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}", None, "authentication", 0,
                    {"reason": "Missing MASSIVE_API_KEY"}, {"provider": "massive/polygon"},
                ))
                evidence.notes.append("Massive/Polygon credentials missing; daily bars not attempted.")
                continue
            client = Long002MassiveClient(
                str(creds["massive_api_key"]),
                budget=budget,
                request_func=test_inject.get("massive_request_func") if test_inject else None,
                min_interval_seconds=0.0 if test_inject else None,
            )
            massive_attempted = True
            for item in probe_symbols:
                symbol = item["identifier"]
                raw = client.fetch_daily_bars(symbol, full_start, full_end, adjusted=False)
                any_attempted = True
                raw_error = "none" if raw.get("status") == 200 and not raw.get("error") else _classify_http_status(raw.get("status"))
                result.records.append(_record(
                    "daily_market_data", "massive/polygon", symbol, None,
                    "v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
                    raw.get("status"), raw_error,
                    0, _safe_bar_summary(raw), {"adjusted": False},
                ))
                if raw_error in ("authentication", "entitlement"):
                    evidence.notes.append(f"Massive/Polygon daily bars for {symbol}: {raw.get('error') or raw.get('status')} ({raw_error}); stopping preferred-provider exercise.")
                    break
                if raw.get("status") != 200 or raw.get("error") or not raw.get("bars"):
                    evidence.notes.append(f"Massive/Polygon daily bars for {symbol}: {raw.get('error') or raw.get('status')}")
                    continue
                evidence.flags["explicit_raw_as_traded_policy"] = True
                quality = _compute_bar_quality(raw["bars"], full_start, full_end, dev_start=dev_start, dev_end=dev_end)
                if quality["dev_completeness"] >= 0.99 and quality["prior_bars"] > 0:
                    evidence.flags["one_complete_dev_year_plus_prior_history"] = True
                if quality["trailing_completeness"] >= 0.99:
                    evidence.flags["daily_bar_integrity_compatible_with_99pct_trailing_year"] = True
                evidence.flags["no_unresolved_duplicates"] = quality["duplicate_count"] == 0
                evidence.flags["no_unresolved_malformed_rows"] = quality["malformed_count"] == 0
                evidence.notes.append(f"Massive/Polygon {symbol} bar quality: {quality}")

                # Demonstrate split-adjusted policy by making a second request.
                adj = client.fetch_daily_bars(symbol, full_start, full_end, adjusted=True)
                result.records.append(_record(
                    "daily_market_data", "massive/polygon", symbol, None,
                    "v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
                    adj.get("status"), "none" if adj.get("status") == 200 and not adj.get("error") else _classify_http_status(adj.get("status")),
                    0, _safe_bar_summary(adj), {"adjusted": True},
                ))
                if adj.get("status") == 200 and not adj.get("error"):
                    evidence.flags["explicit_split_adjusted_policy"] = True
                    if len(raw.get("bars", [])) != len(adj.get("bars", [])):
                        evidence.notes.append(f"Massive/Polygon {symbol}: raw and adjusted bar counts differ ({len(raw.get('bars',[]))} vs {len(adj.get('bars',[]))}).")

                # Demonstrate split/dividend provenance for this symbol.
                splits = client.fetch_splits(symbol)
                result.records.append(_record(
                    "daily_market_data", "massive/polygon", symbol, None,
                    "/v3/reference/splits?ticker={ticker}",
                    splits.get("status"), "none" if splits.get("status") == 200 else _classify_http_status(splits.get("status")),
                    0, _safe_event_summary(splits), {"event_type": "split"},
                ))
                dividends = client.fetch_dividends(symbol)
                result.records.append(_record(
                    "daily_market_data", "massive/polygon", symbol, None,
                    "/v3/reference/dividends?ticker={ticker}",
                    dividends.get("status"), "none" if dividends.get("status") == 200 else _classify_http_status(dividends.get("status")),
                    0, _safe_event_summary(dividends), {"event_type": "dividend"},
                ))
                if splits.get("status") == 200 or dividends.get("status") == 200:
                    evidence.flags["reconstructable_split_handling"] = (
                        splits.get("event_count", 0) > 0 or dividends.get("event_count", 0) > 0
                    )
                raw_bars[symbol.upper()] = raw["bars"]
                selected = "massive/polygon"
                role = "primary"
                break
            if selected:
                break

        if provider == "alpaca":
            if not creds.get("alpaca_api_key") or not creds.get("alpaca_secret_key"):
                result.records.append(_record(
                    "daily_market_data", "alpaca", None, None,
                    "/v2/stocks/{symbol}/bars", None, "authentication", 0,
                    {"reason": "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY"}, {"provider": "alpaca"},
                ))
                evidence.notes.append("Alpaca credentials missing; daily bars not attempted.")
                continue
            client = Long002AlpacaClient(
                str(creds["alpaca_api_key"]),
                str(creds["alpaca_secret_key"]),
                budget=budget,
                request_func=test_inject.get("alpaca_request_func") if test_inject else None,
                request_delay_seconds=0.5,
                max_retries=1,
            )
            for item in probe_symbols:
                symbol = item["identifier"]
                raw = client.fetch_daily_bars(
                    symbol,
                    f"{full_start}T00:00:00Z",
                    f"{full_end}T23:59:59Z",
                    feed="sip",
                    adjustment="raw",
                )
                any_attempted = True
                result.records.append(_record(
                    "daily_market_data", "alpaca", symbol, None,
                    "/v2/stocks/{symbol}/bars",
                    raw.get("http_status"),
                    raw.get("error_classification", "none") if raw.get("http_status") == 200 else _classify_http_status(raw.get("http_status")),
                    raw.get("retry_count", 0), _safe_bar_summary(raw), {"feed": "sip", "adjustment": "raw"},
                ))
                if raw.get("http_status") != 200 or not raw.get("bars"):
                    evidence.notes.append(f"Alpaca daily bars for {symbol}: {raw.get('error_classification')} {raw.get('http_status')}")
                    continue
                evidence.flags["explicit_raw_as_traded_policy"] = True
                quality = _compute_bar_quality(raw["bars"], full_start, full_end, dev_start=dev_start, dev_end=dev_end)
                if quality["dev_completeness"] >= 0.99 and quality["prior_bars"] > 0:
                    evidence.flags["one_complete_dev_year_plus_prior_history"] = True
                if quality["trailing_completeness"] >= 0.99:
                    evidence.flags["daily_bar_integrity_compatible_with_99pct_trailing_year"] = True
                evidence.flags["no_unresolved_duplicates"] = quality["duplicate_count"] == 0
                evidence.flags["no_unresolved_malformed_rows"] = quality["malformed_count"] == 0
                first_bar = _bar_date(raw["bars"][0]) if raw.get("bars") else None
                last_bar = _bar_date(raw["bars"][-1]) if raw.get("bars") else None
                evidence.notes.append(
                    f"Alpaca {symbol}: {quality['total_bars']} bars ({first_bar} to {last_bar}); "
                    f"development year {quality['dev_actual_sessions']}/{quality['dev_expected_sessions']} "
                    f"({quality['dev_completeness']:.2%}); all-window {quality['all_actual_sessions']}/"
                    f"{quality['all_expected_sessions']} ({quality['all_completeness']:.2%}, 2015 warmup sessions absent); "
                    f"trailing year {quality['trailing_completeness']:.2%}; duplicates={quality['duplicate_count']}, malformed={quality['malformed_count']}."
                )

                adj = client.fetch_daily_bars(
                    symbol,
                    f"{full_start}T00:00:00Z",
                    f"{full_end}T23:59:59Z",
                    feed="sip",
                    adjustment="split",
                )
                result.records.append(_record(
                    "daily_market_data", "alpaca", symbol, None,
                    "/v2/stocks/{symbol}/bars",
                    adj.get("http_status"),
                    adj.get("error_classification", "none") if adj.get("http_status") == 200 else _classify_http_status(adj.get("http_status")),
                    adj.get("retry_count", 0), _safe_bar_summary(adj), {"feed": "sip", "adjustment": "split"},
                ))
                if adj.get("http_status") == 200 and not adj.get("error"):
                    evidence.flags["explicit_split_adjusted_policy"] = True
                    if len(raw.get("bars", [])) != len(adj.get("bars", [])):
                        evidence.notes.append(f"Alpaca {symbol}: raw and split-adjusted bar counts differ.")

                # Try to prove split/dividend provenance through Massive even when
                # Alpaca is the fallback OHLCV source.
                if creds.get("massive_api_key"):
                    mc = Long002MassiveClient(
                        str(creds["massive_api_key"]),
                        budget=budget,
                        request_func=test_inject.get("massive_request_func") if test_inject else None,
                        min_interval_seconds=0.0 if test_inject else None,
                    )
                    splits = mc.fetch_splits(symbol)
                    result.records.append(_record(
                        "daily_market_data", "massive/polygon", symbol, None,
                        "/v3/reference/splits?ticker={ticker}",
                        splits.get("status"), "none" if splits.get("status") == 200 else _classify_http_status(splits.get("status")),
                        0, _safe_event_summary(splits), {"event_type": "split"},
                    ))
                    dividends = mc.fetch_dividends(symbol)
                    result.records.append(_record(
                        "daily_market_data", "massive/polygon", symbol, None,
                        "/v3/reference/dividends?ticker={ticker}",
                        dividends.get("status"), "none" if dividends.get("status") == 200 else _classify_http_status(dividends.get("status")),
                        0, _safe_event_summary(dividends), {"event_type": "dividend"},
                    ))
                    if splits.get("status") == 200 or dividends.get("status") == 200:
                        evidence.flags["reconstructable_split_handling"] = (
                            splits.get("event_count", 0) > 0 or dividends.get("event_count", 0) > 0
                        )

                raw_bars[symbol.upper()] = raw["bars"]
                selected = "alpaca"
                role = "fallback" if massive_attempted else "primary"
                break
            if selected:
                break

        if provider == "schwab":
            result.records.append(_record(
                "daily_market_data", "schwab", None, None,
                "Schwab priceHistory", None, "unsupported_capability", 0,
                {"reason": "Schwab OAuth token not configured in this environment"}, {"provider": "schwab"},
            ))

    result.provider_selected = selected
    result.provider_role = role
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted, raw_bars


def _resolve_identity(
    client: Long002MassiveClient,
    symbol: str,
    dates: list[str],
    result: DataFamilyResult,
) -> dict[str, Any] | None:
    """Try each PIT date (active then inactive) and return the best identity row.

    A "best" row is one that has both a populated security type and exchange. We
    intentionally do not claim lifecycle coverage or classification from a
    single returned row; those flags are evaluated separately in
    `_probe_security_master` using the full set of attempts recorded here.
    """
    best: dict[str, Any] | None = None
    for date in dates:
        for active in (True, False):
            detail = client.fetch_ticker_detail(symbol, date, active=active)
            result.records.append(_record(
                "security_master_and_corporate_actions", "massive", symbol, date,
                f"/v3/reference/tickers?ticker={{ticker}}&date={{date}}&active={active}",
                detail.get("status"), "none" if detail.get("status") == 200 and detail.get("row") else _classify_http_status(detail.get("status")),
                0, _safe_identity_summary(detail), {"active_filter": active},
            ))
            if detail.get("status") == 200 and detail.get("row"):
                candidate = {
                    "cik": detail.get("cik"),
                    "type": detail.get("type"),
                    "primary_exchange": detail.get("primary_exchange"),
                    "active": active,
                    "pit_date": date,
                    "row": detail.get("row"),
                }
                if candidate["type"] and candidate["primary_exchange"]:
                    return candidate
                if best is None or (not best.get("type") and candidate.get("type")):
                    best = candidate
    return best


def _probe_security_master(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe per-ticker PIT identity and corporate-action provenance."""
    result = DataFamilyResult(family="security_master_and_corporate_actions")
    evidence = FamilyEvidence(family="security_master_and_corporate_actions")
    any_attempted = False
    identities: dict[str, dict[str, Any]] = {}
    selected = None
    role = None

    for provider in providers:
        if provider == "massive":
            if not creds.get("massive_api_key"):
                result.records.append(_record(
                    "security_master_and_corporate_actions", "massive", None, None,
                    "/v3/reference/tickers?ticker={ticker}&date={date}", None, "authentication", 0,
                    {"reason": "Missing MASSIVE_API_KEY"}, {"provider": "massive"},
                ))
                continue
            client = Long002MassiveClient(
                str(creds["massive_api_key"]),
                budget=budget,
                request_func=test_inject.get("massive_request_func") if test_inject else None,
                min_interval_seconds=0.0 if test_inject else None,
            )
            all_found = True
            for item in panel:
                any_attempted = True
                identity = _resolve_identity(client, item["identifier"], item["as_of_dates"], result)
                if identity:
                    identities[item["identifier"]] = identity
                else:
                    all_found = False

            # Lifecycle coverage requires, for every panel symbol, either an
            # inactive (`active=false`) returned row or at least two distinct PIT
            # dates with returned rows sharing the same ticker/CIK. The current
            # bounded probe does not demonstrate this for the full panel, so the
            # flag is set conservatively.
            lifecycle_rows_per_symbol: dict[str, set[str]] = {}
            inactive_row_found_per_symbol: dict[str, bool] = {}
            for r in result.records:
                if r.family != "security_master_and_corporate_actions" or r.provider != "massive":
                    continue
                summary = r.response_summary or {}
                if not summary.get("row_found"):
                    continue
                sym = r.symbol or summary.get("ticker")
                if not sym:
                    continue
                if summary.get("active") is False:
                    inactive_row_found_per_symbol[sym] = True
                date = r.as_of_date or summary.get("pit_date")
                if date:
                    lifecycle_rows_per_symbol.setdefault(sym, set()).add(date)

            lifecycle_coverage_for_all = all_found and all(
                inactive_row_found_per_symbol.get(s)
                or len(lifecycle_rows_per_symbol.get(s, set())) >= 2
                for s in identities
            )

            # Massive's `type` values (e.g. `CS`, `INDEX`) are not a defensible
            # mapping to the locked exclusion categories (ETF, preferred ETF,
            # closed-end fund, pre-merger SPAC). The panel contains symbols whose
            # returned `type` does not match the intended category (SPY/PFF as
            # `INDEX`, IGR as `CS`, IPOD as `CS`), so this minimum is not satisfied
            # from a single PIT row per symbol.
            defensible_exclusion_classification = False

            evidence.flags["stable_identity_effective_ticker_join_for_probe_panel"] = all_found and lifecycle_coverage_for_all
            evidence.flags["security_type_and_exchange_for_probe_panel"] = all_found and defensible_exclusion_classification

            if not lifecycle_coverage_for_all:
                evidence.notes.append(
                    "Massive per-ticker lookups did not demonstrate active/inactive lifecycle coverage or ticker-change evidence for every panel symbol; stable identity join flag not satisfied."
                )
            if not defensible_exclusion_classification:
                evidence.notes.append(
                    "Massive `type` values (CS/INDEX) do not provide a defensible mapping to the locked exclusion categories; security type and exchange flag not satisfied."
                )

            # Demonstrate split/dividend provenance for AAPL and GOOGL.
            split_count = 0
            dividend_count = 0
            for sym in ("AAPL", "GOOGL"):
                splits = client.fetch_splits(sym)
                any_attempted = True
                result.records.append(_record(
                    "security_master_and_corporate_actions", "massive", sym, None,
                    "/v3/reference/splits?ticker={ticker}",
                    splits.get("status"), "none" if splits.get("status") == 200 else _classify_http_status(splits.get("status")),
                    0, _safe_event_summary(splits), {"event_type": "split"},
                ))
                if splits.get("status") == 200:
                    split_count += splits.get("event_count", 0)
                dividends = client.fetch_dividends(sym)
                result.records.append(_record(
                    "security_master_and_corporate_actions", "massive", sym, None,
                    "/v3/reference/dividends?ticker={ticker}",
                    dividends.get("status"), "none" if dividends.get("status") == 200 else _classify_http_status(dividends.get("status")),
                    0, _safe_event_summary(dividends), {"event_type": "dividend"},
                ))
                if dividends.get("status") == 200:
                    dividend_count += dividends.get("event_count", 0)
            evidence.flags["corporate_action_provenance_for_splits_and_dividends"] = split_count > 0 and dividend_count > 0

            if all_found:
                selected = "massive"
                role = "primary"
            elif any_attempted:
                selected = "massive"
                role = "partial"
            context["symbol_to_cik"] = {s: str(v["cik"]).strip().lstrip("0") or "0" for s, v in identities.items() if v.get("cik")}
            context["identities"] = identities
            break

        if provider == "alpaca":
            result.records.append(_record(
                "security_master_and_corporate_actions", "alpaca", None, None,
                "assets", None, "unsupported_capability", 0,
                {"reason": "Alpaca security master endpoints not exercised in this probe"}, {"provider": "alpaca"},
            ))
        if provider == "sec_edgar":
            result.records.append(_record(
                "security_master_and_corporate_actions", "sec_edgar", None, None,
                "submissions metadata", None, "unsupported_capability", 0,
                {"reason": "EDGAR security master queried only via fundamentals family"}, {"provider": "sec_edgar"},
            ))

    result.provider_selected = selected
    result.provider_role = role
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted


def _probe_fundamentals(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe EDGAR submissions and company facts for PIT shares pathway."""
    result = DataFamilyResult(family="issuer_fundamentals_and_shares")
    evidence = FamilyEvidence(family="issuer_fundamentals_and_shares")
    any_attempted = False
    selected = None
    role = None

    for provider in providers:
        if provider == "sec_edgar":
            client = Long002EdgarClient(
                budget=budget,
                request_func=test_inject.get("edgar_request_func") if test_inject else None,
            )
            symbol_to_cik: dict[str, str] = {}
            if test_inject:
                symbol_to_cik.update(test_inject.get("symbol_to_cik", {}))
            symbol_to_cik.update(context.get("symbol_to_cik", {}))

            # Choose up to three probe issuers with resolved CIKs.
            panel_symbols = {i["identifier"].upper() for i in panel}
            probe_symbols = [s for s in symbol_to_cik if s.upper() in panel_symbols][:3]
            if not probe_symbols:
                probe_symbols = [i["identifier"] for i in panel[:3]]

            resolved_count = 0
            pit_pathway_found = False
            market_cap_computed = False
            # The PIT decision timestamp for this bounded probe is end-of-day on the
            # latest development-period date for which daily bars are available.
            decision_date = "2020-12-31"
            for symbol in probe_symbols:
                cik = symbol_to_cik.get(symbol.upper())
                if not cik:
                    result.records.append(_record(
                        "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                        "submissions/CIK{cik}.json", None, "unknown", 0,
                        {"reason": "CIK not resolved for symbol"}, {"provider": "sec_edgar"},
                    ))
                    continue
                try:
                    submissions = client.fetch_submissions(cik)
                except BudgetError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    result.records.append(_record(
                        "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                        "submissions/CIK{cik}.json", None, _classify_error(exc), 0,
                        {}, {"cik": cik, "exception": str(exc)},
                    ))
                    continue
                any_attempted = True
                result.records.append(_record(
                    "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                    "submissions/CIK{cik}.json", 200 if submissions else None,
                    "none" if submissions else "response", 0,
                    {"submissions_present": bool(submissions), "cik": cik},
                    {"cik": cik},
                ))

                try:
                    facts = client.fetch_company_facts(cik)
                except BudgetError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    result.records.append(_record(
                        "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                        "api/xbrl/companyfacts/CIK{cik}.json", None, _classify_error(exc), 0,
                        {}, {"cik": cik, "exception": str(exc)},
                    ))
                    continue
                result.records.append(_record(
                    "issuer_fundamentals_and_shares", "sec_edgar", symbol, None,
                    "api/xbrl/companyfacts/CIK{cik}.json", 200 if facts else None,
                    "none" if facts else "response", 0,
                    {"facts_present": bool(facts), "cik": cik},
                    {"cik": cik},
                ))

                resolved_count += 1

                # Attempt a PIT market-cap pathway for this issuer. The selected
                # shares fact must be available on or before the decision date,
                # its acceptance timestamp must be on or before the decision date,
                # and the close must be the decision-date (or most recent prior)
                # bar -- not a future-filed fact paired with a stale close.
                shares = _extract_filed_shares_fact(facts, as_of=decision_date, submissions=submissions)
                if shares and symbol.upper() in context.get("daily_bars", {}):
                    close = _lookup_close_on_or_before(
                        _bar_dataframe(context["daily_bars"][symbol.upper()]),
                        decision_date,
                    )
                    if close and shares["value"] and close > 0:
                        market_cap = close * shares["value"]
                        market_cap_computed = True
                        pit_pathway_found = True
                        evidence.notes.append(
                            f"{symbol} market-cap pathway: close={close}, shares={shares['value']}, "
                            f"mcap={market_cap:.2f}, end={shares['end']}, filed={shares.get('filed')}, "
                            f"decision_date={decision_date}"
                        )
                        acc_time = _extract_acceptance_datetime_for_accn(submissions, shares["accn"])
                        if acc_time:
                            evidence.notes.append(
                                f"{symbol} accession {shares['accn']} acceptance timestamp: {acc_time}"
                            )

            evidence.flags["ciK_identity_for_probe_issuers"] = resolved_count == len(probe_symbols) and resolved_count > 0
            # Both PIT flags are set together from one demonstrably PIT-valid
            # shares+close pathway. A generic acceptance timestamp or filed fact
            # without a matched, decision-date-valid shares figure is insufficient.
            evidence.flags["filing_acceptance_time_controls_availability"] = pit_pathway_found
            evidence.flags["viable_non_index_market_cap_pathway"] = market_cap_computed
            evidence.flags["missing_facts_remain_null"] = True  # No fabricated placeholders are inserted.
            selected = "sec_edgar"
            role = "primary"
            break

        if provider == "massive":
            result.records.append(_record(
                "issuer_fundamentals_and_shares", "massive", None, None,
                "financial endpoints", None, "unsupported_capability", 0,
                {"reason": "Massive financial endpoints not exercised"}, {"provider": "massive"},
            ))
        if provider == "yahoo":
            result.records.append(_record(
                "issuer_fundamentals_and_shares", "yahoo", None, None,
                "finance quote/history", None, "unsupported_capability", 0,
                {"reason": "Yahoo used only as diagnostic, not PIT facts"}, {"provider": "yahoo"},
            ))

    result.provider_selected = selected
    result.provider_role = role
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted


def _probe_earnings(
    providers: list[str],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    min_contract: dict[str, Any],
    test_inject: dict[str, Any] | None,
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Probe earnings-event timing; no provider in the budget satisfies the min contract."""
    result = DataFamilyResult(family="earnings_event_timing")
    evidence = FamilyEvidence(family="earnings_event_timing")
    any_attempted = False
    selected = None

    # No live provider calls are made for earnings-event timing. The
    # preregistered candidates are documented as unverified capabilities rather
    # than attempted provider failures, so `any_attempted` stays `False`.
    evidence.notes.append(
        "No live provider calls made for earnings-event timing; preregistered candidates (Massive, Yahoo earnings calendar, SEC EDGAR) remain unverified."
    )
    evidence.unverified.extend([
        "Massive historical earnings schedule",
        "Yahoo earnings calendar",
        "EDGAR disclosure timing as schedule proxy",
    ])

    # The min contract requires a historical known-at-time schedule. None of the
    # preregistered providers demonstrated one, so the `unknown` treatment is
    # fail-closed by design.
    evidence.flags["unknown_treatment_fail_closed"] = True
    result.provider_selected = selected
    result.summary = evidence.to_dict()
    return result, evidence, any_attempted


def _run_family(
    family_name: str,
    family_spec: dict[str, Any],
    panel: list[dict[str, Any]],
    budget: RequestBudget,
    creds: dict[str, str | None],
    test_inject: dict[str, Any] | None,
    context: dict[str, Any],
) -> tuple[DataFamilyResult, FamilyEvidence, bool]:
    """Collect records and evidence for one family without assigning disposition."""
    min_contract = family_spec.get("minimum_usable_contract", {})
    if family_name == "daily_market_data":
        result, evidence, any_attempted, raw_bars = _probe_daily_market_data(
            [family_spec["preferred_provider"]["name"]] + [fb["name"] for fb in family_spec.get("fallback_order", [])],
            panel, budget, creds, min_contract, test_inject,
        )
        context["daily_bars"] = raw_bars
        return result, evidence, any_attempted
    if family_name == "security_master_and_corporate_actions":
        return _probe_security_master(
            [family_spec["preferred_provider"]["name"]] + [fb["name"] for fb in family_spec.get("fallback_order", [])],
            panel, budget, creds, min_contract, test_inject, context,
        )
    if family_name == "issuer_fundamentals_and_shares":
        return _probe_fundamentals(
            [family_spec["preferred_provider"]["name"]] + [fb["name"] for fb in family_spec.get("fallback_order", [])],
            panel, budget, creds, min_contract, test_inject, context,
        )
    if family_name == "earnings_event_timing":
        return _probe_earnings(
            [family_spec["preferred_provider"]["name"]] + [fb["name"] for fb in family_spec.get("fallback_order", [])],
            panel, budget, creds, min_contract, test_inject,
        )
    return DataFamilyResult(family=family_name), FamilyEvidence(family=family_name), False


def _finalize_family(
    family_name: str,
    result: DataFamilyResult,
    evidence: FamilyEvidence,
    min_contract: dict[str, Any],
    any_attempted: bool,
    context: dict[str, Any],
) -> DataFamilyResult:
    """Apply the locked evaluator to set disposition and confidence."""
    # Stable identity join for daily market data depends on security master CIKs.
    if family_name == "daily_market_data" and context.get("identities"):
        identities = context["identities"]
        probe_symbols = {i["identifier"] for i in context.get("panel", [])}
        found = {s for s in identities if s in probe_symbols}
        evidence.flags["stable_identity_join"] = (
            len(found) == len(probe_symbols) > 0
            and all(
                identities[s].get("cik") and identities[s].get("primary_exchange")
                for s in found
            )
        )

    disposition, confidence, blockers, limitations = evaluate_family(
        family_name, min_contract, evidence, any_attempted,
    )
    result.disposition = disposition
    result.evidence_confidence = confidence
    result.blockers = blockers
    result.limitations = limitations
    result.summary = evidence.to_dict()
    return result


def _overall_disposition(families: list[DataFamilyResult]) -> str:
    """Compute overall disposition from per-family dispositions."""
    tuples = [(f.family, f.disposition) for f in families]
    return evaluate_overall(tuples)[0]


def _recommended_next_action(report: FeasibilityReport) -> str:
    if report.overall_disposition == "supported":
        return "Proceed to a separately approved LONG-002C assignment under the unchanged contract"
    if report.overall_disposition == "supported_with_documented_limitations":
        return "Request a specific Gary-approved data-sufficiency amendment before LONG-002C for the unsupported families"
    return "Perform no further LONG-002 work on the unsupported families until provider capability improves or a Gary-approved amendment is granted"


def _collect_limitations(families: list[DataFamilyResult]) -> list[str]:
    out: list[str] = []
    for f in families:
        out.extend(f.limitations)
    return out


def _collect_blockers(families: list[DataFamilyResult]) -> list[str]:
    out: list[str] = []
    for f in families:
        out.extend(f.blockers)
    return out


def run_probe(
    repo_root: Path | str | None = None,
    *,
    test_inject: dict[str, Any] | None = None,
) -> FeasibilityReport:
    """Execute the bounded LONG-002B feasibility probe."""
    root = Path(repo_root or ".")
    spec, probe_sha = load_probe_spec(root)
    long_002_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002-v1.json")
    data_contract_sha = sha256_of_file(root / "docs" / "research" / "specs" / "LONG-002B-data-contract-v1.json")

    budget = RequestBudget(max_requests=spec["hard_network_budget"]["max_total_http_requests"])
    if test_inject:
        creds = {
            "massive_api_key": "test" if test_inject.get("massive_request_func") else None,
            "alpaca_api_key": "test" if test_inject.get("alpaca_request_func") else None,
            "alpaca_secret_key": "test" if test_inject.get("alpaca_request_func") else None,
        }
    else:
        creds = resolve_credentials()

    start = time.monotonic()
    context: dict[str, Any] = {}
    family_order = spec["data_families"]
    family_results: list[DataFamilyResult] = []
    family_evidences: list[FamilyEvidence] = []
    family_attempts: list[bool] = []

    context["panel"] = spec["probe_panel"]["locked_panel"]
    try:
        for family_name, family_spec in family_order.items():
            requests_before = budget.used
            result, evidence, any_attempted = _run_family(
                family_name, family_spec, context["panel"], budget, creds, test_inject, context,
            )
            result.request_count = budget.used - requests_before
            family_results.append(result)
            family_evidences.append(evidence)
            family_attempts.append(any_attempted)
    except BudgetError:
        pass
    runtime = time.monotonic() - start

    # Finalize dispositions with the complete cross-family context.
    for family_name, family_spec, result, evidence, attempted in zip(
        family_order.keys(), family_order.values(), family_results, family_evidences, family_attempts,
    ):
        min_contract = family_spec.get("minimum_usable_contract", {})
        _finalize_family(family_name, result, evidence, min_contract, attempted, context)

    overall = _overall_disposition(family_results)
    overall_confidence = evaluate_overall([(f.family, f.disposition) for f in family_results])[1]
    report = FeasibilityReport(
        task_id="LONG-002B",
        overall_disposition=overall,
        overall_evidence_confidence=overall_confidence,
        total_http_requests=budget.used,
        runtime_seconds=runtime,
        code_commit_sha="",
        long_002_spec_sha256=long_002_sha,
        probe_spec_sha256=probe_sha,
        data_contract_sha256=data_contract_sha,
        data_families=family_results,
    )
    report.recommended_next_action = _recommended_next_action(report)
    report.limitations = _collect_limitations(family_results)
    report.blockers = _collect_blockers(family_results)
    return report
