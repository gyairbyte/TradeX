"""Outcome labeling engine for LONG-002C across all nine target/horizon cells.

Implements locked outcome formulas, adverse barriers, clean risk caps, same-bar ambiguity,
and execution friction scenarios.
"""
from __future__ import annotations

from typing import Any

from tradex.research.long_002c.models import OutcomeLabelRecord
from tradex.research.long_002c.spec import (
    PRIMARY_ENTRY_FRICTION_BPS,
    TARGET_GRID,
)


def compute_outcome_cell(
    immutable_security_id: str,
    ticker_at_decision: str,
    as_of_date: str,
    cutoff_time: str,
    target_pct: float,
    horizon_sessions: int,
    next_open_price: float,  # split-normalized next regular session open
    forward_bars: list[dict[str, Any]],  # list of dicts with split-normalized {"open", "high", "low", "close"}
    pre_entry_atr: float,
    entry_friction_bps: float = PRIMARY_ENTRY_FRICTION_BPS,
    special_distribution_unresolved: bool = False,
    as_traded_entry_price: float | None = None,
) -> OutcomeLabelRecord:
    """Compute outcome metrics for a single (target_pct, horizon_sessions) cell.

    forward_bars must contain at least horizon_sessions bars on a consistent split-normalized price basis.
    Retains both reference_entry_price (raw as-traded open + $0.01 + 5 bps friction) and
    analysis_entry_price (split-normalized open).
    All forward barriers, ATR, returns, MFE, MAE, and clean risk cap paths operate on split-normalized scale.
    If special_distribution_unresolved is True, the outcome cannot be reliably calculated and is excluded from clean targets.
    """
    if len(forward_bars) < horizon_sessions:
        raise ValueError(
            f"Insufficient forward bars for horizon {horizon_sessions}: got {len(forward_bars)}"
        )

    bars = forward_bars[:horizon_sessions]

    # Primary friction: 10 bps all-in
    # Analysis entry price on split-normalized scale includes friction:
    analysis_entry_price = float(next_open_price) * (1.0 + entry_friction_bps / 10000.0)

    # Reference execution entry price on as-traded scale includes friction (NO fixed $0.01 increment):
    if as_traded_entry_price is not None:
        raw_open = float(as_traded_entry_price)
        reference_entry_price = raw_open * (1.0 + entry_friction_bps / 10000.0)
    else:
        reference_entry_price = analysis_entry_price

    # All target, barrier, and cap calculations use the SAME friction-adjusted analytical entry scale
    target_price = analysis_entry_price * (1.0 + target_pct / 100.0)

    # Adverse barrier formulas: max(0.05, 1.5 * pre_entry_atr / analysis_entry_price)
    if pre_entry_atr > 0 and analysis_entry_price > 0:
        adverse_barrier_pct = max(0.05, 1.5 * pre_entry_atr / analysis_entry_price)
    else:
        adverse_barrier_pct = 0.05

    adverse_barrier_price = analysis_entry_price * (1.0 - adverse_barrier_pct)

    # Clean risk cap formulas: min((target_pct / 100.0) / 2.0, adverse_barrier_pct)
    clean_risk_cap_pct = min((target_pct / 100.0) / 2.0, adverse_barrier_pct)
    clean_risk_cap_amount = analysis_entry_price * clean_risk_cap_pct
    clean_risk_cap_price = analysis_entry_price * (1.0 - clean_risk_cap_pct)

    # Forward price path metrics on split-normalized scale
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]

    max_forward_high = max(highs)
    min_forward_low = min(lows)
    close_at_horizon = closes[-1]

    mfe_pct = max_forward_high / analysis_entry_price - 1.0
    target_progress_ratio = mfe_pct / (target_pct / 100.0)
    target_reached = max_forward_high >= target_price

    near_miss = 0.8 <= target_progress_ratio < 1.0
    partial_move = 0.5 <= target_progress_ratio < 0.8

    mae_pct = max(0.0, (analysis_entry_price - min_forward_low) / analysis_entry_price)
    mae_atr = (
        (analysis_entry_price - min_forward_low) / pre_entry_atr
        if pre_entry_atr > 0
        else 0.0
    )
    adverse_excursion = mae_pct >= adverse_barrier_pct

    # Find time_to_target (1-based session index)
    first_target_idx: int | None = None
    for idx, h in enumerate(highs):
        if h >= target_price:
            first_target_idx = idx + 1
            break
    time_to_target = first_target_idx

    # Find time_to_mae (1-based session index of minimum low)
    time_to_mae = lows.index(min_forward_low) + 1

    path_sequence_ambiguous = False
    clean_target_reached = False

    if target_reached and first_target_idx is not None:
        target_bar = bars[first_target_idx - 1]
        tb_high = float(target_bar["high"])
        tb_low = float(target_bar["low"])

        if tb_high >= target_price and tb_low <= adverse_barrier_price:
            path_sequence_ambiguous = True

        # Pre-target excursion check
        pre_target_lows = lows[: first_target_idx - 1]
        pre_target_min_low = min(pre_target_lows) if pre_target_lows else analysis_entry_price
        pre_target_mae_pct = max(0.0, (analysis_entry_price - pre_target_min_low) / analysis_entry_price)

        # On the target bar itself, check if low broke clean risk cap
        target_bar_broke_cap = tb_low <= clean_risk_cap_price

        if (
            not path_sequence_ambiguous
            and pre_target_mae_pct <= clean_risk_cap_pct
            and not target_bar_broke_cap
        ):
            clean_target_reached = True

    # Horizon return and retention metrics
    end_of_horizon_return = close_at_horizon / analysis_entry_price - 1.0
    retention_ratio = (
        end_of_horizon_return / mfe_pct if mfe_pct > 0 else 0.0
    )
    sustained_target = target_reached and (
        end_of_horizon_return >= 0.5 * (target_pct / 100.0)
    )

    if special_distribution_unresolved:
        clean_target_reached = False
        sustained_target = False
        near_miss = False
        partial_move = False

    return OutcomeLabelRecord(
        immutable_security_id=immutable_security_id,
        as_of_date=as_of_date,
        cutoff_time=cutoff_time,
        target_pct=target_pct,
        horizon_sessions=horizon_sessions,
        ticker_at_decision=ticker_at_decision,
        reference_entry_price=round(reference_entry_price, 4),
        entry_friction_bps=entry_friction_bps,
        target_price=round(target_price, 4),
        adverse_barrier_pct=round(adverse_barrier_pct, 6),
        adverse_barrier_price=round(adverse_barrier_price, 4),
        clean_risk_cap_pct=round(clean_risk_cap_pct, 6),
        clean_risk_cap_amount=round(clean_risk_cap_amount, 4),
        mfe_pct=round(mfe_pct, 6),
        target_progress_ratio=round(target_progress_ratio, 6),
        near_miss=near_miss,
        partial_move=partial_move,
        mae_pct=round(mae_pct, 6),
        mae_atr=round(mae_atr, 6),
        adverse_excursion=adverse_excursion,
        clean_target_reached=clean_target_reached,
        path_sequence_ambiguous=path_sequence_ambiguous,
        end_of_horizon_return=round(end_of_horizon_return, 6),
        retention_ratio=round(retention_ratio, 6),
        sustained_target=sustained_target,
        analysis_entry_price=round(analysis_entry_price, 4),
        special_distribution_unresolved=special_distribution_unresolved,
        time_to_target=time_to_target,
        time_to_mae=time_to_mae,
    )


def compute_all_nine_outcomes(
    immutable_security_id: str,
    ticker_at_decision: str,
    as_of_date: str,
    cutoff_time: str,
    next_open_price: float,
    forward_bars: list[dict[str, Any]],  # at least 21 bars on consistent split-normalized basis
    pre_entry_atr: float,
    entry_friction_bps: float = PRIMARY_ENTRY_FRICTION_BPS,
    special_distribution_unresolved: bool = False,
    as_traded_entry_price: float | None = None,
) -> list[OutcomeLabelRecord]:
    """Compute all nine target/horizon outcome combinations for an observation."""
    records: list[OutcomeLabelRecord] = []
    for target_pct, horizon_sessions in TARGET_GRID:
        record = compute_outcome_cell(
            immutable_security_id=immutable_security_id,
            ticker_at_decision=ticker_at_decision,
            as_of_date=as_of_date,
            cutoff_time=cutoff_time,
            target_pct=target_pct,
            horizon_sessions=horizon_sessions,
            next_open_price=next_open_price,
            forward_bars=forward_bars,
            pre_entry_atr=pre_entry_atr,
            entry_friction_bps=entry_friction_bps,
            special_distribution_unresolved=special_distribution_unresolved,
            as_traded_entry_price=as_traded_entry_price,
        )
        records.append(record)
    return records


def parse_special_distribution_dates(dividends: list[dict[str, Any]]) -> set[str]:
    """Extract dates of unresolved material distributions (special cash, spinoffs, capital returns).

    Ordinary regular cash dividends do NOT cause exclusion.
    """
    special_dates: set[str] = set()
    for div in dividends:
        div_type = str(div.get("dividend_type") or div.get("type") or "").upper()
        if div_type in {"SC", "SPECIAL", "SPECIAL_CASH", "SPINOFF", "SPIN_OFF", "RETURN_OF_CAPITAL", "LIQUIDATION"}:
            ex_date = div.get("ex_dividend_date") or div.get("execution_date") or div.get("record_date")
            if ex_date:
                special_dates.add(str(ex_date)[:10])
    return special_dates


def derive_affected_special_distribution_sessions(
    special_distribution_dates: set[str],
    all_sessions: list[str],
    max_horizon_sessions: int = 26,
) -> set[str]:
    """Derive decision session dates whose forward outcome window intersects a special distribution date.

    Any decision session T whose outcome horizon [T, T + max_horizon_sessions] covers a
    special distribution date is affected and must be excluded.
    """
    if not special_distribution_dates or not all_sessions:
        return set()

    affected_sessions: set[str] = set()
    n_sessions = len(all_sessions)

    for idx, session in enumerate(all_sessions):
        window_end_idx = min(n_sessions, idx + max_horizon_sessions + 1)
        window = set(all_sessions[idx:window_end_idx])
        if window & special_distribution_dates:
            affected_sessions.add(session)

    return affected_sessions
