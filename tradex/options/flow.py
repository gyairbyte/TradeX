"""Options data resolution and scanning.

This module distinguishes **true options flow** (transaction-level events from
a provider such as Unusual Whales) from **options-chain snapshots** (aggregated
contract listings from Tradier or Yahoo). It exposes capability-aware source
resolution, structured scan reports, and a non-directional put/call volume
balance helper.

True-flow rows carry provider-supplied fields such as ``side``, ``premium``,
``is_sweep``, and ``provider_sentiment``. Chain rows do not infer those fields.
"""
from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

from tradex.data.fetcher import (
    ProviderCapabilityError,
    ProviderError,
    ProviderResponseError,
    ProviderTransientError,
)
from tradex.options.models import (
    OptionsActivityReport,
    OptionsDataKind,
    OptionsScanStatus,
    OptionsSourceStatus,
)

load_dotenv()

UNUSUAL_WHALES_KEY = os.getenv("UNUSUAL_WHALES_API_KEY", "")
TRADIER_KEY = os.getenv("TRADIER_API_KEY", "")

OPTIONS_DATA_SOURCE = os.getenv("OPTIONS_DATA_SOURCE", "auto").lower().strip()

_OPTIONS_SOURCES = {"auto", "unusual_whales", "tradier", "yahoo"}

# Volume/OI ratio above this = unusual activity worth flagging
VOL_OI_THRESHOLD = 3.0
# Options volume vs 20-day avg above this = volume spike
VOL_SPIKE_THRESHOLD = 2.5

_RESULT_COLUMNS = [
    "ticker", "requested_source", "actual_source", "data_kind",
    "type", "side", "strike", "expiry", "premium",
    "volume", "open_interest", "vol_oi_ratio", "is_sweep",
    "provider_sentiment", "timestamp", "last", "bid", "ask",
]


# ── source resolution ────────────────────────────────────────────────────────
def _resolve_options_source_name(source: str | None) -> str:
    """Return a validated options source string."""
    s = (source or OPTIONS_DATA_SOURCE).lower().strip()
    if s not in _OPTIONS_SOURCES:
        raise ProviderCapabilityError(
            f"Unknown options source '{source}'; supported: {', '.join(sorted(_OPTIONS_SOURCES))}"
        )
    return s


def _has_unusual_whales() -> bool:
    return bool(UNUSUAL_WHALES_KEY)


def _has_tradier() -> bool:
    return bool(TRADIER_KEY)


def _unusual_whales_status(
    requested_source: str,
    *,
    actual_source: str | None,
    available: bool,
    data_kind: OptionsDataKind | None = OptionsDataKind.TRUE_FLOW,
    error: str | None = None,
) -> OptionsSourceStatus:
    return OptionsSourceStatus(
        requested_source=requested_source,
        actual_source=actual_source,
        configured=_has_unusual_whales(),
        available=available,
        data_kind=data_kind,
        freshness="provider_defined",
        delayed=None,
        supports_event_timestamps=True,
        supports_trade_side=True,
        supports_premium=True,
        supports_sweeps=True,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=(
            "Premium, side, sweep, and sentiment fields are provider-supplied and may be absent from any response.",
        ),
        error=error,
    )


def _tradier_chain_status(
    requested_source: str,
    *,
    actual_source: str | None,
    available: bool,
    data_kind: OptionsDataKind | None = OptionsDataKind.CHAIN_SNAPSHOT,
    error: str | None = None,
) -> OptionsSourceStatus:
    return OptionsSourceStatus(
        requested_source=requested_source,
        actual_source=actual_source,
        configured=_has_tradier(),
        available=available,
        data_kind=data_kind,
        freshness="provider_defined",
        delayed=None,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=True,
        supports_open_interest=True,
        limitations=(
            "Provides option-chain snapshots, not transaction-level flow.",
            "Sweep detection, trade-side, and premium data are not available.",
        ),
        error=error,
    )


def _yahoo_chain_status(
    requested_source: str,
    *,
    actual_source: str | None,
    available: bool,
    data_kind: OptionsDataKind | None = OptionsDataKind.CHAIN_SNAPSHOT,
    error: str | None = None,
) -> OptionsSourceStatus:
    return OptionsSourceStatus(
        requested_source=requested_source,
        actual_source=actual_source,
        configured=True,
        available=available,
        data_kind=data_kind,
        freshness="delayed",
        delayed=True,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=True,
        supports_open_interest=True,
        limitations=(
            "Delayed/provider-defined chain snapshots.",
            "No event timestamps, trade side, premium, or sweep detection.",
            "Open interest and volume may update on different cadences.",
        ),
        error=error,
    )


def resolve_flow_source(source: str | None = None) -> OptionsSourceStatus:
    """Resolve the requested source for a true-flow scan.

    ``auto`` selects Unusual Whales only when ``UNUSUAL_WHALES_API_KEY`` is
    configured. Tradier and Yahoo are explicitly rejected as non-flow-capable.
    No network calls are made.
    """
    requested = _resolve_options_source_name(source)

    if requested == "unusual_whales":
        if _has_unusual_whales():
            return _unusual_whales_status(requested, actual_source="unusual_whales", available=True)
        return _unusual_whales_status(
            requested,
            actual_source=None,
            available=False,
            error="Unusual Whales source selected but UNUSUAL_WHALES_API_KEY is not configured.",
        )

    if requested == "tradier":
        configured = _has_tradier()
        error = "Tradier provides option-chain snapshots, not transaction-level flow."
        if not configured:
            error = (
                "Tradier source selected but TRADIER_API_KEY is not configured; "
                "Tradier provides option-chain snapshots, not transaction-level flow."
            )
        return _tradier_chain_status(
            requested,
            actual_source=None,
            available=False,
            data_kind=None,
            error=error,
        )

    if requested == "yahoo":
        return _yahoo_chain_status(
            requested,
            actual_source=None,
            available=False,
            data_kind=None,
            error="Yahoo provides delayed option-chain snapshots, not transaction-level flow.",
        )

    # requested == "auto"
    if _has_unusual_whales():
        return _unusual_whales_status("auto", actual_source="unusual_whales", available=True)
    return OptionsSourceStatus(
        requested_source="auto",
        actual_source=None,
        configured=False,
        available=False,
        data_kind=None,
        freshness="unknown",
        delayed=None,
        supports_event_timestamps=False,
        supports_trade_side=False,
        supports_premium=False,
        supports_sweeps=False,
        supports_chain_volume=False,
        supports_open_interest=False,
        limitations=(
            "No true-flow source is configured.",
            "Tradier and Yahoo provide chain snapshots only.",
        ),
        error="No true-flow source is configured. Configure UNUSUAL_WHALES_API_KEY to enable true options-flow scanning.",
    )


def resolve_chain_source(source: str | None = None) -> OptionsSourceStatus:
    """Resolve the requested source for a chain-activity scan.

    ``auto`` selects Tradier when ``TRADIER_API_KEY`` is configured, otherwise
    Yahoo. Unusual Whales is rejected because it is a true-flow source, not a
    chain snapshot. No network calls are made.
    """
    requested = _resolve_options_source_name(source)

    if requested == "unusual_whales":
        if _has_unusual_whales():
            error = "Unusual Whales is a true-flow source and is not used for chain-snapshot analysis."
        else:
            error = (
                "Unusual Whales source selected but UNUSUAL_WHALES_API_KEY is not configured; "
                "Unusual Whales is a true-flow source, not a chain snapshot."
            )
        return _unusual_whales_status(
            requested,
            actual_source=None,
            available=False,
            data_kind=None,
            error=error,
        )

    if requested == "tradier":
        if _has_tradier():
            return _tradier_chain_status(requested, actual_source="tradier", available=True)
        return _tradier_chain_status(
            requested,
            actual_source=None,
            available=False,
            error="Tradier source selected but TRADIER_API_KEY is not configured.",
        )

    if requested == "yahoo":
        return _yahoo_chain_status(requested, actual_source="yahoo", available=True)

    # requested == "auto"
    if _has_tradier():
        return _tradier_chain_status("auto", actual_source="tradier", available=True)
    return _yahoo_chain_status("auto", actual_source="yahoo", available=True)


# ── numeric helpers ──────────────────────────────────────────────────────────
def _validate_min_vol_oi(min_vol_oi: float) -> float:
    """Validate the volume/open-interest threshold."""
    if isinstance(min_vol_oi, bool):
        raise TypeError("min_vol_oi must be a number, not a bool")
    if isinstance(min_vol_oi, str):
        raise TypeError("min_vol_oi must be a number, not a string")
    if not isinstance(min_vol_oi, (int, float)):
        raise TypeError("min_vol_oi must be numeric")
    if isinstance(min_vol_oi, float) and (math.isnan(min_vol_oi) or math.isinf(min_vol_oi)):
        raise ValueError("min_vol_oi must be finite")
    if min_vol_oi <= 0:
        raise ValueError("min_vol_oi must be positive")
    return float(min_vol_oi)


def _sanitize_failure_message(exc: Exception) -> str:
    """Return a failure string with any configured credentials redacted."""
    text = f"{type(exc).__name__}: {exc}"
    for secret in (UNUSUAL_WHALES_KEY, TRADIER_KEY):
        if secret:
            text = text.replace(secret, "***")
    return text


def _to_number(value: object, *, allow_zero: bool = True, allow_negative: bool = False) -> float | None:
    """Return a cleaned finite number or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    if not allow_negative and v < 0:
        return None
    if not allow_zero and v == 0:
        return None
    return v


def _to_numeric_series(
    series: pd.Series | None,
    df: pd.DataFrame,
    *,
    allow_zero: bool = True,
    allow_negative: bool = False,
) -> pd.Series:
    """Return a JSON-safe object-dtype series with non-finite/invalid values nulled."""
    if series is None:
        return pd.Series([None] * len(df), index=df.index, dtype=object)
    s = pd.to_numeric(series, errors="coerce")

    def _clean(v: object) -> object:
        if pd.isna(v):
            return None
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if not allow_negative and isinstance(v, (int, float)) and v < 0:
            return None
        if not allow_zero and isinstance(v, (int, float)) and v == 0:
            return None
        return v

    return s.apply(_clean)


def _safe_vol_oi_ratio(volume: float | None, open_interest: float | None) -> float | None:
    """Compute volume/open-interest only for valid, finite, non-negative values.

    ``open_interest`` must be strictly positive. ``volume`` must be finite and
    non-negative. Returns ``None`` when either input is missing, non-finite,
    zero/negative OI, or negative volume. Never substitutes 1 for zero OI.
    """
    if volume is None or open_interest is None:
        return None
    if not math.isfinite(volume) or not math.isfinite(open_interest):
        return None
    if volume < 0 or open_interest <= 0:
        return None
    return volume / open_interest


# ── normalization ────────────────────────────────────────────────────────────
def _empty_results() -> pd.DataFrame:
    """Return an empty options result DataFrame with the stable schema."""
    return pd.DataFrame(columns=_RESULT_COLUMNS)


def _normalize_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    s = str(value).strip()
    return s or None


def _normalize_contract_type(value: object) -> str | None:
    s = _normalize_string(value)
    if s is None:
        return None
    s = s.upper()
    if s in {"CALL", "C"}:
        return "CALL"
    if s in {"PUT", "P"}:
        return "PUT"
    return s


def _provider_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _parse_whales_flow(
    records: list[dict],
    ticker: str,
    requested_source: str,
    actual_source: str,
) -> pd.DataFrame:
    """Normalize Unusual Whales flow records to the stable schema."""
    if not records:
        return _empty_results()

    rows = []
    for r in records:
        volume = _to_number(r.get("volume"), allow_zero=True)
        oi = _to_number(r.get("open_interest"), allow_zero=True)
        rows.append({
            "ticker": ticker,
            "requested_source": requested_source,
            "actual_source": actual_source,
            "data_kind": OptionsDataKind.TRUE_FLOW.value,
            "type": _normalize_contract_type(r.get("put_call")),
            "side": _normalize_string(r.get("side")),
            "strike": _to_number(r.get("strike_price"), allow_zero=True),
            "expiry": _normalize_string(r.get("expiry_date")),
            "premium": _to_number(r.get("premium"), allow_zero=True),
            "volume": volume,
            "open_interest": oi,
            "vol_oi_ratio": _safe_vol_oi_ratio(volume, oi),
            "is_sweep": _provider_bool(r.get("is_sweep")),
            "provider_sentiment": _normalize_string(r.get("sentiment")),
            "timestamp": _normalize_string(r.get("created_at")),
            "last": None,
            "bid": None,
            "ask": None,
        })

    return pd.DataFrame(rows, columns=_RESULT_COLUMNS)


def _normalize_chain(
    df: pd.DataFrame,
    ticker: str,
    requested_source: str,
    actual_source: str,
) -> pd.DataFrame:
    """Normalize a Tradier or Yahoo chain DataFrame to the stable schema."""
    if df is None or df.empty:
        return _empty_results()

    out = pd.DataFrame(index=df.index)
    out["ticker"] = df.get("ticker", pd.Series([ticker] * len(df), index=df.index)).fillna(ticker)
    out["requested_source"] = requested_source
    out["actual_source"] = actual_source
    out["data_kind"] = OptionsDataKind.CHAIN_SNAPSHOT.value

    if "type" in df.columns:
        type_col = df["type"]
    elif "option_type" in df.columns:
        type_col = df["option_type"]
    else:
        type_col = None
    out["type"] = type_col.astype(str).str.upper() if type_col is not None else None

    if "expiry" in df.columns:
        expiry_col = df["expiry"]
    elif "expiration_date" in df.columns:
        expiry_col = df["expiration_date"]
    else:
        expiry_col = None
    out["expiry"] = expiry_col

    out["volume"] = _to_numeric_series(df.get("volume"), df, allow_zero=True)
    out["open_interest"] = _to_numeric_series(df.get("openInterest") if "openInterest" in df.columns else df.get("open_interest"), df, allow_zero=True)
    out["premium"] = _to_numeric_series(df.get("premium"), df, allow_zero=True)

    if "lastPrice" in df.columns and "last" not in df.columns:
        last_col = df["lastPrice"]
    else:
        last_col = df.get("last")
    out["last"] = _to_numeric_series(last_col, df, allow_zero=True)
    out["bid"] = _to_numeric_series(df.get("bid"), df, allow_zero=True)
    out["ask"] = _to_numeric_series(df.get("ask"), df, allow_zero=True)
    out["strike"] = _to_numeric_series(df.get("strike"), df, allow_zero=True)

    out["side"] = None
    out["is_sweep"] = False
    out["provider_sentiment"] = None
    out["timestamp"] = None

    out["vol_oi_ratio"] = [
        _safe_vol_oi_ratio(v, oi) for v, oi in zip(out["volume"], out["open_interest"])
    ]

    return out[_RESULT_COLUMNS]


def _sort_results(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by vol_oi_ratio descending with deterministic tie-breaking."""
    if df.empty:
        return df
    sort_cols = ["vol_oi_ratio", "ticker", "type", "strike", "expiry", "volume"]
    ascending = [False, True, True, True, True, False]
    available = [c for c in sort_cols if c in df.columns]
    if "vol_oi_ratio" not in available:
        return df.sort_values(by=available, ascending=ascending[: len(available)], na_position="last", ignore_index=True)
    return df.sort_values(
        by=available,
        ascending=ascending[: len(available)],
        na_position="last",
        ignore_index=True,
    )


# ── provider fetchers ────────────────────────────────────────────────────────
def _fetch_unusual_whales_flow(ticker: str, limit: int = 20) -> list[dict]:
    """Fetch recent options flow for a ticker from Unusual Whales.

    Raises ``ProviderCapabilityError`` when the API key is missing,
    ``ProviderTransientError`` for network issues, and ``ProviderResponseError``
    for non-success HTTP or malformed JSON. No raw response bodies are exposed.
    """
    if not UNUSUAL_WHALES_KEY:
        raise ProviderCapabilityError(
            "Unusual Whales source selected but UNUSUAL_WHALES_API_KEY is not configured"
        )
    try:
        url = f"https://api.unusualwhales.com/api/stock/{ticker}/options-flow"
        headers = {"Authorization": f"Bearer {UNUSUAL_WHALES_KEY}"}
        resp = requests.get(url, headers=headers, params={"limit": limit}, timeout=10)
        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Unusual Whales returned HTTP {resp.status_code} for {ticker}"
            )
        data = resp.json().get("data", [])
        return data if isinstance(data, list) else []
    except requests.RequestException as exc:
        raise ProviderTransientError(
            f"Unusual Whales request failed for {ticker}: {type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"Unusual Whales returned malformed JSON for {ticker}"
        ) from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderResponseError(
            f"Unusual Whales response error for {ticker}: {type(exc).__name__}"
        ) from exc


def _fetch_tradier_chain(ticker: str) -> pd.DataFrame:
    """Fetch the nearest-expiry options chain from Tradier.

    Raises ``ProviderCapabilityError`` for missing credentials, ``ProviderTransientError``
    for network issues, and ``ProviderResponseError`` for bad HTTP or malformed data.
    """
    if not TRADIER_KEY:
        raise ProviderCapabilityError(
            "Tradier source selected but TRADIER_API_KEY is not configured"
        )

    headers = {
        "Authorization": f"Bearer {TRADIER_KEY}",
        "Accept": "application/json",
    }

    try:
        exp_url = "https://api.tradier.com/v1/markets/options/expirations"
        exp_resp = requests.get(
            exp_url,
            headers=headers,
            params={"symbol": ticker, "includeAllRoots": True},
            timeout=10,
        )
        if exp_resp.status_code != 200:
            raise ProviderResponseError(
                f"Tradier expirations returned HTTP {exp_resp.status_code} for {ticker}"
            )
        expirations = exp_resp.json().get("expirations", {}).get("date", [])
        if not expirations:
            return _empty_results()
        nearest_exp = expirations[0] if isinstance(expirations, list) else expirations

        chain_url = "https://api.tradier.com/v1/markets/options/chains"
        chain_resp = requests.get(
            chain_url,
            headers=headers,
            params={"symbol": ticker, "expiration": nearest_exp, "greeks": False},
            timeout=10,
        )
        if chain_resp.status_code != 200:
            raise ProviderResponseError(
                f"Tradier chain returned HTTP {chain_resp.status_code} for {ticker}"
            )
        options = chain_resp.json().get("options", {}).get("option", [])
        if not options:
            return _empty_results()
        return pd.DataFrame(options)
    except requests.RequestException as exc:
        raise ProviderTransientError(
            f"Tradier request failed for {ticker}: {type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"Tradier returned malformed JSON for {ticker}"
        ) from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderResponseError(
            f"Tradier response error for {ticker}: {type(exc).__name__}"
        ) from exc


def _fetch_yf_chain(ticker: str) -> pd.DataFrame:
    """Fetch the nearest-expiry options chain from yfinance.

    Raises ``ProviderTransientError`` for network issues and ``ProviderResponseError``
    for malformed responses. Returns an empty DataFrame for tickers with no options.
    """
    try:
        tk = yf.Ticker(ticker)
        exps = tk.options
        if not exps:
            return _empty_results()
        expiry = exps[0]
        chain = tk.option_chain(expiry)
        calls = chain.calls.copy()
        calls["type"] = "CALL"
        puts = chain.puts.copy()
        puts["type"] = "PUT"
        df = pd.concat([calls, puts], ignore_index=True)
        df["ticker"] = ticker
        df["expiry"] = expiry
        return df
    except requests.RequestException as exc:
        raise ProviderTransientError(
            f"Yahoo Finance request failed for {ticker}: {type(exc).__name__}"
        ) from exc
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderResponseError(
            f"Yahoo Finance response error for {ticker}: {type(exc).__name__}"
        ) from exc


def _resolve_actual_source_for_get_flow(source_name: str) -> str:
    """Resolve ``auto`` to a concrete fetcher for the legacy ``get_flow`` path."""
    if source_name == "auto":
        if _has_unusual_whales():
            return "unusual_whales"
        if _has_tradier():
            return "tradier"
        return "yahoo"
    return source_name


def get_flow(ticker: str, source: str | None = None) -> pd.DataFrame:
    """Fetch options data for ``ticker`` from a single concrete source.

    ``auto`` follows the legacy priority (Unusual Whales → Tradier → Yahoo). This
    low-level helper is retained for callers that need a raw DataFrame. New code
    should prefer the structured ``scan_*_with_report`` APIs.

    Raises ``ProviderCapabilityError`` for missing credentials on paid sources.
    Raises ``ProviderTransientError``/``ProviderResponseError`` for network and
    malformed-response problems. Returns an empty DataFrame for valid zero-data
    responses.
    """
    requested = _resolve_options_source_name(source)
    actual = _resolve_actual_source_for_get_flow(requested)

    if actual == "unusual_whales":
        records = _fetch_unusual_whales_flow(ticker)
        return _parse_whales_flow(records, ticker, requested, actual)

    if actual == "tradier":
        if not _has_tradier():
            raise ProviderCapabilityError(
                "Tradier source selected but TRADIER_API_KEY is not configured"
            )
        df = _fetch_tradier_chain(ticker)
        return _normalize_chain(df, ticker, requested, actual)

    if actual == "yahoo":
        df = _fetch_yf_chain(ticker)
        return _normalize_chain(df, ticker, requested, actual)

    raise ProviderCapabilityError(f"Unsupported options source '{actual}'")


# ── scan APIs ───────────────────────────────────────────────────────────────
def _apply_vol_oi_filter(df: pd.DataFrame, min_vol_oi: float) -> pd.DataFrame:
    """Return rows whose ``vol_oi_ratio`` is finite and >= ``min_vol_oi``."""
    mask = df["vol_oi_ratio"].apply(lambda x: x is not None and x >= min_vol_oi)
    return df[mask].reset_index(drop=True)


def _determine_scan_status(total_matches: int, failures: Mapping[str, str]) -> OptionsScanStatus:
    if failures:
        return OptionsScanStatus.PARTIAL_FAILURE if total_matches > 0 else OptionsScanStatus.COMPLETE_FAILURE
    if total_matches == 0:
        return OptionsScanStatus.NO_MATCHES
    return OptionsScanStatus.COMPLETED


def _scan_report(
    source_status: OptionsSourceStatus,
    results: pd.DataFrame,
    total_requested: int,
    total_fetched: int,
    total_matches: int,
    failures: Mapping[str, str],
    status: OptionsScanStatus | None = None,
) -> OptionsActivityReport:
    if status is None:
        status = _determine_scan_status(total_matches, failures)
    limitations = tuple(source_status.limitations)
    return OptionsActivityReport(
        requested_source=source_status.requested_source,
        actual_source=source_status.actual_source,
        data_kind=source_status.data_kind,
        status=status,
        results=results,
        source_status=source_status,
        total_requested=total_requested,
        total_fetched=total_fetched,
        total_matches=total_matches,
        failures=failures,
        limitations=limitations,
    )


def scan_unusual_flow_with_report(
    tickers: list[str],
    *,
    min_vol_oi: float = VOL_OI_THRESHOLD,
    source: str | None = None,
) -> OptionsActivityReport:
    """Scan ``tickers`` for true options-flow events.

    Only a configured true-flow source (Unusual Whales under the current
    adapters) may run. ``auto`` without Unusual Whales returns
    ``SOURCE_UNAVAILABLE``. Explicit chain sources return ``NOT_FLOW_CAPABLE``.
    """
    _validate_min_vol_oi(min_vol_oi)
    source_status = resolve_flow_source(source)

    if source_status.data_kind != OptionsDataKind.TRUE_FLOW or not source_status.available:
        status = (
            OptionsScanStatus.NOT_FLOW_CAPABLE
            if source_status.requested_source in ("tradier", "yahoo")
            else OptionsScanStatus.SOURCE_UNAVAILABLE
        )
        return _scan_report(
            source_status,
            _empty_results(),
            total_requested=len(tickers),
            total_fetched=0,
            total_matches=0,
            failures={},
            status=status,
        )

    actual = source_status.actual_source
    requested = source_status.requested_source
    all_rows: list[pd.DataFrame] = []
    failures: dict[str, str] = {}

    for ticker in tickers:
        try:
            records = _fetch_unusual_whales_flow(ticker)
            df = _parse_whales_flow(records, ticker, requested, actual)
            all_rows.append(df)
        except ProviderError as exc:
            failures[ticker] = _sanitize_failure_message(exc)

    combined = pd.concat(all_rows, ignore_index=True) if all_rows else _empty_results()
    total_fetched = len(combined)
    filtered = _apply_vol_oi_filter(combined, min_vol_oi)
    total_matches = len(filtered)
    sorted_results = _sort_results(filtered)
    status = _determine_scan_status(total_matches, failures)

    return _scan_report(
        source_status,
        sorted_results,
        total_requested=len(tickers),
        total_fetched=total_fetched,
        total_matches=total_matches,
        failures=failures,
        status=status,
    )


def scan_unusual_flow(
    tickers: list[str],
    min_vol_oi: float = VOL_OI_THRESHOLD,
    source: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible wrapper for ``scan_unusual_flow_with_report``.

    Returns the result DataFrame for a successful true-flow scan. Raises
    ``ProviderCapabilityError`` when the source is unavailable or not flow-capable.
    """
    report = scan_unusual_flow_with_report(tickers, min_vol_oi=min_vol_oi, source=source)
    if report.status in (OptionsScanStatus.SOURCE_UNAVAILABLE, OptionsScanStatus.NOT_FLOW_CAPABLE):
        raise ProviderCapabilityError(report.source_status.error or "True-flow source unavailable")
    return report.results


def scan_chain_activity_with_report(
    tickers: list[str],
    *,
    min_vol_oi: float = VOL_OI_THRESHOLD,
    source: str | None = None,
) -> OptionsActivityReport:
    """Scan ``tickers`` for options-chain activity anomalies.

    Accepts Tradier or Yahoo chain snapshots. ``auto`` prefers Tradier when
    configured, otherwise Yahoo. Never labels chain data as flow, sweeps, or
    directional intent.
    """
    _validate_min_vol_oi(min_vol_oi)
    source_status = resolve_chain_source(source)

    if not source_status.available or source_status.data_kind != OptionsDataKind.CHAIN_SNAPSHOT:
        return _scan_report(
            source_status,
            _empty_results(),
            total_requested=len(tickers),
            total_fetched=0,
            total_matches=0,
            failures={},
            status=OptionsScanStatus.SOURCE_UNAVAILABLE,
        )

    actual = source_status.actual_source
    requested = source_status.requested_source
    fetcher = _fetch_tradier_chain if actual == "tradier" else _fetch_yf_chain
    all_rows: list[pd.DataFrame] = []
    failures: dict[str, str] = {}

    for ticker in tickers:
        try:
            df = fetcher(ticker)
            normalized = _normalize_chain(df, ticker, requested, actual)
            all_rows.append(normalized)
        except ProviderError as exc:
            failures[ticker] = _sanitize_failure_message(exc)

    combined = pd.concat(all_rows, ignore_index=True) if all_rows else _empty_results()
    total_fetched = len(combined)
    filtered = _apply_vol_oi_filter(combined, min_vol_oi)
    total_matches = len(filtered)
    sorted_results = _sort_results(filtered)
    status = _determine_scan_status(total_matches, failures)

    return _scan_report(
        source_status,
        sorted_results,
        total_requested=len(tickers),
        total_fetched=total_fetched,
        total_matches=total_matches,
        failures=failures,
        status=status,
    )


def scan_chain_activity(
    tickers: list[str],
    min_vol_oi: float = VOL_OI_THRESHOLD,
    source: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible wrapper for ``scan_chain_activity_with_report``.

    Returns the result DataFrame. Raises ``ProviderCapabilityError`` for an
    unavailable source.
    """
    report = scan_chain_activity_with_report(tickers, min_vol_oi=min_vol_oi, source=source)
    if report.status == OptionsScanStatus.SOURCE_UNAVAILABLE:
        raise ProviderCapabilityError(report.source_status.error or "Chain source unavailable")
    return report.results


# ── put/call volume balance ──────────────────────────────────────────────────
def _put_call_volume_ratio(put_vol: float, call_vol: float) -> tuple[float | None, str]:
    """Return a non-directional (ratio, balance) pair from aggregate volumes."""
    if call_vol == 0 and put_vol == 0:
        return None, "unknown"
    if call_vol == 0:
        return None, "put_only"
    if put_vol == 0:
        return 0.0, "call_only"
    ratio = put_vol / call_vol
    if ratio < 0.7:
        balance = "call_heavy"
    elif ratio > 1.2:
        balance = "put_heavy"
    else:
        balance = "balanced"
    return ratio, balance


def _sum_contract_volume(df: pd.DataFrame, contract_type: str) -> int:
    if df.empty or "type" not in df.columns or "volume" not in df.columns:
        return 0
    mask = df["type"].astype(str).str.upper() == contract_type
    volumes = df.loc[mask, "volume"].apply(_to_number, allow_zero=True)
    total = volumes.dropna().sum()
    return int(total) if not pd.isna(total) else 0


def get_put_call_activity(
    ticker: str,
    *,
    source: str | None = None,
) -> dict:
    """Return a non-directional call/put volume balance for ``ticker``.

    Uses chain-snapshot sources (Tradier or Yahoo). ``auto`` follows the chain
    priority. Unusual Whales is rejected because it is a true-flow source. The
    result always includes ``directional_inference: false`` and never labels
    aggregate volume as bullish or bearish.
    """
    source_status = resolve_chain_source(source)

    if not source_status.available or source_status.data_kind != OptionsDataKind.CHAIN_SNAPSHOT:
        return {
            "ticker": ticker,
            "requested_source": source_status.requested_source,
            "actual_source": source_status.actual_source,
            "data_kind": OptionsDataKind.CHAIN_SNAPSHOT.value,
            "put_call_volume_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "volume_balance": "unavailable",
            "directional_inference": False,
            "limitations": list(source_status.limitations),
            "error": source_status.error or "Chain source unavailable",
        }

    try:
        df = get_flow(ticker, source=source_status.actual_source)
    except ProviderError as exc:
        return {
            "ticker": ticker,
            "requested_source": source_status.requested_source,
            "actual_source": source_status.actual_source,
            "data_kind": OptionsDataKind.CHAIN_SNAPSHOT.value,
            "put_call_volume_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "volume_balance": "unavailable",
            "directional_inference": False,
            "limitations": list(source_status.limitations),
            "error": _sanitize_failure_message(exc),
        }

    if df.empty:
        return {
            "ticker": ticker,
            "requested_source": source_status.requested_source,
            "actual_source": source_status.actual_source,
            "data_kind": OptionsDataKind.CHAIN_SNAPSHOT.value,
            "put_call_volume_ratio": None,
            "call_volume": 0,
            "put_volume": 0,
            "volume_balance": "unknown",
            "directional_inference": False,
            "limitations": list(source_status.limitations),
            "error": None,
        }

    call_vol = _sum_contract_volume(df, "CALL")
    put_vol = _sum_contract_volume(df, "PUT")
    ratio, balance = _put_call_volume_ratio(put_vol, call_vol)

    return {
        "ticker": ticker,
        "requested_source": source_status.requested_source,
        "actual_source": source_status.actual_source,
        "data_kind": OptionsDataKind.CHAIN_SNAPSHOT.value,
        "put_call_volume_ratio": ratio,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "volume_balance": balance,
        "directional_inference": False,
        "limitations": list(source_status.limitations),
        "error": None,
    }


def get_put_call_sentiment(ticker: str, source: str | None = None) -> dict:
    """Backward-compatible wrapper for ``get_put_call_activity``.

    Preserves the legacy ``sentiment`` and ``put_call_ratio`` keys while replacing
    bullish/bearish conclusions with the non-directional volume balance. Always
    returns ``directional_inference: false``.
    """
    activity = get_put_call_activity(ticker, source=source)
    result = dict(activity)
    result["sentiment"] = activity["volume_balance"]
    result["put_call_ratio"] = activity["put_call_volume_ratio"]
    result["data_source"] = activity["actual_source"] or activity["requested_source"]
    return result
