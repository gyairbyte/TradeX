"""Market data provider abstraction and concrete adapters for the ORB opportunity scanner.

Provides:
- ORBMarketDataProvider: Protocol defining discovery and batched data retrieval.
- MockORBProvider: Deterministic, credential-free, network-free mock provider for tests and offline execution.
- AlpacaORBProvider: Multi-symbol Alpaca adapter with asset discovery, batching, and SIP/IEX feed detection.
- SchwabORBProviderStub: Explicit limitation handler explaining why Schwab cannot support broad-market discovery.
- resolve_orb_provider: Factory resolving the appropriate provider based on settings or explicit provider name.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as dt_time
from typing import Any, Protocol, runtime_checkable

import requests

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.market.hours import MARKET_TIMEZONE

from .models import DailyBar, MinuteBar, OpeningRangeVolumeObservation

logger = logging.getLogger(__name__)

DEFAULT_ALPACA_BATCH_SIZE = 100
DEFAULT_ALPACA_DATA_URL = "https://data.alpaca.markets"
DEFAULT_ALPACA_ASSETS_URL = "https://paper-api.alpaca.markets"


class ORBProviderError(RuntimeError):
    """Base exception for ORB provider failures."""


class ORBProviderConfigurationError(ORBProviderError):
    """Raised for missing credentials or misconfigured providers."""


class ORBProviderRateLimitError(ORBProviderError):
    """Raised when provider rate limits are exceeded."""


class ORBProviderDataUnavailableError(ORBProviderError):
    """Raised when data cannot be retrieved from the provider."""


@runtime_checkable
class ORBMarketDataProvider(Protocol):
    """Protocol for ORB market data providers supporting broad discovery."""

    @property
    def provider_name(self) -> str:
        """Canonical provider name (e.g. 'alpaca', 'mock')."""
        ...

    @property
    def feed_name(self) -> str:
        """Market data feed (e.g. 'sip', 'iex', 'mock')."""
        ...

    @property
    def is_feed_consolidated(self) -> bool:
        """True if consolidated tape (SIP), False if exchange-specific (IEX) or synthetic."""
        ...

    @property
    def feed_disclosure(self) -> str:
        """Human-readable disclosure describing feed characteristics and limitations."""
        ...

    def discover_universe(self) -> list[str]:
        """Discover the broad U.S. equities universe on NYSE and Nasdaq.

        Returns:
            Sorted list of canonical uppercase ticker symbols.
        """
        ...

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyBar]]:
        """Fetch daily regular-session OHLCV bars across requested symbols.

        Returns:
            Dict mapping symbol -> list of DailyBar sorted chronologically.
        """
        ...

    def fetch_opening_range_bars(
        self,
        symbols: list[str],
        session_date: date,
    ) -> dict[str, list[MinuteBar]]:
        """Fetch regular-session 09:30-09:34 ET 1-minute bars for session_date.

        Returns:
            Dict mapping symbol -> list of MinuteBar sorted chronologically.
        """
        ...

    def fetch_prior_opening_range_volumes(
        self,
        symbols: list[str],
        prior_sessions: list[date],
    ) -> dict[str, list[OpeningRangeVolumeObservation]]:
        """Fetch 09:30-09:34 ET regular-session opening-range volume for prior sessions.

        Returns:
            Dict mapping symbol -> list of OpeningRangeVolumeObservation.
        """
        ...


@dataclass
class MockORBProvider:
    """Deterministic, credential-free, network-free mock provider for testing and offline execution."""

    symbols: list[str] = field(default_factory=list)
    daily_bars: dict[str, list[DailyBar]] = field(default_factory=dict)
    opening_range_bars: dict[str, list[MinuteBar]] = field(default_factory=dict)
    prior_opening_range_volumes: dict[str, list[OpeningRangeVolumeObservation]] = field(default_factory=dict)
    provider_name: str = "mock"
    feed_name: str = "sip"
    is_feed_consolidated: bool = True
    feed_disclosure: str = "Deterministic test fixture; simulated consolidated SIP feed."
    simulate_rate_limit: bool = False
    rate_limit_call_count: int = 0
    fail_stage: str | None = None

    @classmethod
    def create_populated(cls) -> MockORBProvider:
        """Create a mock provider seeded with the deterministic 33-symbol synthetic demo fixture."""
        from .demo_fixture import create_demo_snapshot

        snap = create_demo_snapshot()
        symbols = sorted(snap.symbols.keys())
        daily_bars = {sym: p.daily_bars for sym, p in snap.symbols.items()}
        or_bars = {sym: p.opening_range_bars for sym, p in snap.symbols.items()}
        prior_vols = {sym: p.prior_opening_range_volumes for sym, p in snap.symbols.items()}
        return cls(
            symbols=symbols,
            daily_bars=daily_bars,
            opening_range_bars=or_bars,
            prior_opening_range_volumes=prior_vols,
            provider_name="mock",
            feed_name="sip",
            is_feed_consolidated=True,
            feed_disclosure="Deterministic Mock Provider (Simulated 33-Symbol Research Universe)",
        )

    def discover_universe(self) -> list[str]:
        if self.fail_stage == "DISCOVERY":
            raise ORBProviderDataUnavailableError("Simulated mock discovery failure at Stage 1")
        if self.symbols:
            return sorted({s.strip().upper() for s in self.symbols})
        # Default mock universe if none provided
        return sorted(set(list(self.daily_bars.keys()) + list(self.opening_range_bars.keys())))

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyBar]]:
        if self.fail_stage == "DAILY_ELIGIBILITY":
            raise ORBProviderDataUnavailableError("Simulated mock daily bars failure at Stage 2")
        result: dict[str, list[DailyBar]] = {}
        for sym in symbols:
            s_clean = sym.strip().upper()
            bars = self.daily_bars.get(s_clean, [])
            filtered = [b for b in bars if start_date <= b.session_date <= end_date]
            result[s_clean] = sorted(filtered, key=lambda x: x.session_date)
        return result

    def fetch_opening_range_bars(
        self,
        symbols: list[str],
        session_date: date,
    ) -> dict[str, list[MinuteBar]]:
        if self.fail_stage == "OPENING_RANGE":
            raise ORBProviderDataUnavailableError("Simulated mock opening range failure at Stage 3")
        result: dict[str, list[MinuteBar]] = {}
        for sym in symbols:
            s_clean = sym.strip().upper()
            bars = self.opening_range_bars.get(s_clean, [])
            filtered = [
                b for b in bars
                if b.timestamp.astimezone(MARKET_TIMEZONE).date() == session_date
            ]
            result[s_clean] = sorted(filtered, key=lambda x: x.timestamp)
        return result

    def fetch_prior_opening_range_volumes(
        self,
        symbols: list[str],
        prior_sessions: list[date],
    ) -> dict[str, list[OpeningRangeVolumeObservation]]:
        result: dict[str, list[OpeningRangeVolumeObservation]] = {}
        req_dates = set(prior_sessions)
        for sym in symbols:
            s_clean = sym.strip().upper()
            obs_list = self.prior_opening_range_volumes.get(s_clean, [])
            filtered = [o for o in obs_list if o.session_date in req_dates]
            result[s_clean] = sorted(filtered, key=lambda x: x.session_date)
        return result


class AlpacaORBProvider:
    """Multi-symbol Alpaca market data provider supporting broad U.S. equities discovery."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        feed: str = "sip",
        base_url: str = DEFAULT_ALPACA_ASSETS_URL,
        data_url: str = DEFAULT_ALPACA_DATA_URL,
        batch_size: int = DEFAULT_ALPACA_BATCH_SIZE,
        request_func: Callable[..., requests.Response] | None = None,
        max_retries: int = 3,
        rate_limit_pause_seconds: float = 0.5,
    ) -> None:
        if not api_key or not secret_key:
            raise ORBProviderConfigurationError(
                "Alpaca credentials missing: ALPACA_API_KEY and ALPACA_SECRET_KEY must be configured."
            )
        self.api_key = api_key
        self.secret_key = secret_key
        self._feed = feed.strip().lower()
        self.base_url = base_url.rstrip("/")
        self.data_url = data_url.rstrip("/")
        self.batch_size = max(1, batch_size)
        self.max_retries = max_retries
        self.rate_limit_pause_seconds = rate_limit_pause_seconds
        self._is_feed_consolidated = (self._feed == "sip")

        if request_func is not None:
            self._request_func = request_func
        else:
            self._session = requests.Session()
            self._request_func = self._session.get

    @property
    def provider_name(self) -> str:
        return "alpaca"

    @property
    def feed_name(self) -> str:
        return self._feed

    @property
    def is_feed_consolidated(self) -> bool:
        return self._is_feed_consolidated

    @property
    def feed_disclosure(self) -> str:
        if self._is_feed_consolidated:
            return "Alpaca Consolidated Tape (SIP) — full volume across all U.S. stock exchanges."
        return (
            "Alpaca Free Tier (IEX Feed Only) — captures ~2% of market volume. "
            "Relative volume and candidate rankings are provisional heuristics and do not reflect consolidated SIP volume."
        )

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Accept": "application/json",
        }

    def _get_with_retry(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        """Execute HTTP GET with deterministic backoff and 429 rate limit handling."""
        last_resp: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._request_func(url, headers=self._headers(), params=params, timeout=30)
                last_resp = resp
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    pause = float(retry_after) if retry_after else min(2.0 ** attempt, 8.0)
                    time.sleep(pause)
                    continue
                if resp.status_code == 403:
                    req_feed = params.get("feed", self._feed) if params else self._feed
                    raise ORBProviderConfigurationError(
                        f"Alpaca feed entitlement error (HTTP 403 Forbidden for feed='{req_feed}'). "
                        "The configured account lacks entitlement for this market data feed. "
                        "TradeX enforces consistent, non-mixed feeds throughout a scan. "
                        "To perform an explicit provisional heuristic scan, select feed='iex' explicitly before scanning."
                    )
                if resp.status_code == 401:
                    raise ORBProviderConfigurationError(
                        "Alpaca authentication error (HTTP 401 Unauthorized): invalid API credentials."
                    )
                if resp.status_code >= 500:
                    time.sleep(min(1.0 + attempt, 4.0))
                    continue
                resp.raise_for_status()
            except requests.RequestException as err:
                if attempt == self.max_retries:
                    raise ORBProviderDataUnavailableError(f"Alpaca request failed after {attempt} retries: {err}") from err
                time.sleep(min(1.0 + attempt, 4.0))

        if last_resp is not None:
            raise ORBProviderDataUnavailableError(
                f"Alpaca request failed with status HTTP {last_resp.status_code}"
            )
        raise ORBProviderDataUnavailableError("Alpaca request failed without response")

    def discover_universe(self) -> list[str]:
        """Discover all active U.S. equities on NYSE and Nasdaq from Alpaca Assets endpoint."""
        url = f"{self.base_url}/v2/assets"
        params = {"status": "active", "asset_class": "us_equity"}
        resp = self._get_with_retry(url, params=params)
        try:
            data = resp.json()
        except ValueError as err:
            raise ORBProviderDataUnavailableError("Malformed JSON response from Alpaca assets endpoint") from err

        if not isinstance(data, list):
            raise ORBProviderDataUnavailableError(f"Unexpected Alpaca assets response shape: expected list, got {type(data)}")

        target_exchanges = {"NYSE", "NASDAQ"}
        discovered: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            exchange = item.get("exchange", "").upper()
            status = item.get("status", "").lower()
            if symbol and exchange in target_exchanges and status == "active":
                # Filter out obvious test tickers, warrants with special chars if needed, but preserve clean tickers
                clean_sym = symbol.strip().upper()
                if clean_sym and not clean_sym.startswith("$"):
                    discovered.append(clean_sym)

        return sorted(set(discovered))

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyBar]]:
        """Fetch daily regular-session OHLCV bars across requested symbols in batches."""
        result: dict[str, list[DailyBar]] = {s.strip().upper(): [] for s in symbols}
        clean_symbols = sorted({s.strip().upper() for s in symbols})
        if not clean_symbols:
            return result

        url = f"{self.data_url}/v2/stocks/bars"
        # Alpaca expects ISO 8601 timestamps in UTC
        start_ts = f"{start_date.isoformat()}T00:00:00Z"
        end_ts = f"{end_date.isoformat()}T23:59:59Z"

        for i in range(0, len(clean_symbols), self.batch_size):
            batch = clean_symbols[i : i + self.batch_size]
            params: dict[str, Any] = {
                "symbols": ",".join(batch),
                "timeframe": "1Day",
                "feed": self._feed,
                "adjustment": "raw",
                "start": start_ts,
                "end": end_ts,
                "limit": 10000,
            }
            seen_tokens: set[str] = set()
            max_pages = 50
            page_count = 0

            while True:
                resp = self._get_with_retry(url, params=params)
                try:
                    data = resp.json()
                except ValueError as err:
                    raise ORBProviderDataUnavailableError(f"Malformed daily bars JSON from Alpaca: {err}") from err

                bars_by_symbol = data.get("bars", {}) if isinstance(data, dict) else {}
                if isinstance(bars_by_symbol, dict):
                    for sym, raw_bars in bars_by_symbol.items():
                        sym_clean = sym.strip().upper()
                        if sym_clean not in result:
                            result[sym_clean] = []
                        for b in raw_bars:
                            try:
                                raw_t = b["t"]
                                ts = datetime.fromisoformat(raw_t)
                                bar_date = ts.astimezone(MARKET_TIMEZONE).date()
                                result[sym_clean].append(
                                    DailyBar(
                                        symbol=sym_clean,
                                        session_date=bar_date,
                                        open=float(b.get("o", b.get("open", 0.0))),
                                        high=float(b.get("h", b.get("high", 0.0))),
                                        low=float(b.get("l", b.get("low", 0.0))),
                                        close=float(b.get("c", b.get("close", 0.0))),
                                        volume=float(b.get("v", b.get("volume", 0.0))),
                                    )
                                )
                            except (KeyError, ValueError, TypeError):
                                continue

                next_token = data.get("next_page_token") if isinstance(data, dict) else None
                if not next_token:
                    break
                if next_token in seen_tokens:
                    raise ORBProviderDataUnavailableError(
                        f"Pagination cycle detected from Alpaca API for batch: {next_token}"
                    )
                seen_tokens.add(next_token)
                page_count += 1
                if page_count >= max_pages:
                    raise ORBProviderDataUnavailableError(
                        f"Exceeded maximum page limit ({max_pages}) during Alpaca pagination"
                    )
                params["page_token"] = next_token

            if self.rate_limit_pause_seconds > 0:
                time.sleep(self.rate_limit_pause_seconds)

        # Sort and deduplicate bars per symbol
        for sym_clean, bars_list in result.items():
            seen_dates: set[date] = set()
            deduped_bars: list[DailyBar] = []
            for b in sorted(bars_list, key=lambda x: x.session_date):
                if b.session_date not in seen_dates:
                    seen_dates.add(b.session_date)
                    deduped_bars.append(b)
            result[sym_clean] = deduped_bars

        return result

    def fetch_opening_range_bars(
        self,
        symbols: list[str],
        session_date: date,
    ) -> dict[str, list[MinuteBar]]:
        """Fetch regular-session 09:30-09:34 ET 1-minute bars for session_date."""
        result: dict[str, list[MinuteBar]] = {s.strip().upper(): [] for s in symbols}
        clean_symbols = sorted({s.strip().upper() for s in symbols})
        if not clean_symbols:
            return result

        # 09:30 to 09:34 ET window converted to UTC
        start_et = datetime.combine(session_date, dt_time(9, 30), tzinfo=MARKET_TIMEZONE)
        end_et = datetime.combine(session_date, dt_time(9, 34, 59), tzinfo=MARKET_TIMEZONE)
        start_utc = start_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{self.data_url}/v2/stocks/bars"

        for i in range(0, len(clean_symbols), self.batch_size):
            batch = clean_symbols[i : i + self.batch_size]
            params: dict[str, Any] = {
                "symbols": ",".join(batch),
                "timeframe": "1Min",
                "feed": self._feed,
                "adjustment": "raw",
                "start": start_utc,
                "end": end_utc,
                "limit": 10000,
            }
            seen_tokens: set[str] = set()
            max_pages = 50
            page_count = 0

            while True:
                resp = self._get_with_retry(url, params=params)
                try:
                    data = resp.json()
                except ValueError as err:
                    raise ORBProviderDataUnavailableError(f"Malformed minute bars JSON from Alpaca: {err}") from err

                bars_by_symbol = data.get("bars", {}) if isinstance(data, dict) else {}
                if isinstance(bars_by_symbol, dict):
                    for sym, raw_bars in bars_by_symbol.items():
                        sym_clean = sym.strip().upper()
                        if sym_clean not in result:
                            result[sym_clean] = []
                        for b in raw_bars:
                            try:
                                raw_t = b["t"]
                                ts = datetime.fromisoformat(raw_t)
                                bar_date = ts.astimezone(MARKET_TIMEZONE).date()
                                result[sym_clean].append(
                                    MinuteBar(
                                        symbol=sym_clean,
                                        timestamp=ts,
                                        session_date=bar_date,
                                        open=float(b.get("o", b.get("open", 0.0))),
                                        high=float(b.get("h", b.get("high", 0.0))),
                                        low=float(b.get("l", b.get("low", 0.0))),
                                        close=float(b.get("c", b.get("close", 0.0))),
                                        volume=float(b.get("v", b.get("volume", 0.0))),
                                    )
                                )
                            except (KeyError, ValueError, TypeError):
                                continue

                next_token = data.get("next_page_token") if isinstance(data, dict) else None
                if not next_token:
                    break
                if next_token in seen_tokens:
                    raise ORBProviderDataUnavailableError(
                        f"Pagination cycle detected from Alpaca API for batch: {next_token}"
                    )
                seen_tokens.add(next_token)
                page_count += 1
                if page_count >= max_pages:
                    raise ORBProviderDataUnavailableError(
                        f"Exceeded maximum page limit ({max_pages}) during Alpaca pagination"
                    )
                params["page_token"] = next_token

            if self.rate_limit_pause_seconds > 0:
                time.sleep(self.rate_limit_pause_seconds)

        # Sort and deduplicate bars per symbol
        for sym_clean, bars_list in result.items():
            seen_ts: set[datetime] = set()
            deduped_mb: list[MinuteBar] = []
            for b in sorted(bars_list, key=lambda x: x.timestamp):
                if b.timestamp not in seen_ts:
                    seen_ts.add(b.timestamp)
                    deduped_mb.append(b)
            result[sym_clean] = deduped_mb

        return result

    def fetch_prior_opening_range_volumes(
        self,
        symbols: list[str],
        prior_sessions: list[date],
    ) -> dict[str, list[OpeningRangeVolumeObservation]]:
        """Fetch 09:30-09:34 ET regular-session opening-range volume for exact prior sessions."""
        result: dict[str, list[OpeningRangeVolumeObservation]] = {s.strip().upper(): [] for s in symbols}
        clean_symbols = sorted({s.strip().upper() for s in symbols})
        if not clean_symbols or not prior_sessions:
            return result

        # Query session by session to strictly bound to 09:30-09:34 ET without pulling full-day data
        for p_date in prior_sessions:
            or_bars_by_sym = self.fetch_opening_range_bars(clean_symbols, p_date)
            for sym, bars in or_bars_by_sym.items():
                if bars:
                    # Sum 1-minute volumes across 09:30-09:34 ET
                    tot_vol = sum(b.volume for b in bars)
                    result[sym].append(
                        OpeningRangeVolumeObservation(
                            symbol=sym,
                            session_date=p_date,
                            volume=tot_vol,
                        )
                    )

        # Sort observations chronologically per symbol
        for obs_list in result.values():
            obs_list.sort(key=lambda x: x.session_date)

        return result


class SchwabORBProviderStub:
    """Explicit limitation stub explaining why Schwab cannot support broad-market discovery."""

    def __init__(self, settings: TradeXSettings | None = None) -> None:
        self.settings = settings

    @property
    def provider_name(self) -> str:
        return "schwab"

    @property
    def feed_name(self) -> str:
        return "schwab_b2c"

    @property
    def is_feed_consolidated(self) -> bool:
        return True

    @property
    def feed_disclosure(self) -> str:
        return "Charles Schwab Market Data API — single-symbol price history only (unsupported for market-wide discovery)."

    def discover_universe(self) -> list[str]:
        raise ORBProviderConfigurationError(
            "The Schwab Market Data API does not provide a market universe endpoint to list NYSE/Nasdaq equities. "
            "Broad-market discovery requires Alpaca credentials (ALPACA_API_KEY / ALPACA_SECRET_KEY) or Mock provider."
        )

    def fetch_daily_bars(self, symbols: list[str], start_date: date, end_date: date) -> dict[str, list[DailyBar]]:
        raise ORBProviderConfigurationError(
            "The Schwab price history API (/marketdata/v1/pricehistory) only supports single-symbol queries. "
            "Scanning ~8,000 stocks at Schwab's 120 calls/min rate limit would take >66 minutes. "
            "Please use Alpaca for market-wide scanning."
        )

    def fetch_opening_range_bars(self, symbols: list[str], session_date: date) -> dict[str, list[MinuteBar]]:
        raise ORBProviderConfigurationError("Schwab cannot support market-wide intraday retrieval.")

    def fetch_prior_opening_range_volumes(
        self, symbols: list[str], prior_sessions: list[date]
    ) -> dict[str, list[OpeningRangeVolumeObservation]]:
        raise ORBProviderConfigurationError("Schwab cannot support market-wide prior opening volume retrieval.")


def resolve_orb_provider(
    settings: TradeXSettings | None = None,
    provider_name: str | None = None,
    *,
    feed: str | None = None,
    mock_provider: MockORBProvider | None = None,
) -> ORBMarketDataProvider:
    """Factory resolving the active ORB provider with fail-safe configuration."""
    if mock_provider is not None:
        return mock_provider

    if settings is None:
        settings = load_runtime_settings()

    req_name = (provider_name or settings.data.data_provider).strip().lower()

    if req_name == "mock":
        return MockORBProvider.create_populated()

    if req_name == "alpaca":
        api_key = settings.data.alpaca_api_key
        secret_key = settings.data.alpaca_secret_key
        if not api_key or not secret_key:
            raise ORBProviderConfigurationError(
                "Alpaca credentials missing in settings: set ALPACA_API_KEY and ALPACA_SECRET_KEY in your .env file."
            )
        resolved_feed = (feed or "sip").strip().lower()
        return AlpacaORBProvider(api_key=api_key, secret_key=secret_key, feed=resolved_feed)

    if req_name == "schwab":
        return SchwabORBProviderStub(settings=settings)

    raise ORBProviderConfigurationError(
        f"Unsupported provider '{req_name}' for ORB market scanning. Supported providers: 'alpaca', 'mock'."
    )
