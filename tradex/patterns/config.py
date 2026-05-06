"""
Configurable thresholds for pattern mining and matching.

Three built-in profiles cover most use cases. Override any field
by passing a PatternConfig directly to miner/matcher functions.
"""
from dataclasses import dataclass


@dataclass
class PatternConfig:
    # ── What counts as a "major move" ────────────────────────────────────────
    runup_pct: float = 15.0       # % gain over move_days to qualify as a run-up
    decline_pct: float = 12.0     # % loss over move_days to qualify as a decline
                                  # (asymmetric: stocks fall faster than they rise)
    move_days: int = 5            # trading days the move plays out over

    # ── Pre-event window to extract and fingerprint ───────────────────────────
    lookback_days: int = 10       # trading days before the event to capture
                                  # 10 days ≈ 2 calendar weeks

    # ── History depth for mining ──────────────────────────────────────────────
    history_years: int = 3        # how far back to mine for events
                                  # 3 years captures bull (2023-24), bear (2022), recovery

    # ── Fingerprint quality gate ──────────────────────────────────────────────
    min_events: int = 20          # minimum events needed to trust a fingerprint
                                  # below 20 the average is too noisy

    # ── Similarity alerting ───────────────────────────────────────────────────
    alert_threshold: float = 75.0 # similarity % above which we fire an alert


# ── Built-in profiles ─────────────────────────────────────────────────────────

PROFILES: dict[str, PatternConfig] = {
    "conservative": PatternConfig(
        runup_pct=20.0,
        decline_pct=16.0,
        move_days=5,
        lookback_days=10,
        alert_threshold=78.0,
        # For: AAPL, MSFT, GOOGL, SPY — large caps move less so threshold is higher
    ),
    "standard": PatternConfig(
        # Default — works well for most mid/large cap individual stocks
    ),
    "volatile": PatternConfig(
        runup_pct=30.0,
        decline_pct=25.0,
        move_days=5,
        lookback_days=10,
        alert_threshold=70.0,
        # For: SOXL, TQQQ, MSTR, NVDA, TSLA — these move 2-3x more than typical stocks
        # Lower alert threshold because volatile fingerprints are naturally noisier
    ),
}


def get_profile(name: str) -> PatternConfig:
    if name not in PROFILES:
        raise ValueError(f"Profile must be one of {list(PROFILES)}. Got: '{name}'")
    return PROFILES[name]
