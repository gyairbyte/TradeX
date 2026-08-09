"""Baseline B — simple VWAP reclaim without opening-drive requirements."""
from __future__ import annotations

from .candidate import _stop_for_reclaim
from .eligibility import check_ticker_eligibility
from .execution import attempt_trade
from .models import CostScenario, Session, Signal, TickerMeta
from .opening_drive import evaluate_opening_drive
from .reclaim import find_first_reclaim
from .spec import IntradaySpec
from .vwap import compute_session_vwap


def evaluate_baseline_b_session(
    ticker: str,
    ticker_meta: TickerMeta,
    session: Session,
    prior_sessions: list[Session],
    costs: CostScenario,
    spec: IntradaySpec,
) -> list[Signal]:
    """Evaluate Baseline B for one ticker-session."""
    eligible, eligibility_reasons = check_ticker_eligibility(ticker_meta, spec)
    if not eligible:
        return [
            Signal(
                ticker=ticker,
                session_date=session.session_date,
                strategy="baseline_b",
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
                reason=";".join(eligibility_reasons),
            )
        ]

    compute_session_vwap(session)
    # Baseline B does not require opening-drive qualification, but the engine
    # still computes it for reporting consistency.
    opening_drive = evaluate_opening_drive(session, prior_sessions, ticker_meta, spec)

    reclaim_bar = find_first_reclaim(
        session, opening_drive, spec, require_opening_drive=False
    )
    if reclaim_bar is None:
        return [
            Signal(
                ticker=ticker,
                session_date=session.session_date,
                strategy="baseline_b",
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
            opening_drive_qualified=None,
            score=None,
            costs=costs,
            spec=spec,
            strategy="baseline_b",
        )
    ]
