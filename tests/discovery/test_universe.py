"""Tests for universe resolution and parsing (LONG-MVP-003)."""

from __future__ import annotations

import pytest

from tradex.config import settings_from_mapping
from tradex.discovery.models import Scope
from tradex.discovery.universe import (
    UniverseSourceError,
    _classify_symbol_and_name,
    parse_nasdaq_directory,
    parse_other_directory,
    resolve_all_us_stocks,
    resolve_universe,
)

SAMPLE_NASDAQ_TXT = """Symbol|Security Name|Market Category|Financial Status|Round Lot Size|Test Issue|NASDAQ Symbol|NextShares|ETF
AAPL|Apple Inc. - Common Stock|Q|N|100|N|AAPL|N|N
MSFT|Microsoft Corporation - Common Stock|Q|N|100|N|MSFT|N|N
TEST|Test Security - Common Stock|Q|N|100|Y|TEST|N|N
QQQ|Invesco QQQ Trust, Series 1|Q|N|100|N|QQQ|N|Y
NXSTW|Nextstar Media Group Warrant|G|N|100|N|NXSTW|N|N
ACADR|Acadia Pharmaceuticals Right|S|N|100|N|ACADR|N|N
XYZU|XYZ Corp Unit|S|N|100|N|XYZU|N|N
ABC$P|ABC Capital Preferred Stock|S|N|100|N|ABC$P|N|N
DEF|DEF Senior Notes due 2030|Q|N|100|N|DEF|N|N
File Creation Time: 102220260830||||||||
"""

SAMPLE_OTHER_TXT = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue
IBM|International Business Machines Common Stock|N|IBM|N|100|N
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N
BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N
BF B|Brown-Forman Corporation Class B|N|BF B|N|100|N
FOO+WS|Foo Corp Warrant|N|FOO.WS|N|100|N
BAR=U|Bar Acquisition Corp Unit|A|BAR.U|N|100|N
BAZ$A|Baz Corp Preferred Series A|N|BAZpA|N|100|N
TEST2|Other Test Issue|N|TEST2|N|100|Y
BADSYM?|Malformed Symbol|N|BADSYM?|N|100|N
File Creation Time: 102220260830||||||
"""


def test_parse_nasdaq_directory_valid():
    """Valid nasdaqlisted.txt parses symbols, exclusions, and file timestamp."""
    inc, counts, _unsup, file_ts, rows = parse_nasdaq_directory(SAMPLE_NASDAQ_TXT)
    assert inc == ["AAPL", "MSFT"]
    assert counts["test_issue"] == 1  # TEST
    assert counts["etf"] == 1  # QQQ
    assert counts["warrant"] == 1  # NXSTW
    assert counts["right"] == 1  # ACADR
    assert counts["unit"] == 1  # XYZU
    assert counts["preferred"] == 1  # ABC$P
    assert counts["note"] == 1  # DEF Senior Notes
    assert file_ts == "2026-10-22T08:30:00+00:00"
    assert rows == 9


def test_parse_other_directory_valid():
    """Valid otherlisted.txt parses symbols, normalizes share classes, and tracks exclusions."""
    inc, counts, unsup, file_ts, rows = parse_other_directory(SAMPLE_OTHER_TXT)
    assert "IBM" in inc
    assert "BRK-B" in inc  # Normalized from BRK.B
    assert "BF-B" in inc  # Normalized from BF B
    assert counts["etf"] == 1  # SPY
    assert counts["test_issue"] == 1  # TEST2
    assert counts["warrant"] == 1  # FOO+WS
    assert counts["unit"] == 1  # BAR=U
    assert counts["preferred"] == 1  # BAZ$A
    assert "BADSYM?" in unsup
    assert file_ts == "2026-10-22T08:30:00+00:00"
    assert rows == 9


def test_parse_rejects_html():
    """HTML response or 404/500 error page raises UniverseSourceError."""
    html_doc = "<!DOCTYPE html><html><body>Error 404 Not Found</body></html>"
    with pytest.raises(UniverseSourceError, match="Received empty or HTML content"):
        parse_nasdaq_directory(html_doc)
    with pytest.raises(UniverseSourceError, match="Received empty or HTML content"):
        parse_other_directory(html_doc)


def test_parse_rejects_empty():
    """Empty content raises UniverseSourceError."""
    with pytest.raises(UniverseSourceError):
        parse_nasdaq_directory("")
    with pytest.raises(UniverseSourceError):
        parse_other_directory("   \n\n  ")


def test_parse_rejects_missing_columns():
    """Missing mandatory column raises UniverseSourceError."""
    bad_header = "Symbol|Security Name|Market Category\nAAPL|Apple|Q\n"
    with pytest.raises(UniverseSourceError, match="Missing mandatory column"):
        parse_nasdaq_directory(bad_header)


def test_classify_symbol_and_name_rules():
    """Conservative common stock classification covers all security types."""
    # Common stock
    sym, reason = _classify_symbol_and_name("AAPL", "Apple Inc.", False, False, "nasdaq")
    assert sym == "AAPL" and reason is None

    # Share classes
    sym, reason = _classify_symbol_and_name("GOOG.L", "Alphabet Class A", False, False, "nasdaq")
    assert sym == "GOOG-L" and reason is None

    # Preferred stock
    _, reason = _classify_symbol_and_name("ALL$B", "Allstate Corp Preferred Series B", False, False, "other")
    assert reason == "preferred"
    _, reason = _classify_symbol_and_name("C-PJ", "Citigroup Dep Shs Repstg 1/1000th Pfd", False, False, "other")
    assert reason == "preferred"

    # Warrants
    _, reason = _classify_symbol_and_name("QS.WS", "QuantumScape Corp Wt", False, False, "other")
    assert reason == "warrant"

    # Rights
    _, reason = _classify_symbol_and_name("XYZR", "XYZ Rights Offering", False, False, "nasdaq")
    assert reason == "right"

    # Units
    _, reason = _classify_symbol_and_name("XYZU", "XYZ Corp Units", False, False, "nasdaq")
    assert reason == "unit"

    # Notes
    _, reason = _classify_symbol_and_name("BABA", "Senior Notes due 2035", False, False, "other")
    assert reason == "note"


def test_resolve_all_us_stocks_end_to_end(tmp_path):
    """resolve_all_us_stocks merges both sources, dedups, caches, and retains provenance."""
    cache_dir = tmp_path / "discovery_cache"
    settings = settings_from_mapping({"TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir)})

    def mock_fetcher(url: str) -> str:
        if "nasdaqlisted" in url:
            return SAMPLE_NASDAQ_TXT
        if "otherlisted" in url:
            return SAMPLE_OTHER_TXT
        raise ValueError(f"Unexpected URL: {url}")

    tickers, prov = resolve_all_us_stocks(settings=settings, http_fetcher=mock_fetcher)
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "IBM" in tickers
    assert "BRK-B" in tickers
    assert "BF-B" in tickers
    assert "TEST" not in tickers
    assert "SPY" not in tickers
    assert prov.scope == Scope.ALL_US_STOCKS
    assert prov.universe_id == "all_us_stocks"
    assert prov.included_ticker_count == len(tickers)
    assert not prov.is_stale

    # Confirm snapshot was cached to disk
    cached_file = cache_dir / "universe_all_us_stocks.json"
    assert cached_file.exists()


def test_resolve_all_us_stocks_preserves_cached_on_failure(tmp_path):
    """If network refresh fails, preserved cached snapshot is returned with is_stale=True."""
    cache_dir = tmp_path / "discovery_cache"
    settings = settings_from_mapping({"TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir)})

    # First run succeeds
    def mock_ok(url: str) -> str:
        return SAMPLE_NASDAQ_TXT if "nasdaqlisted" in url else SAMPLE_OTHER_TXT

    tickers_1, _ = resolve_all_us_stocks(settings=settings, http_fetcher=mock_ok)

    # Second run with network failure
    def mock_fail(url: str) -> str:
        raise OSError("Connection timed out")

    tickers_2, prov_2 = resolve_all_us_stocks(
        settings=settings, http_fetcher=mock_fail, force_refresh=True
    )
    assert tickers_2 == tickers_1
    assert prov_2.is_stale
    assert "Connection timed out" in (prov_2.stale_reason or "")


def test_resolve_all_us_stocks_fails_closed_if_no_cache(tmp_path):
    """If network fails and NO cache exists, raises UniverseSourceError without silent fallback."""
    cache_dir = tmp_path / "empty_cache"
    settings = settings_from_mapping({"TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir)})

    def mock_fail(url: str) -> str:
        raise OSError("DNS lookup failed")

    with pytest.raises(UniverseSourceError, match="Failed to resolve All U.S. Listed Stocks"):
        resolve_all_us_stocks(settings=settings, http_fetcher=mock_fail)


def test_resolve_all_us_stocks_fails_if_only_one_source_succeeds(tmp_path):
    """If one directory fails, does NOT treat single directory as the full market."""
    cache_dir = tmp_path / "empty_cache"
    settings = settings_from_mapping({"TRADEX_DISCOVERY_CACHE_DIR": str(cache_dir)})

    def mock_partial(url: str) -> str:
        if "nasdaqlisted" in url:
            return SAMPLE_NASDAQ_TXT
        raise OSError("otherlisted failed")

    with pytest.raises(UniverseSourceError):
        resolve_all_us_stocks(settings=settings, http_fetcher=mock_partial)


def test_resolve_universe_index_scopes():
    """Index scopes resolve without altering user watchlists."""
    settings = settings_from_mapping({})
    sp_tickers, sp_prov = resolve_universe(Scope.SP500, settings=settings)
    assert len(sp_tickers) >= 500
    assert sp_prov.universe_id == "sp500"
    assert "AAPL" in sp_tickers

    ndx_tickers, ndx_prov = resolve_universe(Scope.NASDAQ100, settings=settings)
    assert len(ndx_tickers) >= 100
    assert ndx_prov.universe_id == "nasdaq100"
    assert "MSFT" in ndx_tickers


def test_resolve_universe_watchlist_scope():
    """My Watchlist scope resolves active watchlist."""
    settings = settings_from_mapping({})
    wl = ["NVDA", "amd", "INTC"]
    tickers, prov = resolve_universe(Scope.MY_WATCHLIST, watchlist=wl, settings=settings)
    assert tickers == ["NVDA", "AMD", "INTC"]
    assert prov.universe_id == "my_watchlist"
    assert prov.included_ticker_count == 3
