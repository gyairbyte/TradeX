"""Opening-drive qualification state frozen at 10:00 AM Eastern."""
from __future__ import annotations

from statistics import median

from .models import Bar, OpeningDriveState, Session, TickerMeta
from .spec import IntradaySpec

_OPENING_DRIVE_BAR_COUNT = 6
_REQUIRED_PRIOR_SESSIONS = 20


def _first_six_bars(session: Session) -> list[Bar]:
    """Return the first six completed regular-session bars if all are present and valid."""
    first_six = [
        session.bars[g]
        for g in sorted(session.grid)[:_OPENING_DRIVE_BAR_COUNT]
        if g in session.bars
    ]
    if len(first_six) != _OPENING_DRIVE_BAR_COUNT:
        return []
    if any(not b.is_valid for b in first_six):
        return []
    return first_six


def _prior_six_bar_cumulative_volumes(
    prior_sessions: list[Session],
) -> list[float]:
    """Return the 6-bar cumulative volumes for the most recent 20 *complete* prior sessions.

    A prior session is complete when all of its first six regular-session bars are
    present and valid.  The function filters for complete sessions, then takes the
    newest 20 by session date.  If fewer than 20 complete sessions are available,
    an empty list is returned.
    """
    sorted_prior = sorted(prior_sessions, key=lambda s: s.session_date)

    def _is_complete(session: Session) -> bool:
        # A prior session is complete only when every expected regular-session grid
        # position is present and valid.  The six-bar cumulative volume is still
        # computed from the first six bars below.
        if len(session.bars) != len(session.grid):
            return False
        for g in session.grid:
            bar = session.bars.get(g)
            if bar is None or not bar.is_valid:
                return False
        return True

    complete = [s for s in sorted_prior if _is_complete(s)]
    recent = complete[-_REQUIRED_PRIOR_SESSIONS:]
    if len(recent) < _REQUIRED_PRIOR_SESSIONS:
        return []

    return [sum(s.bars[g].volume for g in sorted(s.grid)[:_OPENING_DRIVE_BAR_COUNT]) for s in recent]


def evaluate_opening_drive(
    session: Session,
    prior_sessions: list[Session],
    ticker_meta: TickerMeta,
    spec: IntradaySpec,
) -> OpeningDriveState:
    """Return the frozen 10:00 AM opening-drive qualification state."""
    reasons: list[str] = []
    first_six = _first_six_bars(session)
    missing_bars = _OPENING_DRIVE_BAR_COUNT - len(first_six) + sum(
        1 for b in first_six if not b.is_valid
    )

    if missing_bars > 0:
        reasons.append(f"missing_or_invalid_first_six_bars={missing_bars}")

    if not first_six:
        return OpeningDriveState(
            qualified=False,
            return_pct=None,
            close_at_10am=None,
            vwap_at_10am=None,
            cumulative_volume=None,
            median_prior_cumulative_volume=None,
            volume_multiple=None,
            missing_bars=missing_bars,
            reasons=reasons,
        )

    if not ticker_meta.is_eligible:
        reasons.append("ticker_not_eligible")

    if ticker_meta.prior_close is not None and ticker_meta.prior_close < spec.prior_close_min:
        reasons.append(f"prior_close_{ticker_meta.prior_close}_below_{spec.prior_close_min}")

    if (
        ticker_meta.prior_20_median_dollar_volume is not None
        and ticker_meta.prior_20_median_dollar_volume < spec.prior_dollar_volume_min
    ):
        reasons.append(
            f"prior_20_median_dollar_volume_{ticker_meta.prior_20_median_dollar_volume}_"
            f"below_{spec.prior_dollar_volume_min}"
        )

    excluded_types = {"otc", "warrant", "right", "unit", "preferred_stock"}
    if ticker_meta.security_type.lower() in excluded_types:
        reasons.append(f"security_type_excluded_{ticker_meta.security_type}")

    open_930 = first_six[0].open
    close_955 = first_six[-1].close
    vwap_955 = first_six[-1].vwap
    cumulative_volume = sum(b.volume for b in first_six)

    if cumulative_volume <= 0:
        reasons.append("cumulative_volume_nonpositive")

    if vwap_955 is None:
        reasons.append("vwap_unavailable_at_10am")

    prior_volumes = _prior_six_bar_cumulative_volumes(prior_sessions)
    median_prior = median(prior_volumes) if prior_volumes else None

    if not prior_volumes:
        reasons.append("insufficient_prior_20_complete_sessions_for_volume_baseline")
    elif median_prior is None or median_prior <= 0:
        reasons.append("nonpositive_median_prior_20_session_volume_baseline")

    volume_multiple = (
        cumulative_volume / median_prior
        if median_prior is not None and median_prior > 0
        else None
    )

    if vwap_955 is not None:
        return_pct = 100.0 * (close_955 / open_930 - 1.0)
        close_above_vwap = close_955 > vwap_955
        volume_ok = volume_multiple is not None and volume_multiple >= spec.opening_drive_min_volume_multiple
        return_ok = return_pct >= spec.opening_drive_min_return_pct

        if not return_ok:
            reasons.append(
                f"return_pct_{return_pct:.4f}_below_min_{spec.opening_drive_min_return_pct}"
            )
        if not close_above_vwap:
            reasons.append("close_at_10am_not_above_vwap")
        if not volume_ok:
            reasons.append(
                f"volume_multiple_{volume_multiple}_below_min_{spec.opening_drive_min_volume_multiple}"
                if volume_multiple is not None
                else "volume_multiple_unavailable"
            )

        qualified = (
            missing_bars == 0
            and ticker_meta.is_eligible
            and (ticker_meta.prior_close is None or ticker_meta.prior_close >= spec.prior_close_min)
            and (ticker_meta.prior_20_median_dollar_volume is None or ticker_meta.prior_20_median_dollar_volume >= spec.prior_dollar_volume_min)
            and ticker_meta.security_type.lower() not in {"otc", "warrant", "right", "unit", "preferred_stock"}
            and cumulative_volume > 0
            and return_ok
            and close_above_vwap
            and volume_ok
        )
    else:
        return_pct = None
        qualified = False

    return OpeningDriveState(
        qualified=qualified,
        return_pct=return_pct,
        close_at_10am=close_955,
        vwap_at_10am=vwap_955,
        cumulative_volume=cumulative_volume,
        median_prior_cumulative_volume=median_prior,
        volume_multiple=volume_multiple,
        missing_bars=missing_bars,
        reasons=reasons,
    )
