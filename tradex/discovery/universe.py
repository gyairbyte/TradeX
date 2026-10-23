"""Universe discovery and resolution for TradeX scan scopes (LONG-MVP-003).

Provides deterministic resolution and provenance tracking for:
  - My Watchlist (user active watchlist)
  - S&P 500 (TradeX preset or refreshed store constituents)
  - Nasdaq 100 (TradeX preset or refreshed store constituents)
  - All U.S. Listed Stocks (official Nasdaq Trader Symbol Directories)

Inclusion and Exclusion Policy:
  - Sourced simultaneously from both Nasdaq Trader directories:
      * nasdaqlisted.txt (Nasdaq-listed securities)
      * otherlisted.txt (NYSE, NYSE American, NYSE Arca, BATS, etc.)
  - Header validation and footer timestamp extraction.
  - Excludes test issues (Test Issue == 'Y').
  - Excludes ETFs (ETF == 'Y' or NextShares == 'Y').
  - Excludes warrants, rights, units, preferred instruments, notes, and debt
    using conservative, documented symbol-pattern and security-name rules.
  - Normalizes unambiguous share-class delimiters (e.g. BRK.B -> BRK-B).
  - Reports unsupported or ambiguous symbols without guessing or hallucinating.
  - Returns a deterministically sorted, deduplicated universe with full provenance.
  - Caches valid snapshots and preserves last-known good snapshot on source failure.
  - Never silently substitutes a narrower index universe for All U.S. Listed Stocks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tradex.config import TradeXSettings, load_runtime_settings
from tradex.discovery.models import Scope, UniverseProvenance
from tradex.watchlists import presets as wl_presets
from tradex.watchlists import store as wl_store

logger = logging.getLogger(__name__)

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

UNIVERSE_FRESHNESS_HOURS = 24
NETWORK_TIMEOUT_SECONDS = 15.0


class UniverseSourceError(RuntimeError):
    """Raised when a universe source fails or returns malformed data."""


# Regex for share-class normalization (e.g. BRK.B or BRK B -> BRK-B)
_SHARE_CLASS_RE = re.compile(r"^([A-Z]{1,5})[.\s/]([A-Z]{1,2})$")

# Standard normalized US ticker symbol: 1-5 letters, optional hyphen share class
_VALID_NORMALIZED_TICKER_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,2})?$")

# Exclusion patterns for security name
_WARRANT_NAME_RE = re.compile(r"\b(warrant|warrants|wts?)\b", re.IGNORECASE)
_RIGHTS_NAME_RE = re.compile(r"\b(rights?|rts?)\b", re.IGNORECASE)
_UNIT_NAME_RE = re.compile(r"\b(units?|uts?)\b", re.IGNORECASE)
_PREFERRED_NAME_RE = re.compile(
    r"\b(preferred|pref|prf|depositary\s+shares?|depositary\s+receipts?|dep\s+shs?)\b",
    re.IGNORECASE,
)
_NOTE_NAME_RE = re.compile(
    r"\b(notes?|debentures?|senior\s+notes?|subordinated\s+notes?|etn|exchange\s+traded\s+notes?)\b",
    re.IGNORECASE,
)


def _default_http_fetcher(url: str, timeout: float = NETWORK_TIMEOUT_SECONDS) -> str:
    """Fetch URL contents over HTTPS with bounded timeout."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TradeX/0.1 (Market-Discovery-Ingestion)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise UniverseSourceError(f"HTTP error {status} fetching {url}")
        charset = response.headers.get_content_charset() or "utf-8"
        raw_bytes = response.read()
        return raw_bytes.decode(charset, errors="replace")


def _parse_footer_timestamp(footer_line: str) -> str | None:
    """Parse 'File Creation Time: MMDDYYYYHHMM' into an ISO timestamp or safe string."""
    if not footer_line.startswith("File Creation Time:"):
        return None
    time_part = footer_line.replace("File Creation Time:", "").split("|")[0].strip()
    if len(time_part) == 12 and time_part.isdigit():
        try:
            # MMDDYYYYHHMM
            month = int(time_part[0:2])
            day = int(time_part[2:4])
            year = int(time_part[4:8])
            hour = int(time_part[8:10])
            minute = int(time_part[10:12])
            dt = datetime(year, month, day, hour, minute, tzinfo=UTC)
            return dt.isoformat()
        except ValueError:
            pass
    return time_part or None


def _classify_symbol_and_name(
    symbol_raw: str,
    name_raw: str,
    is_test: bool,
    is_etf: bool,
    exchange_source: str,
) -> tuple[str | None, str | None]:
    """Classify an instrument record.

    Returns:
      (normalized_symbol, None) if included as common stock.
      (None, exclusion_reason) if excluded.
      (None, "unsupported") if ambiguous or un-parseable symbol.
    """
    if is_test:
        return None, "test_issue"
    if is_etf:
        return None, "etf"

    sym = symbol_raw.strip().upper()
    name = name_raw.strip()

    # Name-based conservative non-common-stock exclusions
    if _PREFERRED_NAME_RE.search(name):
        return None, "preferred"
    if _WARRANT_NAME_RE.search(name):
        return None, "warrant"
    if _RIGHTS_NAME_RE.search(name):
        return None, "right"
    if _UNIT_NAME_RE.search(name):
        return None, "unit"
    if _NOTE_NAME_RE.search(name):
        return None, "note"

    # Symbol-based structural exclusions
    if "$" in sym or ".PR" in sym or "-P" in sym or re.search(r"p[A-Z]$", sym):
        return None, "preferred"
    if "+" in sym or sym.endswith((".WS", ".W", ".WT")):
        return None, "warrant"
    if sym.endswith((".RT", ".R")):
        return None, "right"
    if "=" in sym or sym.endswith((".U", ".UN", ".UT")):
        return None, "unit"

    # Nasdaq 5-letter fifth-character suffix conventions
    if exchange_source == "nasdaq" and len(sym) == 5:
        fifth = sym[4]
        if fifth == "W":
            return None, "warrant"
        if fifth == "R":
            return None, "right"
        if fifth == "U":
            return None, "unit"
        if fifth in ("P", "O", "N", "M", "L", "K", "J", "I"):
            return None, "preferred"

    # Normalize share classes (e.g. BRK.B -> BRK-B)
    match_sc = _SHARE_CLASS_RE.match(sym)
    if match_sc:
        normalized = f"{match_sc.group(1)}-{match_sc.group(2)}"
    else:
        normalized = sym

    if not _VALID_NORMALIZED_TICKER_RE.match(normalized):
        return None, "unsupported"

    return normalized, None


def _load_saved_watchlist_safe(name: str, settings: TradeXSettings | None = None) -> list[str] | None:
    """Load a named watchlist from store, returning None if database or table is uninitialized."""
    db_path = wl_store._resolve_db_path(settings)
    if not db_path.exists():
        return None
    try:
        return wl_store.load(name, settings=settings)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return None
        raise


def compute_all_us_snapshot_hash(
    tickers: list[str],
    nasdaq_rows: int,
    other_rows: int,
    gen_ts: str | None,
) -> str:
    """Compute a deterministic, verifiable SHA-256 hash for the All U.S. universe snapshot."""
    hash_input = json.dumps(
        {
            "gen_ts": gen_ts,
            "nasdaq_rows": int(nasdaq_rows),
            "other_rows": int(other_rows),
            "tickers": sorted(dict.fromkeys(tickers)),
        },
        sort_keys=True,
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def parse_nasdaq_directory(
    content: str,
    *,
    min_listings: int = 2,
) -> tuple[list[str], dict[str, int], list[str], str | None, int]:
    """Parse nasdaqlisted.txt.

    Returns:
      (included_symbols, exclusion_counts, unsupported_symbols, file_timestamp, total_rows)
    """
    if not content or content.lstrip().startswith("<!DOCTYPE") or "<html" in content.lower():
        raise UniverseSourceError("Received empty or HTML content instead of valid nasdaqlisted.txt")

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise UniverseSourceError("nasdaqlisted.txt content has no lines")

    header = [c.strip() for c in lines[0].split("|")]
    required = ["Symbol", "Security Name", "Test Issue"]
    for req in required:
        if req not in header:
            raise UniverseSourceError(f"Missing mandatory column {req!r} in nasdaqlisted.txt header")
    if "ETF" not in header and "NextShares" not in header:
        raise UniverseSourceError("Missing mandatory column 'ETF' or 'NextShares' in nasdaqlisted.txt header")

    sym_idx = header.index("Symbol")
    name_idx = header.index("Security Name")
    test_idx = header.index("Test Issue")
    etf_idx = header.index("ETF") if "ETF" in header else -1
    nextshares_idx = header.index("NextShares") if "NextShares" in header else -1

    min_parts = max(sym_idx, name_idx, test_idx, etf_idx, nextshares_idx) + 1

    included: list[str] = []
    unsupported: list[str] = []
    counts: dict[str, int] = {
        "test_issue": 0,
        "etf": 0,
        "warrant": 0,
        "preferred": 0,
        "right": 0,
        "unit": 0,
        "note": 0,
    }
    file_ts: str | None = None
    data_rows = 0

    for line in lines[1:]:
        if line.startswith("File Creation Time:"):
            file_ts = _parse_footer_timestamp(line)
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < min_parts:
            continue

        data_rows += 1
        sym_raw = parts[sym_idx]
        name_raw = parts[name_idx] if name_idx < len(parts) else ""
        is_test = (parts[test_idx].upper() == "Y") if test_idx < len(parts) else False
        is_etf = (parts[etf_idx].upper() == "Y") if etf_idx < len(parts) else False
        if nextshares_idx != -1 and nextshares_idx < len(parts) and parts[nextshares_idx].upper() == "Y":
            is_etf = True

        norm_sym, reason = _classify_symbol_and_name(
            sym_raw, name_raw, is_test=is_test, is_etf=is_etf, exchange_source="nasdaq"
        )
        if norm_sym:
            included.append(norm_sym)
        elif reason == "unsupported":
            unsupported.append(sym_raw)
        elif reason in counts:
            counts[reason] += 1

    if data_rows < min_listings:
        raise UniverseSourceError(
            f"nasdaqlisted.txt contains only {data_rows} listings (expected >= {min_listings}); "
            f"rejecting as truncated/incomplete"
        )
    if not included:
        raise UniverseSourceError("nasdaqlisted.txt parsed 0 common stock symbols; rejecting as incomplete")

    return included, counts, unsupported, file_ts, data_rows


def parse_other_directory(
    content: str,
    *,
    min_listings: int = 2,
) -> tuple[list[str], dict[str, int], list[str], str | None, int]:
    """Parse otherlisted.txt.

    Returns:
      (included_symbols, exclusion_counts, unsupported_symbols, file_timestamp, total_rows)
    """
    if not content or content.lstrip().startswith("<!DOCTYPE") or "<html" in content.lower():
        raise UniverseSourceError("Received empty or HTML content instead of valid otherlisted.txt")

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise UniverseSourceError("otherlisted.txt content has no lines")

    header = [c.strip() for c in lines[0].split("|")]
    required = ["ACT Symbol", "Security Name", "Exchange", "CQS Symbol", "ETF", "Test Issue"]
    for req in required:
        if req not in header:
            raise UniverseSourceError(f"Missing mandatory column {req!r} in otherlisted.txt header")

    act_idx = header.index("ACT Symbol")
    name_idx = header.index("Security Name")
    etf_idx = header.index("ETF")
    test_idx = header.index("Test Issue")

    min_parts = max(act_idx, name_idx, etf_idx, test_idx) + 1

    included: list[str] = []
    unsupported: list[str] = []
    counts: dict[str, int] = {
        "test_issue": 0,
        "etf": 0,
        "warrant": 0,
        "preferred": 0,
        "right": 0,
        "unit": 0,
        "note": 0,
    }
    file_ts: str | None = None
    data_rows = 0

    for line in lines[1:]:
        if line.startswith("File Creation Time:"):
            file_ts = _parse_footer_timestamp(line)
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < min_parts:
            continue

        data_rows += 1
        sym_raw = parts[act_idx]
        name_raw = parts[name_idx] if name_idx < len(parts) else ""
        is_test = (parts[test_idx].upper() == "Y") if test_idx < len(parts) else False
        is_etf = (parts[etf_idx].upper() == "Y") if etf_idx < len(parts) else False

        norm_sym, reason = _classify_symbol_and_name(
            sym_raw, name_raw, is_test=is_test, is_etf=is_etf, exchange_source="other"
        )
        if norm_sym:
            included.append(norm_sym)
        elif reason == "unsupported":
            unsupported.append(sym_raw)
        elif reason in counts:
            counts[reason] += 1

    if data_rows < min_listings:
        raise UniverseSourceError(
            f"otherlisted.txt contains only {data_rows} listings (expected >= {min_listings}); "
            f"rejecting as truncated/incomplete"
        )
    if not included:
        raise UniverseSourceError("otherlisted.txt parsed 0 common stock symbols; rejecting as incomplete")

    return included, counts, unsupported, file_ts, data_rows


def _get_universe_cache_path(settings: TradeXSettings) -> Path:
    """Return path to cached All U.S. Stocks universe snapshot."""
    cache_dir = Path(str(settings.paths.discovery_cache_dir)).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "universe_all_us_stocks.json"


def _load_cached_universe_snapshot(settings: TradeXSettings) -> tuple[list[str], UniverseProvenance] | None:
    path = _get_universe_cache_path(settings)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "tickers" not in data or "provenance" not in data:
            logger.warning("Universe cache at %s is not a valid snapshot dictionary; rejecting.", path)
            return None
        raw_tickers = data["tickers"]
        if not isinstance(raw_tickers, list) or not raw_tickers:
            logger.warning("Universe cache at %s contains empty or non-list tickers; rejecting.", path)
            return None
        tickers = [str(t).strip().upper() for t in raw_tickers if str(t).strip()]
        prov = UniverseProvenance.from_dict(data["provenance"])

        # Check count consistency
        if len(tickers) != prov.included_ticker_count:
            logger.warning(
                "Universe cache ticker count mismatch (%d != %d); rejecting corrupt snapshot.",
                len(tickers),
                prov.included_ticker_count,
            )
            return None

        n_rows = prov.original_listing_counts.get("nasdaqlisted", 0)
        o_rows = prov.original_listing_counts.get("otherlisted", 0)
        if n_rows <= 0 or o_rows <= 0:
            logger.warning("Universe cache listing counts missing or invalid; rejecting corrupt snapshot.")
            return None

        expected_hash = compute_all_us_snapshot_hash(
            tickers, n_rows, o_rows, prov.source_file_generation_timestamp
        )
        if expected_hash != prov.snapshot_hash:
            logger.warning(
                "Universe cache snapshot hash mismatch (computed %s != stored %s); rejecting corrupt snapshot.",
                expected_hash,
                prov.snapshot_hash,
            )
            return None

        return tickers, prov
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load cached universe snapshot from %s: %s", path, exc)
        return None


def _save_cached_universe_snapshot(
    settings: TradeXSettings,
    tickers: list[str],
    prov: UniverseProvenance,
) -> None:
    path = _get_universe_cache_path(settings)
    tmp_path = path.with_suffix(".tmp")
    payload = {
        "tickers": tickers,
        "provenance": prov.to_dict(),
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)


def resolve_all_us_stocks(
    *,
    settings: TradeXSettings | None = None,
    http_fetcher: Callable[[str], str] | None = None,
    allow_stale: bool = False,
    force_refresh: bool = False,
    min_listings_per_source: int = 2,
) -> tuple[list[str], UniverseProvenance]:
    """Resolve the All U.S. Listed Stocks universe from official Nasdaq Trader files.

    If refresh fails:
      - If cached snapshot is stale (>= 24h old) and allow_stale is False: fails closed.
      - If cached snapshot is stale and allow_stale is True: preserves snapshot marked is_stale=True.
      - If cached snapshot is fresh (< 24h old): returns fresh snapshot.
      - If no valid snapshot exists, raises UniverseSourceError.
      - Never silently substitutes S&P 500, Nasdaq 100, or a partial universe.
    """
    settings = settings or load_runtime_settings()
    fetcher = http_fetcher or _default_http_fetcher

    cached = _load_cached_universe_snapshot(settings)
    now = datetime.now(UTC)

    if cached is not None and not force_refresh:
        tickers, prov = cached
        try:
            cached_dt = datetime.fromisoformat(prov.retrieval_timestamp)
            age = now - cached_dt
            if age < timedelta(hours=UNIVERSE_FRESHNESS_HOURS):
                return tickers, prov
        except ValueError:
            pass

    # Attempt fetch from official sources
    fetch_error: Exception | None = None
    try:
        nasdaq_content = fetcher(NASDAQ_LISTED_URL)
        other_content = fetcher(OTHER_LISTED_URL)
    except Exception as exc:  # noqa: BLE001
        fetch_error = exc
        nasdaq_content = ""
        other_content = ""

    if not fetch_error and nasdaq_content and other_content:
        try:
            n_inc, n_counts, n_unsup, n_ts, n_rows = parse_nasdaq_directory(
                nasdaq_content, min_listings=min_listings_per_source
            )
            o_inc, o_counts, o_unsup, o_ts, o_rows = parse_other_directory(
                other_content, min_listings=min_listings_per_source
            )

            combined_exclusions: dict[str, int] = {}
            for k in set(n_counts) | set(o_counts):
                combined_exclusions[k] = n_counts.get(k, 0) + o_counts.get(k, 0)

            all_unsupported = sorted(set(n_unsup + o_unsup))

            # Deduplication
            seen: set[str] = set()
            dedup_tickers: list[str] = []
            duplicate_count = 0
            for t in n_inc + o_inc:
                if t in seen:
                    duplicate_count += 1
                else:
                    seen.add(t)
                    dedup_tickers.append(t)

            dedup_tickers.sort()
            combined_exclusions["duplicate"] = duplicate_count

            gen_timestamps = [t for t in (n_ts, o_ts) if t]
            combined_gen_ts = ", ".join(gen_timestamps) if gen_timestamps else None

            snapshot_hash = compute_all_us_snapshot_hash(dedup_tickers, n_rows, o_rows, combined_gen_ts)

            prov = UniverseProvenance(
                universe_id="all_us_stocks",
                scope=Scope.ALL_US_STOCKS,
                source_urls=(NASDAQ_LISTED_URL, OTHER_LISTED_URL),
                retrieval_timestamp=now.isoformat(),
                source_file_generation_timestamp=combined_gen_ts,
                snapshot_hash=snapshot_hash,
                original_listing_counts={
                    "nasdaqlisted": n_rows,
                    "otherlisted": o_rows,
                    "total": n_rows + o_rows,
                },
                included_ticker_count=len(dedup_tickers),
                excluded_counts_by_reason=combined_exclusions,
                unsupported_symbol_count=len(all_unsupported),
                unsupported_symbols=tuple(all_unsupported),
                is_stale=False,
                stale_reason=None,
            )

            _save_cached_universe_snapshot(settings, dedup_tickers, prov)
            return dedup_tickers, prov

        except Exception as exc:  # noqa: BLE001
            fetch_error = exc

    # Refresh failed. Check if a cached snapshot can be preserved.
    if cached is not None:
        tickers, prov = cached
        age_hours: float | None = None
        try:
            cached_dt = datetime.fromisoformat(prov.retrieval_timestamp)
            age_hours = (now - cached_dt).total_seconds() / 3600.0
        except ValueError:
            pass

        is_stale_by_age = age_hours is None or age_hours >= UNIVERSE_FRESHNESS_HOURS
        age_str = f"{age_hours:.1f}h old" if age_hours is not None else "unknown age"

        if is_stale_by_age and not allow_stale:
            raise UniverseSourceError(
                f"Nasdaq Trader directories refresh failed ({fetch_error}) and cached snapshot is stale "
                f"({age_str}, retrieved {prov.retrieval_timestamp}). Explicit opt-in (allow_stale=True) "
                f"is required to scan a stale universe."
            )

        stale_reason = (
            f"Source refresh failed ({fetch_error}); using preserved snapshot ({age_str}, "
            f"retrieved {prov.retrieval_timestamp})."
        )
        stale_prov = UniverseProvenance(
            universe_id=prov.universe_id,
            scope=prov.scope,
            source_urls=prov.source_urls,
            retrieval_timestamp=prov.retrieval_timestamp,
            source_file_generation_timestamp=prov.source_file_generation_timestamp,
            snapshot_hash=prov.snapshot_hash,
            original_listing_counts=prov.original_listing_counts,
            included_ticker_count=prov.included_ticker_count,
            excluded_counts_by_reason=prov.excluded_counts_by_reason,
            unsupported_symbol_count=prov.unsupported_symbol_count,
            unsupported_symbols=prov.unsupported_symbols,
            is_stale=True,
            stale_reason=stale_reason,
        )
        return tickers, stale_prov

    raise UniverseSourceError(
        f"Failed to resolve All U.S. Listed Stocks from Nasdaq Trader directories "
        f"and no valid cached snapshot exists: {fetch_error}"
    )


def resolve_universe(
    scope: Scope | str,
    *,
    watchlist: list[str] | None = None,
    settings: TradeXSettings | None = None,
    http_fetcher: Callable[[str], str] | None = None,
    allow_stale: bool = False,
    force_refresh: bool = False,
) -> tuple[list[str], UniverseProvenance]:
    """Resolve tickers and provenance for any approved discovery scope."""
    if isinstance(scope, str):
        scope = Scope(scope)

    settings = settings or load_runtime_settings()
    now_iso = datetime.now(UTC).isoformat()

    if scope == Scope.MY_WATCHLIST:
        raw_list = watchlist or []
        normalized = list(dict.fromkeys(str(t).strip().upper() for t in raw_list if str(t).strip()))
        hash_val = hashlib.sha256(",".join(normalized).encode("utf-8")).hexdigest()
        prov = UniverseProvenance(
            universe_id="my_watchlist",
            scope=Scope.MY_WATCHLIST,
            source_urls=(),
            retrieval_timestamp=now_iso,
            source_file_generation_timestamp=None,
            snapshot_hash=hash_val,
            original_listing_counts={"watchlist": len(normalized)},
            included_ticker_count=len(normalized),
            excluded_counts_by_reason={},
            unsupported_symbol_count=0,
            unsupported_symbols=(),
            is_stale=False,
            stale_reason=None,
        )
        return normalized, prov

    if scope == Scope.SP500:
        saved = _load_saved_watchlist_safe("S&P 500", settings=settings)
        source_label = "Saved Watchlist" if saved else "TradeX Preset Snapshot (2026-05)"
        tickers = list(dict.fromkeys(saved or wl_presets.SP500))
        tickers.sort()
        hash_val = hashlib.sha256(",".join(tickers).encode("utf-8")).hexdigest()
        prov = UniverseProvenance(
            universe_id="sp500",
            scope=Scope.SP500,
            source_urls=(),
            retrieval_timestamp=now_iso,
            source_file_generation_timestamp="2026-05",
            snapshot_hash=hash_val,
            original_listing_counts={"sp500": len(tickers)},
            included_ticker_count=len(tickers),
            excluded_counts_by_reason={},
            unsupported_symbol_count=0,
            unsupported_symbols=(),
            is_stale=False,
            stale_reason=f"Constituent snapshot ({source_label}); not real-time index membership.",
        )
        return tickers, prov

    if scope == Scope.NASDAQ100:
        saved = _load_saved_watchlist_safe("Nasdaq 100", settings=settings)
        source_label = "Saved Watchlist" if saved else "TradeX Preset Snapshot (2026-05)"
        tickers = list(dict.fromkeys(saved or wl_presets.NDX100))
        tickers.sort()
        hash_val = hashlib.sha256(",".join(tickers).encode("utf-8")).hexdigest()
        prov = UniverseProvenance(
            universe_id="nasdaq100",
            scope=Scope.NASDAQ100,
            source_urls=(),
            retrieval_timestamp=now_iso,
            source_file_generation_timestamp="2026-05",
            snapshot_hash=hash_val,
            original_listing_counts={"nasdaq100": len(tickers)},
            included_ticker_count=len(tickers),
            excluded_counts_by_reason={},
            unsupported_symbol_count=0,
            unsupported_symbols=(),
            is_stale=False,
            stale_reason=f"Constituent snapshot ({source_label}); not real-time index membership.",
        )
        return tickers, prov

    if scope == Scope.ALL_US_STOCKS:
        return resolve_all_us_stocks(
            settings=settings,
            http_fetcher=http_fetcher,
            allow_stale=allow_stale,
            force_refresh=force_refresh,
        )

    raise ValueError(f"Unsupported discovery scope: {scope}")
