"""Characterization tests for confluence scoring."""

from unittest.mock import patch

import pandas as pd
import pytest

from tradex.tracker import confluence


def _make_bars(n: int = 31) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame that satisfies the 30-bar minimum."""
    return pd.DataFrame(
        {
            "open": [1.0] * n,
            "high": [2.0] * n,
            "low": [0.5] * n,
            "close": [1.5] * n,
            "volume": [10] * n,
        }
    )


def _fake_score(score: int):
    def _fn(df: pd.DataFrame) -> dict:
        return {"score": score, "reasons": ["momentum"], "last_close": 100.0}

    return _fn


EXPECTED_COLUMNS = {
    "ticker",
    "confluence_score",
    "tier",
    "active_timeframes",
    "timeframe_coverage",
    "available_timeframes",
    "missing_timeframes",
    "score_intraday",
    "score_short",
    "score_long",
    "days_until_earnings",
    "last_close",
}


def test_empty_confluence_returns_empty_dataframe():
    """run_confluence_screen must return an empty DataFrame with the stable output schema."""
    low_result = {
        "ticker": "AAPL",
        "confluence_score": 10,
        "tier": "weak / single timeframe",
        "active_timeframes": ["intraday"],
        "available_timeframes": ["intraday"],
        "missing_timeframes": ["short", "long"],
        "timeframe_coverage": "1/3",
        "complete_timeframe_coverage": False,
        "scores": {"intraday": 10},
        "reasons": {"intraday": ["none"]},
        "last_close": 100.0,
        "errors": {},
    }

    with (
        patch.object(confluence, "days_until_earnings", return_value=None),
        patch.object(confluence, "score_confluence", return_value=low_result),
    ):
        result = confluence.run_confluence_screen(["AAPL"], min_confluence=50)

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert set(result.columns) == EXPECTED_COLUMNS

    # An empty ticker list should produce the same stable schema.
    empty = confluence.run_confluence_screen([], min_confluence=50)
    assert isinstance(empty, pd.DataFrame)
    assert empty.empty
    assert set(empty.columns) == EXPECTED_COLUMNS


def test_confluence_propagates_provider_to_all_timeframes():
    """score_confluence must pass the provider to fetch for intraday, short, and long."""
    captured = []

    def fake_fetch(ticker, timeframe, provider=None, *, settings=None):
        captured.append((ticker, timeframe, provider))
        return _make_bars(31)

    def fake_score(df):
        return {"score": 60, "reasons": ["momentum"], "last_close": 100.0}

    with (
        patch.object(confluence, "fetch", side_effect=fake_fetch),
        patch.object(confluence.intraday, "score", side_effect=fake_score),
        patch.object(confluence.short_term, "score", side_effect=fake_score),
        patch.object(confluence.long_term, "score", side_effect=fake_score),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        confluence.score_confluence("AAPL", provider="schwab")

    assert len(captured) == 3
    timeframes = {call[1] for call in captured}
    assert timeframes == {"intraday", "short", "long"}
    assert all(call[2] == "schwab" for call in captured)


def test_run_confluence_screen_propagates_provider():
    """run_confluence_screen must pass provider to score_confluence."""
    captured = []

    def fake_score_confluence(ticker, provider=None, *, settings=None):
        captured.append(provider)
        return {
            "ticker": ticker,
            "confluence_score": 0,
            "tier": "no data",
            "active_timeframes": [],
            "available_timeframes": [],
            "missing_timeframes": ["intraday", "short", "long"],
            "timeframe_coverage": "0/3",
            "complete_timeframe_coverage": False,
            "scores": {},
            "reasons": {},
            "last_close": None,
            "errors": {"intraday": "no data", "short": "no data", "long": "no data"},
        }

    with (
        patch.object(confluence, "score_confluence", side_effect=fake_score_confluence),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        result = confluence.run_confluence_screen(["AAPL"], provider="alpaca")

    assert captured == ["alpaca"]
    assert isinstance(result, pd.DataFrame)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixed-weight scoring regressions
# ═══════════════════════════════════════════════════════════════════════════════


def _score_confluence_with_scores(scores: dict[str, int | None]):
    """Run score_confluence with mocked fetch/scorer for requested timeframes.

    A score of None means the timeframe is unavailable (fetch raises).
    """

    def fake_fetch(ticker, timeframe, provider=None, *, settings=None):
        if scores.get(timeframe) is None:
            raise RuntimeError("no data")
        return _make_bars(31)

    def fake_score_factory(tf):
        return lambda df: {"score": scores[tf], "reasons": ["momentum"], "last_close": 100.0}

    with (
        patch.object(confluence, "fetch", side_effect=fake_fetch),
        patch.object(confluence.intraday, "score", side_effect=fake_score_factory("intraday")),
        patch.object(confluence.short_term, "score", side_effect=fake_score_factory("short")),
        patch.object(confluence.long_term, "score", side_effect=fake_score_factory("long")),
    ):
        return confluence.score_confluence("TEST")


def _make_score_cases():
    cases = [
        ({"intraday": 100, "short": 100, "long": 100}, 100),
        ({"intraday": 100, "short": 0, "long": 0}, 30),
        ({"intraday": 0, "short": 100, "long": 0}, 40),
        ({"intraday": 0, "short": 0, "long": 100}, 30),
        ({"intraday": 100, "short": 100, "long": 0}, 70),
        ({"intraday": 100, "short": 0, "long": 100}, 60),
        ({"intraday": 0, "short": 100, "long": 100}, 70),
    ]
    return cases


@pytest.mark.parametrize("scores,expected", _make_score_cases())
def test_confluence_fixed_weight_scoring(scores, expected):
    """Missing timeframes contribute zero and weights are never renormalized."""
    result = _score_confluence_with_scores(scores)
    assert result["confluence_score"] == expected
    assert 0 <= result["confluence_score"] <= 100
    available = {tf for tf, s in scores.items() if s is not None}
    assert set(result["available_timeframes"]) == available
    assert set(result["missing_timeframes"]) == ({"intraday", "short", "long"} - available)


def test_confluence_does_not_claim_all_timeframes_when_one_is_missing():
    """If short and long data are unavailable, the result must not claim all timeframes are aligned."""
    result = _score_confluence_with_scores({"intraday": 95, "short": None, "long": None})
    assert result["tier"] != "all timeframes aligned"
    assert result["confluence_score"] == 28
    assert result["tier"] == "weak / single timeframe"
    assert result["timeframe_coverage"] == "1/3"
    assert "short" in result["missing_timeframes"]
    assert "long" in result["missing_timeframes"]
    assert "short" in result["errors"]
    assert "long" in result["errors"]


def test_confluence_no_data_result_is_stable():
    """A complete fetch/score failure still returns the full stable result schema."""
    result = _score_confluence_with_scores({"intraday": None, "short": None, "long": None})
    assert result["confluence_score"] == 0
    assert result["tier"] == "no data"
    assert result["active_timeframes"] == []
    assert result["available_timeframes"] == []
    assert result["missing_timeframes"] == ["intraday", "short", "long"]
    assert result["timeframe_coverage"] == "0/3"
    assert result["complete_timeframe_coverage"] is False
    assert result["scores"] == {}
    assert result["reasons"] == {}
    assert result["last_close"] is None
    assert result["errors"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tier classification regressions
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_timeframes_aligned_requires_all_three_active_and_high_score():
    result = _score_confluence_with_scores({"intraday": 95, "short": 95, "long": 95})
    assert result["tier"] == "all timeframes aligned"
    assert result["confluence_score"] == 95
    assert result["timeframe_coverage"] == "3/3"
    assert result["complete_timeframe_coverage"] is True


def test_all_timeframes_aligned_not_awarded_with_only_two_timeframes():
    result = _score_confluence_with_scores({"intraday": 100, "short": 100, "long": None})
    assert result["tier"] != "all timeframes aligned"
    assert result["confluence_score"] == 70
    assert result["tier"] == "strong confluence"


def test_one_timeframe_can_never_be_moderate_strong_or_aligned():
    result = _score_confluence_with_scores({"intraday": 100, "short": None, "long": None})
    assert result["confluence_score"] == 30
    assert result["tier"] == "weak / single timeframe"


def test_two_timeframes_strong_confluence():
    result = _score_confluence_with_scores({"intraday": 100, "short": 100, "long": None})
    assert result["confluence_score"] == 70
    assert result["tier"] == "strong confluence"


def test_two_timeframes_moderate_confluence():
    result = _score_confluence_with_scores({"intraday": 100, "short": 60, "long": None})
    assert result["confluence_score"] == 54
    assert result["tier"] == "moderate confluence"


def test_two_timeframes_weak_incomplete():
    result = _score_confluence_with_scores({"intraday": 10, "short": 60, "long": None})
    assert result["confluence_score"] == 27
    assert result["tier"] == "weak / incomplete timeframes"


def test_three_timeframes_weak_confluence():
    result = _score_confluence_with_scores({"intraday": 20, "short": 30, "long": 40})
    assert result["confluence_score"] == 30
    assert result["tier"] == "weak confluence"


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage metadata regressions
# ═══════════════════════════════════════════════════════════════════════════════


def test_coverage_metadata_deterministic_order():
    result = _score_confluence_with_scores({"long": 50, "short": 60, "intraday": 70})
    assert result["available_timeframes"] == ["intraday", "short", "long"]
    assert result["missing_timeframes"] == []
    assert result["timeframe_coverage"] == "3/3"
    assert result["timeframe_count"] == 3


def test_coverage_metadata_with_missing_timeframes():
    result = _score_confluence_with_scores({"short": 60, "intraday": None, "long": None})
    assert result["available_timeframes"] == ["short"]
    assert result["missing_timeframes"] == ["intraday", "long"]
    assert result["timeframe_coverage"] == "1/3"
    assert result["complete_timeframe_coverage"] is False


def test_errors_record_insufficient_data_and_fetch_failures():
    def fake_fetch(ticker, timeframe, provider=None, *, settings=None):
        if timeframe == "intraday":
            return _make_bars(20)
        if timeframe == "short":
            raise RuntimeError("fetch failed")
        return _make_bars(31)

    def fake_score(df):
        return {"score": 60, "reasons": ["momentum"], "last_close": 100.0}

    with (
        patch.object(confluence, "fetch", side_effect=fake_fetch),
        patch.object(confluence.intraday, "score", side_effect=fake_score),
        patch.object(confluence.short_term, "score", side_effect=fake_score),
        patch.object(confluence.long_term, "score", side_effect=fake_score),
    ):
        result = confluence.score_confluence("TEST")

    assert result["errors"]["intraday"] == "insufficient data"
    assert "fetch failed" in result["errors"]["short"]
    assert result["available_timeframes"] == ["long"]
    assert result["timeframe_coverage"] == "1/3"


# ═══════════════════════════════════════════════════════════════════════════════
# run_confluence_screen regressions
# ═══════════════════════════════════════════════════════════════════════════════


def test_screen_uses_corrected_score_for_min_confluence_threshold():
    """A single timeframe score of 100 must not pass min_confluence=70."""
    with patch.object(confluence, "score_confluence") as fake:
        fake.return_value = {
            "ticker": "TEST",
            "confluence_score": 30,
            "tier": "weak / single timeframe",
            "active_timeframes": ["intraday"],
            "available_timeframes": ["intraday"],
            "missing_timeframes": ["short", "long"],
            "timeframe_coverage": "1/3",
            "complete_timeframe_coverage": False,
            "scores": {"intraday": 100},
            "reasons": {"intraday": ["momentum"]},
            "last_close": 100.0,
            "errors": {"short": "no data", "long": "no data"},
        }
        with patch.object(confluence, "days_until_earnings", return_value=None):
            result = confluence.run_confluence_screen(["TEST"], min_confluence=70)
    assert result.empty
    assert set(result.columns) == EXPECTED_COLUMNS


def test_screen_includes_complete_result_and_coverage_columns():
    with patch.object(confluence, "score_confluence") as fake:
        fake.return_value = {
            "ticker": "TEST",
            "confluence_score": 95,
            "tier": "all timeframes aligned",
            "active_timeframes": ["intraday", "short", "long"],
            "available_timeframes": ["intraday", "short", "long"],
            "missing_timeframes": [],
            "timeframe_coverage": "3/3",
            "complete_timeframe_coverage": True,
            "scores": {"intraday": 95, "short": 95, "long": 95},
            "reasons": {"intraday": ["momentum"]},
            "last_close": 100.0,
            "errors": {},
        }
        with patch.object(confluence, "days_until_earnings", return_value=None):
            result = confluence.run_confluence_screen(["TEST"], min_confluence=50)

    assert len(result) == 1
    assert result.iloc[0]["confluence_score"] == 95
    assert result.iloc[0]["timeframe_coverage"] == "3/3"
    assert result.iloc[0]["available_timeframes"] == "intraday, short, long"
    assert result.iloc[0]["missing_timeframes"] == ""
    assert result.iloc[0]["score_intraday"] == 95
    assert result.iloc[0]["score_short"] == 95
    assert result.iloc[0]["score_long"] == 95


def test_screen_sorts_descending_by_corrected_score():
    rows = [
        {
            "ticker": "LOW",
            "confluence_score": 30,
            "tier": "weak / single timeframe",
            "active_timeframes": ["intraday"],
            "available_timeframes": ["intraday"],
            "missing_timeframes": ["short", "long"],
            "timeframe_coverage": "1/3",
            "complete_timeframe_coverage": False,
            "scores": {"intraday": 100},
            "reasons": {"intraday": ["momentum"]},
            "last_close": 100.0,
            "errors": {},
        },
        {
            "ticker": "HIGH",
            "confluence_score": 95,
            "tier": "all timeframes aligned",
            "active_timeframes": ["intraday", "short", "long"],
            "available_timeframes": ["intraday", "short", "long"],
            "missing_timeframes": [],
            "timeframe_coverage": "3/3",
            "complete_timeframe_coverage": True,
            "scores": {"intraday": 95, "short": 95, "long": 95},
            "reasons": {},
            "last_close": 100.0,
            "errors": {},
        },
    ]

    with (
        patch.object(confluence, "score_confluence", side_effect=rows),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        result = confluence.run_confluence_screen(["LOW", "HIGH"], min_confluence=50)

    assert list(result["ticker"]) == ["HIGH"]
    assert result.iloc[0]["confluence_score"] == 95


def test_screen_missing_score_placeholder_unchanged():
    with patch.object(confluence, "score_confluence") as fake:
        fake.return_value = {
            "ticker": "TEST",
            "confluence_score": 70,
            "tier": "strong confluence",
            "active_timeframes": ["intraday", "short"],
            "available_timeframes": ["intraday", "short"],
            "missing_timeframes": ["long"],
            "timeframe_coverage": "2/3",
            "complete_timeframe_coverage": False,
            "scores": {"intraday": 100, "short": 75},
            "reasons": {},
            "last_close": 100.0,
            "errors": {"long": "no data"},
        }
        with patch.object(confluence, "days_until_earnings", return_value=None):
            result = confluence.run_confluence_screen(["TEST"], min_confluence=50)

    assert result.iloc[0]["score_intraday"] == 100
    assert result.iloc[0]["score_short"] == 75
    assert result.iloc[0]["score_long"] == "-"


def test_confluence_screen_fails_closed_when_filter_enabled_and_earnings_unknown():
    """When exclude_earnings_within > 0 and earnings date is unknown, ticker is skipped."""
    score_called = []

    def fake_score(ticker, **kwargs):
        score_called.append(ticker)
        return {
            "ticker": ticker,
            "confluence_score": 80,
            "tier": "strong confluence",
            "active_timeframes": ["intraday", "short"],
            "available_timeframes": ["intraday", "short"],
            "missing_timeframes": ["long"],
            "timeframe_coverage": "2/3",
            "complete_timeframe_coverage": False,
            "scores": {"intraday": 80, "short": 80},
            "reasons": {},
            "last_close": 100.0,
            "errors": {},
        }

    with (
        patch.object(confluence, "score_confluence", side_effect=fake_score),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        result = confluence.run_confluence_screen(
            ["AAPL"], min_confluence=50, exclude_earnings_within=5
        )

    assert result.empty
    assert score_called == []


def test_confluence_screen_passes_through_when_filter_disabled_and_earnings_unknown():
    """When exclude_earnings_within is 0 or None and earnings date is unknown, ticker is scored."""
    fake_result = {
        "ticker": "AAPL",
        "confluence_score": 80,
        "tier": "strong confluence",
        "active_timeframes": ["intraday", "short"],
        "available_timeframes": ["intraday", "short"],
        "missing_timeframes": ["long"],
        "timeframe_coverage": "2/3",
        "complete_timeframe_coverage": False,
        "scores": {"intraday": 80, "short": 80},
        "reasons": {},
        "last_close": 100.0,
        "errors": {},
    }

    with (
        patch.object(confluence, "score_confluence", return_value=fake_result),
        patch.object(confluence, "days_until_earnings", return_value=None),
    ):
        result = confluence.run_confluence_screen(
            ["AAPL"], min_confluence=50, exclude_earnings_within=0
        )

    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "AAPL"
    assert result.iloc[0]["days_until_earnings"] is None
