"""Session VWAP computation with per-bar reset and no future-bar access."""
from __future__ import annotations

from .models import Session


def compute_session_vwap(session: Session) -> None:
    """Compute typical-price VWAP for all valid bars in ``session``.

    Bars are processed in chronological order. Zero-volume bars contribute a
    typical price of zero to the cumulative numerator and zero to the cumulative
    volume, leaving the VWAP unchanged.
    """
    cum_pv = 0.0
    cum_v = 0.0
    for bar_start in sorted(session.bars):
        bar = session.bars[bar_start]
        if not bar.is_valid:
            continue
        typical = (bar.high + bar.low + bar.close) / 3.0
        bar.typical_price = typical
        bar.cum_price_volume = cum_pv + typical * bar.volume
        bar.cum_volume = cum_v + bar.volume
        cum_pv = bar.cum_price_volume
        cum_v = bar.cum_volume
        if cum_v > 0:
            bar.vwap = cum_pv / cum_v
        else:
            bar.vwap = None


def reset_session_vwap(session: Session) -> None:
    """Clear VWAP-derived fields so computation can be redone."""
    for bar in session.bars.values():
        bar.typical_price = None
        bar.cum_price_volume = None
        bar.cum_volume = None
        bar.vwap = None
