"""Baseline A — current production intraday score with explicit fresh weights."""
from __future__ import annotations

from datetime import datetime

from .execution import attempt_trade
from .models import CostScenario, Session, Signal, TickerMeta
from .normalize import bars_to_dataframe
from .spec import IntradaySpec
from .vwap import compute_session_vwap


def _signal_bar_stop(bar) -> float:
    stop_buffer = max(0.01, bar.close * 0.0005)
    return bar.low - stop_buffer


def _baseline_search_window(session: Session, spec: IntradaySpec) -> list[datetime]:
    from .reclaim import _grid_in_window

    return _grid_in_window(
        session, spec.reclaim_search_start_time, spec.reclaim_search_end_time
    )



def evaluate_baseline_a_session(
    ticker: str,
    ticker_meta: TickerMeta,
    session: Session,
    prior_sessions: list[Session],
    costs: CostScenario,
    spec: IntradaySpec,
) -> list[Signal]:
    """Evaluate the production intraday-score baseline for one ticker-session."""
    import tradex.signals.intraday as intraday_module
    from tradex.signals.indicators import add_indicators
    from tradex.signals.intraday import score as intraday_score
    from tradex.signals.weights import IntradayWeights

    compute_session_vwap(session)

    prior_bars = [b for s in prior_sessions for b in s.bars.values() if b.is_valid]
    current_bars = [b for b in session.bars.values() if b.is_valid]
    all_bars = sorted(prior_bars + current_bars, key=lambda b: b.bar_start)
    if len(all_bars) < 20:
        return [
            Signal(
                ticker=ticker,
                session_date=session.session_date,
                strategy="baseline_a",
                signal_bar_start=None,
                signal_time=None,
                opening_drive_qualified=None,
                score=None,
                stop_price=None,
                target_price=None,
                entry_open=None,
                entry_fill=None,
                risk_per_share=None,
                status="no_signal",
                reason="insufficient_history_for_indicators",
            )
        ]

    full_df = add_indicators(bars_to_dataframe(all_bars))
    weights = IntradayWeights()

    original_add_indicators = intraday_module.add_indicators
    try:
        for bar_start in _baseline_search_window(session, spec):
            bar = session.bars.get(bar_start)
            if bar is None or not bar.is_valid:
                continue

            idx = full_df.index.get_loc(bar_start)
            if not isinstance(idx, int):
                continue
            if idx < 20:
                continue

            # Avoid recomputing indicators for every search bar. add_indicators
            # is backward-looking, so row values are unchanged by later rows; we
            # patch it to return the already-computed slice up to the same length.
            def _patched_add_indicators(df):
                return full_df.iloc[: len(df)].copy()

            intraday_module.add_indicators = _patched_add_indicators

            df_slice = full_df.iloc[: idx + 1]
            score_output = intraday_score(df_slice, weights=weights)
            if score_output["score"] >= 40:
                stop_price = _signal_bar_stop(bar)
                return [
                    attempt_trade(
                        ticker=ticker,
                        ticker_meta=ticker_meta,
                        session=session,
                        signal_bar=bar,
                        stop_price=stop_price,
                        opening_drive_qualified=None,
                        score=float(score_output["score"]),
                        costs=costs,
                        spec=spec,
                        strategy="baseline_a",
                    )
                ]
    finally:
        intraday_module.add_indicators = original_add_indicators

    return [
        Signal(
            ticker=ticker,
            session_date=session.session_date,
            strategy="baseline_a",
            signal_bar_start=None,
            signal_time=None,
            opening_drive_qualified=None,
            score=None,
            stop_price=None,
            target_price=None,
            entry_open=None,
            entry_fill=None,
            risk_per_share=None,
            status="no_signal",
            reason="no_score_reached_40",
        )
    ]
