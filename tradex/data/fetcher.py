"""
OHLCV data fetcher supporting four providers:
  - yahoo   : free, no setup, 15-min delayed intraday (default)
  - alpaca  : free real-time US stocks (requires ALPACA_API_KEY + ALPACA_SECRET_KEY in .env)
  - ibkr    : real-time global markets (requires running TWS/IB Gateway locally)
  - schwab  : Charles Schwab API — replaced TD Ameritrade in Sept 2024
              (requires Schwab brokerage account + OAuth app at developer.schwab.com)

Set the provider via the DATA_PROVIDER env var or pass it explicitly to fetch().
"""
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()


class ProviderError(RuntimeError):
    """Base class for OHLCV provider failures."""


class ProviderCapabilityError(ProviderError):
    """Raised when a provider does not support a requested data capability."""


class ProviderConfigurationError(ProviderError):
    """Raised for missing packages, invalid configuration, or unsafe local settings."""


class ProviderAuthenticationError(ProviderError):
    """Raised for missing credentials, missing token files, or authentication failures."""


class ProviderDataUnavailableError(ProviderError):
    """Raised when a provider cannot return data for a requested symbol or date range."""


class ProviderTransientError(ProviderError):
    """Raised for network timeouts, connection errors, or other retryable outages."""


class ProviderResponseError(ProviderError):
    """Raised for malformed or unexpected provider responses that are not retryable."""


# ── timeframe presets ────────────────────────────────────────────────────────
# Each provider maps these to its own param names internally.
TIMEFRAMES = {
    "intraday": {"period": "5d",  "interval": "5m"},
    "short":    {"period": "60d", "interval": "1d"},
    "long":     {"period": "2y",  "interval": "1wk"},
}

DEFAULT_PROVIDER = os.getenv("DATA_PROVIDER", "yahoo")


_MAX_ALLOWED_RETRIES = 5


def _default_backoff(attempt: int) -> float:
    """Default deterministic exponential backoff with a small cap."""
    return min(2 ** attempt, 8.0)


@dataclass(frozen=True)
class FetchPolicy:
    """Retry and fallback policy for OHLCV fetches.

    ``max_retries`` is the number of *extra* attempts beyond the first one.
    ``max_retries=0`` means a single attempt. ``fallback_order`` is a tuple of
    canonical provider names to try only when the previous provider produced
    zero usable datasets for the requested symbols. The primary provider is
    always removed from the fallback list.
    """

    max_retries: int = 0
    fallback_order: tuple[str, ...] = ()
    backoff: Callable[[int], float] | None = _default_backoff

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative; got {self.max_retries}")
        if self.max_retries > _MAX_ALLOWED_RETRIES:
            raise ValueError(
                f"max_retries must be at most {_MAX_ALLOWED_RETRIES}; got {self.max_retries}"
            )

    @classmethod
    def build(
        cls,
        max_retries: int | str | None = None,
        fallback_order: str | tuple[str, ...] | list[str] | None = None,
    ) -> "FetchPolicy":
        """Create a policy from explicit arguments and/or environment variables.

        Explicit arguments override ``OHLCV_MAX_RETRIES`` and ``OHLCV_FALLBACK_ORDER``.
        """
        # Resolve max_retries
        if max_retries is None:
            env_retries = os.getenv("OHLCV_MAX_RETRIES")
            max_retries = int(env_retries) if env_retries is not None else 0
        try:
            retries = int(max_retries)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"OHLCV_MAX_RETRIES must be an integer; got {max_retries!r}") from exc
        if retries < 0:
            raise ValueError(f"max_retries must be non-negative; got {retries}")
        if retries > _MAX_ALLOWED_RETRIES:
            raise ValueError(
                f"max_retries must be at most {_MAX_ALLOWED_RETRIES}; got {retries}"
            )

        # Resolve fallback_order
        raw_fallback = fallback_order
        if raw_fallback is None:
            raw_fallback = os.getenv("OHLCV_FALLBACK_ORDER", "")
        if isinstance(raw_fallback, str):
            parts = [p.strip() for p in raw_fallback.split(",") if p.strip()]
            raw_fallback = parts

        seen: set[str] = set()
        normalized: list[str] = []
        for p in raw_fallback:
            canonical = resolve_provider(p)
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(canonical)

        return cls(max_retries=retries, fallback_order=tuple(normalized))

    def fallback_for(self, primary: str) -> tuple[str, ...]:
        """Return the fallback order with the primary provider removed."""
        return tuple(p for p in self.fallback_order if p != resolve_provider(primary))


@dataclass
class FetchReport:
    """Structured result of a batch OHLCV fetch attempt."""

    data: dict[str, pd.DataFrame]
    requested_provider: str
    actual_provider: str | None
    fallback_used: bool
    providers_attempted: tuple[str, ...]
    failures: dict[str, ProviderError]
    attempts: dict[str, int]
    total_requested: int
    total_fetched: int
    total_fetch_attempted: int
    retries: int


def normalize_yahoo_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance MultiIndex columns and normalize names to lowercase.

    yfinance >= 0.2.x can return either single-level columns ("Open", "Close",
    ...) or a MultiIndex whose first level is the field name and whose second
    level is the ticker symbol. This helper produces a single-level lowercase
    column index regardless of the input shape.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    return df


# ── Yahoo Finance ─────────────────────────────────────────────────────────────
def _fetch_yahoo(ticker: str, timeframe: str) -> pd.DataFrame:
    tf = TIMEFRAMES[timeframe]
    df = yf.download(
        ticker,
        period=tf["period"],
        interval=tf["interval"],
        progress=False,
        auto_adjust=True,
    )
    return normalize_yahoo_columns(df).dropna()


# ── Alpaca ────────────────────────────────────────────────────────────────────
# Requires: pip install alpaca-py
# Env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY
# Free tier gives real-time IEX feed; paid gives SIP (full NBBO).
_ALPACA_INTERVAL_MAP = {
    "intraday": "5Min",
    "short":    "1Day",
    "long":     "1Week",
}
_ALPACA_LIMIT_MAP = {
    "intraday": 1000,   # ~5 trading days of 5m bars
    "short":    60,
    "long":     104,    # 2 years of weekly bars
}

def _fetch_alpaca(ticker: str, timeframe: str) -> pd.DataFrame:
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    except ImportError:
        raise ImportError("Install alpaca-py: pip install alpaca-py")

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise OSError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    client = StockHistoricalDataClient(api_key, secret_key)

    tf_str = _ALPACA_INTERVAL_MAP[timeframe]
    tf_map = {
        "5Min":  TimeFrame(5, TimeFrameUnit.Minute),
        "1Day":  TimeFrame(1, TimeFrameUnit.Day),
        "1Week": TimeFrame(1, TimeFrameUnit.Week),
    }

    from datetime import UTC, datetime, timedelta
    lookback_days = {"intraday": 7, "short": 90, "long": 730}
    start = datetime.now(UTC) - timedelta(days=lookback_days[timeframe])

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=tf_map[tf_str],
        start=start,
        limit=_ALPACA_LIMIT_MAP[timeframe],
    )
    bars = client.get_stock_bars(request).df

    # Alpaca returns a MultiIndex (symbol, timestamp) — drop symbol level
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(ticker, level="symbol")

    bars.index.name = "datetime"
    bars = bars.rename(columns={"open": "open", "high": "high", "low": "low",
                                 "close": "close", "volume": "volume"})
    return bars[["open", "high", "low", "close", "volume"]].dropna()


# ── Interactive Brokers ───────────────────────────────────────────────────────
# Requires: pip install ib_insync  AND  TWS or IB Gateway running locally
# TWS/Gateway must have API connections enabled (Edit > Global Config > API > Enable)
# Default connection: host=127.0.0.1, port=7497 (paper) or 7496 (live)
_IBKR_DURATION_MAP = {
    "intraday": ("5 D", "5 mins"),
    "short":    ("60 D", "1 day"),
    "long":     ("2 Y",  "1 week"),
}

def _fetch_ibkr(ticker: str, timeframe: str) -> pd.DataFrame:
    try:
        from ib_insync import IB, Stock, util
    except ImportError:
        raise ImportError("Install ib_insync: pip install ib_insync")

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "7497"))   # 7497 = paper, 7496 = live
    client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        contract = Stock(ticker, "SMART", "USD")
        duration, bar_size = _IBKR_DURATION_MAP[timeframe]
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        df = util.df(bars).set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={"open": "open", "high": "high", "low": "low",
                                  "close": "close", "volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]].dropna()
    finally:
        ib.disconnect()


# ── Charles Schwab (replaced TD Ameritrade Sept 2024) ────────────────────────
# Requires: pip install schwab-py
# Setup:
#   1. Create a Schwab brokerage account at schwab.com
#   2. Register an app at developer.schwab.com — get SCHWAB_APP_KEY + SCHWAB_APP_SECRET
#   3. Run scripts/schwab_oauth.py once to generate the OAuth token file at
#      SCHWAB_TOKEN_PATH (default: ~/.tradex_schwab_token.json). After that,
#      this fetcher just reads the token; schwab-py refreshes it automatically.
# Note: TD Ameritrade API (tda-api library) is fully dead — do not use it.
from datetime import UTC, datetime, timedelta


def _repo_root() -> Path | None:
    """Return the repository root if this file is inside a git checkout, else None."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").is_dir():
            return parent
    return None


def _assert_token_path_outside_repo(token_path: str) -> None:
    """Refuse to read or write a Schwab token file that lives inside the repo."""
    repo_root = _repo_root()
    if repo_root is None:
        return
    resolved = Path(token_path).expanduser().resolve()
    if resolved.is_relative_to(repo_root):
        raise ValueError(
            f"Schwab token path must not be inside the repository: {resolved}\n"
            f"Set SCHWAB_TOKEN_PATH to a location outside {repo_root}, "
            "e.g. ~/.tradex_schwab_token.json"
        )


# Map each timeframe to (client method name, lookback timedelta).
# Lookbacks roughly match what other providers return for the same timeframe.
_SCHWAB_TIMEFRAMES = {
    "intraday": ("get_price_history_every_five_minutes", timedelta(days=5)),
    "short":    ("get_price_history_every_day",          timedelta(days=120)),
    "long":     ("get_price_history_every_week",         timedelta(days=730)),
}

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


# Cache the authenticated client across calls — fetching a watchlist would
# otherwise reload + decrypt the token file once per ticker.
_SCHWAB_CLIENT = None
_SCHWAB_LOCK = threading.Lock()


def _normalize_schwab_candles(candles: list[dict], drop_any_null: bool = True) -> pd.DataFrame:
    """Convert Schwab price-history candles into the canonical OHLCV DataFrame.

    Schwab candle JSON contains: open, high, low, close, volume, datetime (epoch ms).
    Returns a sorted, de-duplicated, UTC timezone-aware DataFrame with columns
    open, high, low, close, volume. Duplicate timestamps keep the last occurrence.

    By default rows with any missing OHLCV field are dropped. For date-ranged
    daily history callers can pass ``drop_any_null=False`` to keep rows that
    have other OHLCV data but a missing close (needed for COR-003 session
    counting).
    """
    if not candles:
        return pd.DataFrame(
            columns=_OHLCV_COLUMNS,
            index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
        )

    df = pd.DataFrame(candles)
    df.columns = [c.lower() for c in df.columns]

    if "datetime" not in df.columns:
        return pd.DataFrame(
            columns=_OHLCV_COLUMNS,
            index=pd.DatetimeIndex([], name="datetime", tz="UTC"),
        )

    # Coerce epoch-ms timestamps; invalid values become NaT and are dropped.
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True, errors="coerce")
    df = df.dropna(subset=["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    for col in _OHLCV_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_OHLCV_COLUMNS]

    for col in _OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows that are missing any OHLCV field, or -- for daily history -- only
    # rows with no OHLCV data at all. Volume of 0 is valid; NaN is not.
    if drop_any_null:
        return df.dropna(subset=_OHLCV_COLUMNS)
    return df.dropna(how="all")


def _get_schwab_client():
    """Return an authenticated Schwab client, or raise a safe error."""
    try:
        from schwab.auth import client_from_token_file
    except ImportError as e:
        raise ImportError(
            "Install schwab-py to use the Schwab provider: "
            "uv pip install -e \".[schwab]\""
        ) from e

    app_key = os.getenv("SCHWAB_APP_KEY", "").strip()
    app_secret = os.getenv("SCHWAB_APP_SECRET", "").strip()
    token_path = os.path.expanduser(
        os.getenv("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json")
    )

    if not app_key or not app_secret:
        raise OSError("SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in .env")

    _assert_token_path_outside_repo(token_path)

    if not os.path.exists(token_path):
        raise FileNotFoundError(
            "Schwab OAuth token not found. "
            "Run `python scripts/schwab_oauth.py` once to generate it."
        )

    global _SCHWAB_CLIENT
    with _SCHWAB_LOCK:
        if _SCHWAB_CLIENT is None:
            try:
                _SCHWAB_CLIENT = client_from_token_file(
                    token_path=token_path,
                    api_key=app_key,
                    app_secret=app_secret,
                )
            except Exception:  # noqa: BLE001
                raise RuntimeError(
                    "Schwab authentication failed. Verify the token file, "
                    "app key, and app secret, then re-run the OAuth script."
                ) from None

    return _SCHWAB_CLIENT


def _fetch_schwab(ticker: str, timeframe: str) -> pd.DataFrame:
    """Fetch canonical OHLCV data from the Schwab Market Data API.

    Raises:
        ImportError:            schwab-py is not installed.
        EnvironmentError:       SCHWAB_APP_KEY or SCHWAB_APP_SECRET missing.
        FileNotFoundError:      The OAuth token file does not exist.
        ValueError:             The token path is inside the repo or timeframe unsupported.
        RuntimeError:            The Schwab API request failed.
        ValueError:             The response was not valid JSON.
    """
    client = _get_schwab_client()

    if timeframe not in _SCHWAB_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe for schwab: {timeframe}")
    method_name, lookback = _SCHWAB_TIMEFRAMES[timeframe]

    end = datetime.now(UTC)
    start = end - lookback

    resp = getattr(client, method_name)(
        ticker,
        start_datetime=start,
        end_datetime=end,
        need_extended_hours_data=False,
    )

    status = getattr(resp, "status_code", "unknown")
    try:
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        raise RuntimeError(
            f"Schwab price-history request failed for {ticker} ({timeframe}) "
            f"(HTTP {status}). The response may contain an error from Schwab."
        ) from None

    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise ValueError(
            f"Schwab returned non-JSON price-history response for {ticker}"
        ) from None

    candles = data.get("candles", []) if isinstance(data, dict) else []
    return _normalize_schwab_candles(candles)


def _classify_exception(exc: Exception, ticker: str, timeframe: str) -> ProviderError:
    """Translate an unexpected provider exception into a safe, typed error.

    The returned error contains no credentials, tokens, or raw response bodies.
    """
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, ImportError):
        return ProviderConfigurationError(
            f"Provider package not installed for {ticker} ({timeframe})"
        )
    if isinstance(exc, FileNotFoundError):
        return ProviderAuthenticationError(
            f"Missing token or credential file for {ticker} ({timeframe})"
        )
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return ProviderTransientError(
            f"Network error fetching {ticker} ({timeframe})"
        )
    if isinstance(exc, OSError):
        # OSError covers EnvironmentError; in this codebase we raise it for
        # missing env vars. Treat missing credentials as non-retryable auth/config.
        return ProviderAuthenticationError(
            f"Missing environment configuration for {ticker} ({timeframe})"
        )
    if isinstance(exc, RuntimeError):
        return ProviderResponseError(
            f"Provider request failed for {ticker} ({timeframe})"
        )
    if isinstance(exc, ValueError):
        return ProviderConfigurationError(
            f"Invalid provider configuration or request for {ticker} ({timeframe})"
        )
    return ProviderResponseError(
        f"Unexpected provider error for {ticker} ({timeframe})"
    )


def _fetch_with_retry(
    provider_func: Callable[[], pd.DataFrame],
    policy: FetchPolicy,
    sleeper: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """Call a provider fetch function with a bounded number of retries.

    Retries only occur for ``ProviderTransientError``. All other errors stop
    immediately. ``sleeper`` is injectable for tests.
    """
    if sleeper is None:
        sleeper = time.sleep
    attempts = policy.max_retries + 1
    last_error: ProviderError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return provider_func()
        except ProviderError as e:
            last_error = e
            if isinstance(e, ProviderTransientError) and attempt < attempts:
                backoff = policy.backoff(attempt) if policy.backoff else _default_backoff(attempt)
                sleeper(backoff)
                continue
            raise
        except Exception as e:  # noqa: BLE001
            classified = _classify_exception(e, "", "")
            last_error = classified
            if isinstance(classified, ProviderTransientError) and attempt < attempts:
                backoff = policy.backoff(attempt) if policy.backoff else _default_backoff(attempt)
                sleeper(backoff)
                continue
            raise classified
    # Defensive: should be unreachable because the loop either returns or raises.
    raise last_error or ProviderResponseError("Unknown fetch failure")


def fetch_multi_report(
    tickers: list[str],
    timeframe: str,
    provider: str | None = None,
    policy: FetchPolicy | None = None,
    sleeper: Callable[[float], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    status: Callable[[str], None] | None = None,
) -> FetchReport:
    """Fetch OHLCV data for ``tickers`` with retries and whole-batch fallback.

    The function tries ``provider`` first, then each provider in the configured
    fallback order. It stops at the first provider that produces at least one
    usable dataset. Failures are captured in the returned ``FetchReport`` and never
    swallowed silently.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {list(TIMEFRAMES)}")

    policy = policy or FetchPolicy()
    requested_provider = resolve_provider(provider)
    providers_to_try = (requested_provider,) + policy.fallback_for(requested_provider)

    total_fetch_attempted = 0
    all_failures: dict[str, ProviderError] = {}
    all_attempts: dict[str, int] = {}
    providers_attempted: list[str] = []

    remaining = list(tickers)
    data: dict[str, pd.DataFrame] = {}
    actual_provider: str | None = None
    fallback_used = False

    for p_idx, p in enumerate(providers_to_try):
        if not remaining:
            break
        providers_attempted.append(p)
        if p_idx > 0 and status is not None:
            status(f"Falling back to {p}")
        elif p_idx > 0:
            print(f"[fallback] Trying provider '{p}' for {len(remaining)} remaining tickers")

        provider_func = _PROVIDERS[p]
        remaining_next: list[str] = []
        any_success_this_provider = False

        for i, ticker in enumerate(remaining):
            all_attempts[ticker] = all_attempts.get(ticker, 0) + 1
            total_fetch_attempted += 1
            try:
                df = _fetch_with_retry(
                    lambda t=ticker, f=timeframe, pf=provider_func: pf(t, f),
                    policy,
                    sleeper=sleeper,
                )
            except ProviderError as e:
                all_failures[ticker] = e
                remaining_next.append(ticker)
                continue

            if df.empty or not _has_usable_ohlcv(df):
                # No usable data for this ticker from this provider.
                all_failures[ticker] = ProviderDataUnavailableError(
                    f"No usable OHLCV data for {ticker} ({timeframe}) from {p}"
                )
                remaining_next.append(ticker)
                continue

            data[ticker] = df
            all_failures.pop(ticker, None)
            any_success_this_provider = True

            if p_idx == 0 and progress is not None:
                progress(i + 1, len(tickers))

        if any_success_this_provider:
            actual_provider = p
            fallback_used = p != requested_provider
            # Whole-scan fallback stops at the first provider that produced any
            # usable data. The remaining tickers are reported as unavailable.
            break
        else:
            remaining = remaining_next

    return FetchReport(
        data=data,
        requested_provider=requested_provider,
        actual_provider=actual_provider,
        fallback_used=fallback_used,
        providers_attempted=tuple(providers_attempted),
        failures=all_failures,
        attempts=all_attempts,
        total_requested=len(tickers),
        total_fetched=len(data),
        total_fetch_attempted=total_fetch_attempted,
        retries=policy.max_retries,
    )


def _has_usable_ohlcv(df: pd.DataFrame) -> bool:
    """Return True if a DataFrame contains at least one usable OHLCV row."""
    return not df.empty and any(c in df.columns for c in ("close", "Close"))


# ── Public API ────────────────────────────────────────────────────────────────
_PROVIDERS = {
    "yahoo":  _fetch_yahoo,
    "alpaca": _fetch_alpaca,
    "ibkr":   _fetch_ibkr,
    "schwab": _fetch_schwab,
}


def resolve_provider(provider: str | None = None) -> str:
    """
    Resolve and normalize an OHLCV provider name.

    Args:
        provider: Explicit provider name, or None to use ``DATA_PROVIDER`` env var.

    Returns:
        A normalized lowercase provider string from ``{"yahoo", "alpaca", "ibkr", "schwab"}``.

    Raises:
        ValueError: If the provider is missing or not a supported OHLCV provider.
    """
    p = (provider if provider is not None else DEFAULT_PROVIDER).strip().lower()
    if p not in _PROVIDERS:
        raise ValueError(
            f"provider must be one of {sorted(_PROVIDERS)}; got {p!r}"
        )
    return p


def fetch(ticker: str, timeframe: str, provider: str | None = None) -> pd.DataFrame:
    """
    Fetch OHLCV data for a ticker.

    Args:
        ticker:    e.g. "NVDA"
        timeframe: "intraday" | "short" | "long"
        provider:  "yahoo" | "alpaca" | "ibkr" | "schwab" (defaults to DATA_PROVIDER env var, then "yahoo")
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {list(TIMEFRAMES)}")

    p = resolve_provider(provider)
    return _PROVIDERS[p](ticker, timeframe)


def fetch_multi(
    tickers: list[str],
    timeframe: str,
    provider: str | None = None,
    policy: FetchPolicy | None = None,
) -> FetchReport:
    """Fetch data for multiple tickers with retries and whole-batch fallback.

    Returns a ``FetchReport`` with successes, failures, and provenance metadata.
    New code should prefer ``fetch_multi_report``.
    """
    return fetch_multi_report(tickers, timeframe, provider=provider, policy=policy)
