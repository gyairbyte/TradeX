"""Candidate open-drive VWAP pullback/reclaim strategy."""
from __future__ import annotations

from .execution import attempt_trade
from .models import Bar, CostScenario, Session, Signal, TickerMeta
from .opening_drive import evaluate_opening_drive
from .reclaim import find_first_reclaim
from .spec import IntradaySpec
from .vwap import compute_session_vwap


def _stop_for_reclaim(bar: Bar) -> float:
    stop_buffer = max(0.01, bar.close * 0.0005)
    return bar.low - stop_buffer


def evaluate_candidate_session(
    ticker: str,
    ticker_meta: TickerMeta,
    session: Session,
    prior_sessions: list[Session],
    costs: CostScenario,
    spec: IntradaySpec,
) -> list[Signal]:
    """Evaluate the candidate strategy for one ticker-session."""
    compute_session_vwap(session)
    opening_drive = evaluate_opening_drive(session, prior_sessions, ticker_meta, spec)

    reclaim_bar = find_first_reclaim(session, opening_drive, spec, require_opening_drive=True)
    if reclaim_bar is None:
        return [
            Signal(
                ticker=ticker,
                session_date=session.session_date,
                strategy="candidate",
                signal_bar_start=None,
                signal_time=None,
                opening_drive_qualified=opening_drive.qualified,
                score=None,
                stop_price=None,
                target_price=None,
                entry_open=None,
                entry_fill=None,
                risk_per_share=None,
                status="no_signal",
                reason="no_reclaim_bar_found",
            )
        ]

    stop_price = _stop_for_reclaim(reclaim_bar)
    return [
        attempt_trade(
            ticker=ticker,
            ticker_meta=ticker_meta,
            session=session,
            signal_bar=reclaim_bar,
            stop_price=stop_price,
            opening_drive_qualified=opening_drive.qualified,
            score=None,
            costs=costs,
            spec=spec,
            strategy="candidate",
        )
    ]
