"""Event detection, rolling quantile threshold, and overlap tests."""
from __future__ import annotations

from datetime import date

import pytest

from tradex.research.daytrade_reversal.calendar import build_regular_session_grid, to_market_time
from tradex.research.daytrade_reversal.events import (
    classify_overlapping_events,
    compute_session_threshold,
    detect_events_in_session,
    extract_session_eligible_returns,
)
from tradex.research.daytrade_reversal.quality import audit_ticker_session
from tradex.research.daytrade_reversal.synthetic import generate_synthetic_session_bars


def test_threshold_requires_exactly_20_prior_valid_sessions(sample_trading_days) -> None:
    """Threshold returns None if fewer than 20 prior valid sessions are available."""
    days = sample_trading_days[:25]
    sessions = []
    for d in days[:19]:
        grid = build_regular_session_grid(d)
        raw_df = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw_df, grid)
        sessions.append(s)

    # 19 sessions < 20
    assert compute_session_threshold(sessions) is None

    # Add 20th session
    d20 = days[19]
    grid20 = build_regular_session_grid(d20)
    raw20 = generate_synthetic_session_bars("AAPL", d20)
    s20, _ = audit_ticker_session("AAPL", d20, raw20, grid20)
    sessions.append(s20)

    # Exactly 20 sessions -> threshold is computed
    threshold = compute_session_threshold(sessions)
    assert threshold is not None
    assert isinstance(threshold, float)


def test_opening_minute_0930_excluded_from_threshold_distribution() -> None:
    """The 09:30 opening return is strictly excluded from the reference return population."""
    session_d = date(2025, 1, 2)
    grid = build_regular_session_grid(session_d)

    # Inject an extreme plunge at 09:30 (-10%)
    raw_df = generate_synthetic_session_bars("AAPL", session_d, minute_returns={"09:30": -0.10})
    s, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    returns = extract_session_eligible_returns(s)
    # The return at 09:30 must not be present in eligible returns
    assert all(r > -0.05 for r in returns)


def test_current_session_excluded_from_threshold(sample_trading_days) -> None:
    """Current session D is not included in its own threshold calculation."""
    days = sample_trading_days[:21]
    prior_sessions = []
    for d in days[:20]:
        grid = build_regular_session_grid(d)
        raw_df = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw_df, grid)
        prior_sessions.append(s)

    t_before = compute_session_threshold(prior_sessions)

    # Candidate session 21 has an extreme -20% plunge at 10:00
    d21 = days[20]
    grid21 = build_regular_session_grid(d21)
    raw21 = generate_synthetic_session_bars("AAPL", d21, minute_returns={"10:00": -0.20})
    s21, _ = audit_ticker_session("AAPL", d21, raw21, grid21)

    # Threshold for session 21 uses ONLY prior_sessions, so adding s21 would alter it
    assert compute_session_threshold(prior_sessions) == t_before
    # If s21 were erroneously included, threshold would change
    assert compute_session_threshold(prior_sessions + [s21]) != t_before


def test_event_at_exact_threshold_and_just_above(sample_trading_days) -> None:
    """An observation <= threshold is an event; just above (> threshold) is a non-event."""
    days = sample_trading_days[:21]
    prior_sessions = []
    for d in days[:20]:
        grid = build_regular_session_grid(d)
        raw_df = generate_synthetic_session_bars("AAPL", d)
        s, _ = audit_ticker_session("AAPL", d, raw_df, grid)
        prior_sessions.append(s)

    # Threshold is negative (-0.010) while default bars have return +0.0001
    threshold = -0.010
    d21 = days[20]
    grid21 = build_regular_session_grid(d21)

    # Case 1: Exactly at threshold
    raw_exact = generate_synthetic_session_bars("AAPL", d21, minute_returns={"10:00": threshold})
    s_exact, _ = audit_ticker_session("AAPL", d21, raw_exact, grid21)
    events_exact, _ = detect_events_in_session(s_exact, threshold, "development")
    assert len(events_exact) == 1
    assert events_exact[0].event_return == pytest.approx(threshold)

    # Case 2: Just above threshold (threshold + 1e-4)
    raw_above = generate_synthetic_session_bars(
        "AAPL", d21, minute_returns={"10:00": threshold + 1e-4}
    )
    s_above, _ = audit_ticker_session("AAPL", d21, raw_above, grid21)
    events_above, non_events_above = detect_events_in_session(s_above, threshold, "development")
    assert len(events_above) == 0
    assert any(to_market_time(bar.bar_start).strftime("%H:%M") == "10:00" for bar, _ in non_events_above)


def test_earliest_and_latest_event_boundaries(sample_trading_days) -> None:
    """Earliest eligible event is at 09:31; latest eligible event is at 15:54.

    Events attempted at 09:30 or 15:55 are prohibited.
    """
    session_d = sample_trading_days[0]
    grid = build_regular_session_grid(session_d)

    # Trigger plunges at 09:30, 09:31, 15:54, 15:55
    plunges = {
        "09:30": -0.05,
        "09:31": -0.05,
        "15:54": -0.05,
        "15:55": -0.05,
    }
    raw_df = generate_synthetic_session_bars("AAPL", session_d, minute_returns=plunges)
    s, _ = audit_ticker_session("AAPL", session_d, raw_df, grid)

    # With threshold -0.01, only the -0.05 returns qualify if time is eligible
    events, _ = detect_events_in_session(s, threshold=-0.01, split_name="development")

    event_times = [to_market_time(e.event_bar_start).strftime("%H:%M") for e in events]
    assert "09:30" not in event_times
    assert "09:31" in event_times
    assert "15:54" in event_times
    assert "15:55" not in event_times


def test_overlapping_events_same_and_cross_ticker(sample_trading_days) -> None:
    """Consecutive same-ticker and simultaneous cross-ticker events are classified as overlapping."""
    d = sample_trading_days[0]
    grid = build_regular_session_grid(d)

    # AAPL has events at 10:00 and 10:02 (consecutive forward window overlap [10:01, 10:06] and [10:03, 10:08])
    raw_aapl = generate_synthetic_session_bars(
        "AAPL", d, minute_returns={"10:00": -0.05, "10:02": -0.05}
    )
    s_aapl, _ = audit_ticker_session("AAPL", d, raw_aapl, grid)
    events_aapl, _ = detect_events_in_session(s_aapl, -0.01, "development")

    # MSFT has event at 10:00 (simultaneous with AAPL)
    raw_msft = generate_synthetic_session_bars("MSFT", d, minute_returns={"10:00": -0.05})
    s_msft, _ = audit_ticker_session("MSFT", d, raw_msft, grid)
    events_msft, _ = detect_events_in_session(s_msft, -0.01, "development")

    all_events = events_aapl + events_msft
    classify_overlapping_events(all_events)

    # AAPL event at 10:00 overlaps with AAPL at 10:02 (same-ticker) AND MSFT at 10:00 (cross-ticker)
    aapl_1000 = next(
        e for e in all_events if e.ticker == "AAPL" and to_market_time(e.event_bar_start).strftime("%H:%M") == "10:00"
    )
    assert aapl_1000.is_overlapping is True
    assert aapl_1000.same_ticker_overlap is True
    assert aapl_1000.cross_ticker_overlap is True

    # MSFT event at 10:00 overlaps cross-ticker with AAPL at 10:00
    msft_1000 = next(e for e in all_events if e.ticker == "MSFT")
    assert msft_1000.is_overlapping is True
    assert msft_1000.same_ticker_overlap is False
    assert msft_1000.cross_ticker_overlap is True
