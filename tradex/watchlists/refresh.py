"""
Refresh preset watchlists from the web.

Scrapes Wikipedia for S&P 500 / DJIA / NDX 100 constituents (which already
include GICS sector tags inline) plus the Russell 1000 page for a broader
US large+mid cap universe with sectors. Uses Schwab fundamentals for the
liquidity filter and yfinance for market-cap-based ranking.

Sector presets are built from the **Russell 1000 universe filtered for
liquidity** ($5 minimum price, 100k average daily volume) — not just S&P 500
members. This captures liquid names like PLTR, RDDT, CRWD, HOOD, SOFI, SMCI
that S&P 500-only filtering would miss.

Network-heavy — designed to be triggered explicitly via a UI button, not on
every dashboard load.
"""
from __future__ import annotations

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd
import requests
from dotenv import load_dotenv

# Load .env so SCHWAB_* credentials are available even when this module is
# called from a context that hasn't already loaded them (scripts, notebooks).
# Safe to call repeatedly.
load_dotenv()

log = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DOW_URL = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
NDX_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
RUSSELL1000_URL = "https://en.wikipedia.org/wiki/Russell_1000_Index"

# Wikipedia rejects pandas' default urllib UA with 403. Set a real UA.
_HTTP_HEADERS = {
    "User-Agent": "TradeX/0.1 (personal market scanner; +https://github.com/gyairbyte/TradeX)",
}

SECTOR_TOP_N = 100

# Liquidity floor for sector membership.
MIN_PRICE = 5.0
MIN_AVG_VOLUME = 100_000


@dataclass
class RefreshResult:
    sp500: list[str]
    dow30: list[str]
    ndx100: list[str]
    per_sector: dict[str, list[str]]
    sp100: list[str]
    warnings: list[str]
    russell1000: list[str] = None
    sector_universe_size: int = 0          # how many tickers passed the liquidity filter
    constituent_source: str = "wikipedia"  # S&P 500 / Dow / NDX / Russell 1000 source
    market_cap_source: str = "yahoo"     # market-cap ranking source


def _read_tables(url: str) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=_HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    if not tables:
        raise RuntimeError(f"no tables found at {url}")
    return tables


def _fetch_sp500() -> pd.DataFrame:
    df = _read_tables(SP500_URL)[0]
    df = df.rename(columns={c: c.strip() for c in df.columns})
    sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
    sec_col = "GICS Sector" if "GICS Sector" in df.columns else None
    out = pd.DataFrame({"ticker": df[sym_col].astype(str).str.replace(".", "-", regex=False)})
    if sec_col:
        out["sector"] = df[sec_col].astype(str)
    return out


def _fetch_dow() -> list[str]:
    for t in _read_tables(DOW_URL):
        cols = [c for c in t.columns if isinstance(c, str)]
        if any("Symbol" in c for c in cols):
            sym_col = next(c for c in cols if "Symbol" in c)
            return t[sym_col].astype(str).str.replace(".", "-", regex=False).tolist()
    raise RuntimeError("could not locate Dow components table")


def _fetch_ndx() -> list[str]:
    for t in _read_tables(NDX_URL):
        cols = [str(c) for c in t.columns]
        if any(c in ("Ticker", "Symbol") for c in cols):
            sym_col = next(c for c in cols if c in ("Ticker", "Symbol"))
            return t[sym_col].astype(str).str.replace(".", "-", regex=False).tolist()
    raise RuntimeError("could not locate NDX components table")


def _fetch_russell1000() -> pd.DataFrame:
    """Returns columns: ticker, sector. ~1000 rows of US large+mid cap with GICS tags."""
    for t in _read_tables(RUSSELL1000_URL):
        cols = [str(c) for c in t.columns]
        if "Symbol" in cols and "GICS Sector" in cols:
            df = pd.DataFrame({
                "ticker": t["Symbol"].astype(str).str.replace(".", "-", regex=False),
                "sector": t["GICS Sector"].astype(str),
            })
            return df
    raise RuntimeError("could not locate Russell 1000 components table on Wikipedia")


def _fetch_yahoo_market_caps(tickers: list[str], max_workers: int = 12) -> dict[str, float]:
    """Fetch market caps from Yahoo Finance fast_info."""
    import yfinance as yf

    caps: dict[str, float] = {}

    def _one(t: str) -> tuple[str, float | None]:
        try:
            info = yf.Ticker(t).fast_info
            cap = info.get("market_cap") if isinstance(info, dict) else getattr(info, "market_cap", None)
            return t, float(cap) if cap else None
        except Exception:
            log.debug("market cap fetch failed for %s", t)
            return t, None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for fut in as_completed(ex.submit(_one, t) for t in tickers):
            t, cap = fut.result()
            if cap is not None:
                caps[t] = cap
    return caps


def _fetch_schwab_market_caps(tickers: list[str]) -> dict[str, float]:
    """Fetch market caps from Schwab FUNDAMENTAL data."""
    from tradex.data.fetcher import ProviderCapabilityError

    caps: dict[str, float] = {}
    client = _schwab_client_or_none()
    if client is None:
        raise ProviderCapabilityError(
            "Schwab market-cap source selected but Schwab is not configured"
        )

    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i:i + batch_size]
        try:
            r = client.get_instruments(chunk, client.Instrument.Projection.FUNDAMENTAL)
            r.raise_for_status()
            inst_list = r.json().get("instruments", [])
        except Exception:
            log.debug("Schwab market-cap batch %s failed", chunk[0] if chunk else "")
            continue

        for it in inst_list:
            sym = it.get("symbol")
            fundamental = it.get("fundamental", {}) if isinstance(it, dict) else {}
            cap = fundamental.get("marketCap") or fundamental.get("marketcap")
            if sym and cap:
                try:
                    caps[sym] = float(cap)
                except (TypeError, ValueError):
                    continue
    return caps


def _resolve_market_cap_source(source: str | None) -> str:
    return (source or os.getenv("MARKET_CAP_DATA_SOURCE", "yahoo")).lower().strip()


def fetch_market_caps(
    tickers: list[str], source: str | None = None, max_workers: int = 12
) -> dict[str, float]:
    """Fetch market caps for ``tickers`` from an explicit source.

    Supported sources:
      - ``yahoo``  (default): Yahoo Finance fast_info
      - ``schwab``: Schwab FUNDAMENTAL data (requires Schwab credentials)

    ``DATA_PROVIDER`` is not used for market-cap data.
    """
    from tradex.data.fetcher import ProviderCapabilityError

    s = _resolve_market_cap_source(source)
    if s == "yahoo":
        return _fetch_yahoo_market_caps(tickers, max_workers=max_workers)
    if s == "schwab":
        return _fetch_schwab_market_caps(tickers)
    raise ProviderCapabilityError(
        f"Market-cap source '{s}' is not supported; supported: yahoo, schwab"
    )


def _schwab_client_or_none():
    """Return an authenticated Schwab client if available, else None.

    The liquidity filter degrades to "no filter" if Schwab isn't configured —
    sector presets still build, just with the full unfiltered Russell 1000.
    """
    try:
        from schwab.auth import client_from_token_file
    except ImportError:
        return None
    app_key = os.getenv("SCHWAB_APP_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    token_path = os.path.expanduser(
        os.getenv("SCHWAB_TOKEN_PATH", "~/.tradex_schwab_token.json")
    )
    if not (app_key and app_secret and os.path.exists(token_path)):
        return None
    try:
        return client_from_token_file(
            token_path=token_path, api_key=app_key, app_secret=app_secret,
        )
    except Exception:
        log.warning("schwab client init failed for liquidity filter")
        return None


def _schwab_liquidity_filter(
    tickers: list[str],
    min_price: float = MIN_PRICE,
    min_avg_volume: int = MIN_AVG_VOLUME,
    batch_size: int = 100,
) -> tuple[set[str], list[str]]:
    """Return (set of tickers passing filter, list of warnings).

    Calls Schwab get_instruments (FUNDAMENTAL) for avg3MonthVolume and
    get_quotes for current price. Both are batched.
    """
    warnings: list[str] = []
    client = _schwab_client_or_none()
    if client is None:
        warnings.append(
            "Schwab not configured — skipping liquidity filter. "
            "Sector presets will include all Russell 1000 members."
        )
        return set(tickers), warnings

    survivors: set[str] = set()
    n_priced = 0
    n_volumed = 0

    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i:i + batch_size]
        # Fundamentals → avg3MonthVolume
        try:
            r1 = client.get_instruments(chunk, client.Instrument.Projection.FUNDAMENTAL)
            r1.raise_for_status()
            inst_list = r1.json().get("instruments", [])
        except Exception:
            warnings.append(f"Schwab fundamentals batch {i}-{i + batch_size} failed")
            log.debug("Schwab fundamentals batch %s failed", i)
            continue

        vol_map = {
            it["symbol"]: it.get("fundamental", {}).get("avg3MonthVolume")
            for it in inst_list
        }
        n_volumed += sum(1 for v in vol_map.values() if v is not None)

        # Quotes → lastPrice
        try:
            r2 = client.get_quotes(chunk)
            r2.raise_for_status()
            quote_map = r2.json()
        except Exception:
            warnings.append(f"Schwab quotes batch {i}-{i + batch_size} failed")
            log.debug("Schwab quotes batch %s failed", i)
            continue

        for sym in chunk:
            vol = vol_map.get(sym)
            price = quote_map.get(sym, {}).get("quote", {}).get("lastPrice")
            if price is not None:
                n_priced += 1
            if vol is None or price is None:
                continue
            if price >= min_price and vol >= min_avg_volume:
                survivors.add(sym)

    if n_priced < len(tickers) * 0.9:
        warnings.append(
            f"Schwab returned price data for only {n_priced}/{len(tickers)} tickers. "
            "Some may be missing from sector presets."
        )
    return survivors, warnings


def refresh_all(
    top_n_per_sector: int = SECTOR_TOP_N, market_cap_source: str | None = None
) -> RefreshResult:
    warnings: list[str] = []

    # ── Index lists (still useful as their own presets) ─────────────────────
    try:
        sp500_df = _fetch_sp500()
    except Exception as e:
        raise RuntimeError(f"S&P 500 fetch failed: {e}") from e

    try:
        dow30 = _fetch_dow()
    except Exception as e:
        warnings.append(f"Dow 30 fetch failed: {e}")
        dow30 = []

    try:
        ndx100 = _fetch_ndx()
    except Exception as e:
        warnings.append(f"NDX 100 fetch failed: {e}")
        ndx100 = []

    # ── Russell 1000 (the broad-US-market source for sectors) ───────────────
    try:
        r1k_df = _fetch_russell1000()
    except Exception as e:
        warnings.append(f"Russell 1000 fetch failed ({e}) — falling back to S&P 500 for sectors")
        r1k_df = sp500_df.copy()

    # ── Market caps for SP100 ranking ───────────────────────────────────────
    resolved_cap_source = _resolve_market_cap_source(market_cap_source)
    try:
        caps = fetch_market_caps(sp500_df["ticker"].tolist(), source=resolved_cap_source)
    except Exception:
        caps = {}
        warnings.append(f"Market-cap fetch failed for source '{resolved_cap_source}'")
    sp500_df["market_cap"] = sp500_df["ticker"].map(caps).fillna(0)
    if (sp500_df["market_cap"] == 0).any():
        n_missing = int((sp500_df["market_cap"] == 0).sum())
        warnings.append(f"market cap unavailable for {n_missing} S&P 500 tickers — ranked last")
    sp100 = sp500_df.sort_values("market_cap", ascending=False).head(100)["ticker"].tolist()

    # ── Sector presets: Russell 1000 → liquidity filter → group by GICS ─────
    universe_tickers = r1k_df["ticker"].dropna().unique().tolist()
    survivors, filter_warnings = _schwab_liquidity_filter(universe_tickers)
    warnings.extend(filter_warnings)

    filtered_df = r1k_df[r1k_df["ticker"].isin(survivors)].copy()

    per_sector: dict[str, list[str]] = {}
    if "sector" in filtered_df.columns and not filtered_df.empty:
        # No yfinance market-cap call for sectors — sort by ticker alpha for now.
        # (Rationale: we'd pay another ~1000 yfinance calls just to sort within sectors
        # that are already capped at top_n_per_sector. Not worth the time.)
        for sector, group in filtered_df.groupby("sector"):
            tickers = sorted(group["ticker"].unique().tolist())
            per_sector[sector] = tickers[:top_n_per_sector]
    else:
        warnings.append("no GICS sector data after filtering — per-sector lists not refreshed")

    return RefreshResult(
        sp500=sp500_df["ticker"].tolist(),
        dow30=dow30,
        ndx100=ndx100,
        per_sector=per_sector,
        sp100=sp100,
        warnings=warnings,
        russell1000=r1k_df["ticker"].tolist(),
        sector_universe_size=len(survivors),
        constituent_source="wikipedia",
        market_cap_source=resolved_cap_source,
    )


SECTOR_TO_PRESET_KEY = {
    "Information Technology": "sector_tech",
    "Health Care": "sector_healthcare",
    "Financials": "sector_financials",
    "Consumer Discretionary": "sector_consumer_disc",
    "Consumer Staples": "sector_consumer_staples",
    "Energy": "sector_energy",
    "Industrials": "sector_industrials",
    "Materials": "sector_materials",
    "Utilities": "sector_utilities",
    "Real Estate": "sector_real_estate",
    "Communication Services": "sector_comms",
}


def result_to_preset_overrides(result: RefreshResult) -> dict[str, list[str]]:
    """Map a RefreshResult into {preset_key: tickers} for everything we can refresh."""
    out: dict[str, list[str]] = {}
    if result.sp500:
        out["sp500"] = result.sp500
    if result.sp100:
        out["sp100"] = result.sp100
    if result.dow30:
        out["dow30"] = result.dow30
    if result.ndx100:
        out["ndx100"] = result.ndx100
    for sector, tickers in result.per_sector.items():
        key = SECTOR_TO_PRESET_KEY.get(sector)
        if key:
            out[key] = tickers
    return out
