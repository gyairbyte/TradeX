"""Opening range qualification, candidate filtering, and Top-20 ranking mechanics."""
from __future__ import annotations

import math
from datetime import date, time
from zoneinfo import ZoneInfo

from .models import (
    Candidate,
    DataIntegrityError,
    Direction,
    MinuteBar,
    OpeningRange,
    OrderIntent,
    OrderStatus,
    RankedCandidate,
)

MARKET_TIMEZONE = ZoneInfo("America/New_York")
OR_MINUTE_TIMES = (
    time(9, 30),
    time(9, 31),
    time(9, 32),
    time(9, 33),
    time(9, 34),
)


def evaluate_opening_range(minute_bars: list[MinuteBar]) -> OpeningRange | None:
    """Evaluate the first 5 regular-session minute bars (09:30-09:34) for a symbol on session D.

    Must contain all 5 bars. If any are missing, duplicated, or invalid, returns None (fail closed).
    All bars must have the identical symbol and session_date.
    """
    if not minute_bars or len(minute_bars) < 5:
        return None

    symbol = minute_bars[0].symbol
    session_date = minute_bars[0].session_date
    if any(b.symbol != symbol or b.session_date != session_date for b in minute_bars):
        return None

    # Filter and sort bars belonging to 09:30-09:34 ET
    or_bars: dict[time, MinuteBar] = {}
    for bar in minute_bars:
        local_time = bar.timestamp.astimezone(MARKET_TIMEZONE).time()
        if local_time in OR_MINUTE_TIMES:
            if local_time in or_bars:
                # Duplicate minute bar detected -> fail closed
                return None
            or_bars[local_time] = bar

    if len(or_bars) != 5:
        # Missing opening-range minute -> fail closed
        return None

    sorted_bars = [or_bars[t] for t in OR_MINUTE_TIMES]
    symbol = sorted_bars[0].symbol
    session_date = sorted_bars[0].session_date

    or_open = sorted_bars[0].open
    or_high = max(b.high for b in sorted_bars)
    or_low = min(b.low for b in sorted_bars)
    or_close = sorted_bars[-1].close
    or_volume = sum(b.volume for b in sorted_bars)

    if not all(
        not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
        for v in (or_open, or_high, or_low, or_close, or_volume)
    ):
        return None

    if or_close > or_open:
        direction = Direction.LONG
        stop_level = or_high
    elif or_close < or_open:
        direction = Direction.SHORT
        stop_level = or_low
    else:
        direction = Direction.DOJI
        stop_level = None

    return OpeningRange(
        symbol=symbol,
        session_date=session_date,
        or_open=or_open,
        or_high=or_high,
        or_low=or_low,
        or_close=or_close,
        or_volume=or_volume,
        direction=direction,
        stop_level=stop_level,
    )


def evaluate_candidate(
    symbol: str,
    session_date: date,
    opening_range: OpeningRange,
    adv14: float | None,
    atr14: float | None,
    mean_prior_or_volume: float | None,
    rv: float | None,
    price_min: float = 5.0,
    adv_min: float = 1_000_000.0,
    atr_min: float = 0.50,
    rv_min: float = 1.0,
) -> Candidate:
    """Evaluate eligibility filters for a candidate symbol at 09:35 ET."""
    # Check all numeric indicator inputs for finiteness: non-finite values must fail closed and NEVER be treated as technical filter failure
    for name, val in [
        ("opening_price", opening_range.or_open),
        ("or_volume", opening_range.or_volume),
        ("adv14", adv14),
        ("atr14", atr14),
        ("mean_prior_or_volume", mean_prior_or_volume),
        ("rv", rv),
    ]:
        if val is not None and (
            isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val)
        ):
            raise DataIntegrityError(f"Candidate {name} must be finite for {symbol}: {val}")

    rejection_reasons: list[str] = []

    opening_price = opening_range.or_open
    price_passed = opening_price > price_min
    if not price_passed:
        rejection_reasons.append(f"Price {opening_price:.2f} <= {price_min:.2f}")

    adv_passed = adv14 is not None and adv14 >= adv_min
    if not adv_passed:
        if adv14 is None:
            rejection_reasons.append("ADV14 is non-computable")
        else:
            rejection_reasons.append(f"ADV14 {adv14:.0f} < {adv_min:.0f}")

    atr_passed = atr14 is not None and atr14 > atr_min
    if not atr_passed:
        if atr14 is None:
            rejection_reasons.append("ATR14 is non-computable")
        else:
            rejection_reasons.append(f"ATR14 {atr14:.2f} <= {atr_min:.2f}")

    rv_passed = rv is not None and rv >= rv_min
    if not rv_passed:
        if rv is None:
            rejection_reasons.append("RV14 is non-computable")
        else:
            rejection_reasons.append(f"RV14 {rv:.2f} < {rv_min:.2f}")

    is_eligible = price_passed and adv_passed and atr_passed and rv_passed

    return Candidate(
        symbol=symbol,
        session_date=session_date,
        opening_price=opening_price,
        adv14=adv14 if adv14 is not None else 0.0,
        atr14=atr14 if atr14 is not None else 0.0,
        or_volume=opening_range.or_volume,
        mean_prior_or_volume=mean_prior_or_volume if mean_prior_or_volume is not None else 0.0,
        relative_volume=rv if rv is not None else 0.0,
        price_passed=price_passed,
        adv_passed=adv_passed,
        atr_passed=atr_passed,
        rv_passed=rv_passed,
        is_eligible=is_eligible,
        rejection_reasons=tuple(rejection_reasons),
    )


def size_order_intent(
    candidate: Candidate,
    opening_range: OpeningRange,
    session_start_equity: float,
    risk_fraction: float = 0.01,
    leverage_cap: float = 4.0,
    stop_loss_atr_mult: float = 0.10,
) -> OrderIntent:
    """Compute base risk and leverage desired shares for a qualifying candidate.

    Sizing methodology (Zarattini & Aziz SSRN 4416622):
        R = 0.10 * ATR14
        risk_shares = floor((session_start_equity * 0.01) / R)
        leverage_shares = floor((4.0 * session_start_equity) / stop_level)
        desired_shares = min(risk_shares, leverage_shares)
    """
    if opening_range.direction == Direction.DOJI:
        return OrderIntent(
            symbol=candidate.symbol,
            session_date=candidate.session_date,
            direction=Direction.DOJI,
            stop_level=None,
            atr14=candidate.atr14,
            protective_stop_offset=0.0,
            desired_shares=0,
            risk_per_share=0.0,
            status=OrderStatus.NO_ORDER_DOJI,
            reason="Doji opening range produces no order",
        )

    stop_level = opening_range.stop_level
    if stop_level is None or stop_level <= 0 or candidate.atr14 <= 0:
        return OrderIntent(
            symbol=candidate.symbol,
            session_date=candidate.session_date,
            direction=opening_range.direction,
            stop_level=stop_level,
            atr14=candidate.atr14,
            protective_stop_offset=0.0,
            desired_shares=0,
            risk_per_share=0.0,
            status=OrderStatus.NON_COMPUTABLE,
            reason="Invalid stop level or ATR14",
        )

    r_per_share = stop_loss_atr_mult * candidate.atr14
    if r_per_share <= 0:
        return OrderIntent(
            symbol=candidate.symbol,
            session_date=candidate.session_date,
            direction=opening_range.direction,
            stop_level=stop_level,
            atr14=candidate.atr14,
            protective_stop_offset=0.0,
            desired_shares=0,
            risk_per_share=0.0,
            status=OrderStatus.NON_COMPUTABLE,
            reason="Zero or negative risk per share",
        )

    risk_shares = math.floor((session_start_equity * risk_fraction) / r_per_share)
    leverage_shares = math.floor((leverage_cap * session_start_equity) / stop_level)
    desired_shares = min(risk_shares, leverage_shares)

    if desired_shares <= 0:
        return OrderIntent(
            symbol=candidate.symbol,
            session_date=candidate.session_date,
            direction=opening_range.direction,
            stop_level=stop_level,
            atr14=candidate.atr14,
            protective_stop_offset=r_per_share,
            desired_shares=0,
            risk_per_share=r_per_share,
            status=OrderStatus.CAPACITY_REJECTED,
            reason="Desired shares <= 0 under 1% risk / 4x leverage constraints",
        )

    return OrderIntent(
        symbol=candidate.symbol,
        session_date=candidate.session_date,
        direction=opening_range.direction,
        stop_level=stop_level,
        atr14=candidate.atr14,
        protective_stop_offset=r_per_share,
        desired_shares=desired_shares,
        risk_per_share=r_per_share,
        status=OrderStatus.ORDER_NOT_TRIGGERED,
        reason="",
    )


def rank_and_select_top_20(
    candidates: list[Candidate],
    opening_ranges: dict[str, OpeningRange],
    session_start_equity: float = 25000.0,
    top_n: int = 20,
) -> list[RankedCandidate]:
    """Rank eligible candidates by RV descending (ticker ascending tie-break) and select Top 20.

    CRITICAL INVARIANTS:
    1. Selection occurs at 09:35 before knowing later trade triggers or outcomes.
    2. Doji candidates in Top 20 produce NO_ORDER and are NOT backfilled with rank #21.
    """
    eligible = [c for c in candidates if c.is_eligible]
    # Deterministic sort: RV descending, symbol ascending
    eligible.sort(key=lambda c: (-c.relative_volume, c.symbol))

    selected = eligible[:top_n]
    ranked_candidates: list[RankedCandidate] = []

    for rank_idx, cand in enumerate(selected, start=1):
        op = opening_ranges[cand.symbol]
        intent = size_order_intent(
            candidate=cand,
            opening_range=op,
            session_start_equity=session_start_equity,
        )
        ranked_candidates.append(
            RankedCandidate(
                rank=rank_idx,
                candidate=cand,
                opening_range=op,
                order_intent=intent,
            )
        )

    return ranked_candidates
