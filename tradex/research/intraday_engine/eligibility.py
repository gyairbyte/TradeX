"""Point-in-time liquidity and security-type eligibility for INTRA-001."""
from __future__ import annotations

from .models import TickerMeta
from .spec import IntradaySpec

_EXCLUDED_SECURITY_TYPES = {"otc", "warrant", "right", "unit", "preferred_stock"}


def check_ticker_eligibility(
    ticker_meta: TickerMeta,
    spec: IntradaySpec,
) -> tuple[bool, list[str]]:
    """Return (eligible, reasons) against the locked liquidity/security rules."""
    reasons: list[str] = []
    if not ticker_meta.is_eligible:
        reasons.append("ticker_not_eligible")
    if ticker_meta.prior_close is not None and ticker_meta.prior_close < spec.prior_close_min:
        reasons.append(f"prior_close_{ticker_meta.prior_close}_below_{spec.prior_close_min}")
    if (
        ticker_meta.prior_20_median_dollar_volume is not None
        and ticker_meta.prior_20_median_dollar_volume < spec.prior_dollar_volume_min
    ):
        reasons.append("prior_20_median_dollar_volume_below_threshold")
    if ticker_meta.security_type.lower() in _EXCLUDED_SECURITY_TYPES:
        reasons.append(f"security_type_excluded_{ticker_meta.security_type}")
    return (not reasons), reasons
