"""Anonymization, price normalization, and packet blinding for LONG-002D3A."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002c.manifest import CandidateSecurity
from tradex.research.long_002c.providers import AlpacaDailyClient
from tradex.research.long_002d.loader import (
    load_candidate_bars,
)
from tradex.research.long_002d3a.models import (
    AnswerKeyRecord,
    BlindedBar,
    PilotCandidate,
    StageAPacket,
    StageBPacket,
)
from tradex.research.long_002d3a.spec import (
    enforce_split_guard,
)

LOOKBACK_BARS = 61  # T-60 to T0 inclusive (61 daily bars)


def get_market_cap_cohort(market_cap: float | None) -> str:
    """Map numeric point-in-time market cap to an anonymized qualitative cohort."""
    if market_cap is None or pd.isna(market_cap):
        return "unknown"
    if market_cap < 3_000_000_000:
        return "< $3B (index exception)"
    elif market_cap < 5_000_000_000:
        return "$3B - $5B (Mid-Cap)"
    elif market_cap < 20_000_000_000:
        return "$5B - $20B (Mid-to-Large Cap)"
    elif market_cap < 200_000_000_000:
        return "$20B - $200B (Large Cap)"
    else:
        return "$200B+ (Mega Cap)"


def generate_blinded_case_packet(
    candidate: PilotCandidate,
    cand_security: CandidateSecurity,
    alpaca: AlpacaDailyClient,
    spy_closes: dict[str, float],
    eligibility_row: dict[str, Any] | None,
    earnings_row: dict[str, Any] | None,
) -> tuple[StageAPacket, StageBPacket, AnswerKeyRecord]:
    """Construct anonymized Stage A packet, Stage B packet, and AnswerKeyRecord.

    Enforces:
    - Zero future bar leakage: historical bars strictly end at candidate.as_of_date (T0).
    - Price normalization: starting value at T-60 scaled to 100.0.
    - Relative time labels: T-60 to T0.
    - Zero identity, dates, or outcomes in reviewer-visible payloads.
    """
    as_of = candidate.as_of_date
    enforce_split_guard(as_of)

    # 1. Load candidate bars strictly from cache
    df_bars_raw, _, _ = load_candidate_bars(cand_security, alpaca)
    if df_bars_raw.empty:
        raise RuntimeError(f"Missing cached bars for security: {candidate.immutable_security_id}")

    # Enforce strict cutoff: zero bars after as_of_date!
    df_bars_prior = df_bars_raw.loc[:as_of].copy()

    # Assert no future bar leaked
    latest_bar_date = df_bars_prior.index[-1]
    if latest_bar_date > as_of:
        raise ValueError(
            f"LEAKAGE BREACH: Bar date {latest_bar_date} exceeds decision cutoff {as_of}!"
        )

    # Take lookback window of up to LOOKBACK_BARS (61 bars: T-60 to T0)
    df_window = df_bars_prior.tail(LOOKBACK_BARS).copy()
    num_bars = len(df_window)
    if num_bars < 20:
        raise ValueError(
            f"Insufficient lookback history ({num_bars} bars) for security {candidate.immutable_security_id} at {as_of}"
        )

    # 2. Normalize price series (starting close at T-(num_bars-1) = 100.0)
    base_close = float(df_window["close"].iloc[0])
    if base_close <= 0:
        raise ValueError(f"Invalid non-positive base close: {base_close}")
    scale_factor = 100.0 / base_close

    norm_open = (df_window["open"] * scale_factor).to_numpy(dtype=float)
    norm_high = (df_window["high"] * scale_factor).to_numpy(dtype=float)
    norm_low = (df_window["low"] * scale_factor).to_numpy(dtype=float)
    norm_close = (df_window["close"] * scale_factor).to_numpy(dtype=float)

    # Moving averages on normalized series
    s_close = pd.Series(norm_close)
    norm_sma20 = s_close.rolling(20, min_periods=20).mean().to_numpy(dtype=float)
    norm_sma50 = s_close.rolling(50, min_periods=50).mean().to_numpy(dtype=float)

    # ATR% 14 (scale-invariant percentage): compute true range on normalized prices
    s_high = pd.Series(norm_high)
    s_low = pd.Series(norm_low)
    prev_close = s_close.shift(1)
    tr = pd.concat([
        s_high - s_low,
        (s_high - prev_close).abs(),
        (s_low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()
    atr_pct_14 = (atr14 / s_close * 100.0).to_numpy(dtype=float)

    # Relative volume (volume / rolling 20d median volume)
    raw_vol = df_window["volume"].to_numpy(dtype=float)
    s_vol = pd.Series(raw_vol)
    vol_median20 = s_vol.rolling(20, min_periods=20).median().to_numpy(dtype=float)
    rel_vol = np.where(vol_median20 > 0, raw_vol / vol_median20, np.nan)

    # 3. Build relative bar list
    relative_bars: list[dict[str, Any]] = []
    # Relative index from -(num_bars - 1) to 0
    start_rel_idx = -(num_bars - 1)

    for i in range(num_bars):
        rel_idx = start_rel_idx + i
        label = "T0" if rel_idx == 0 else f"T{rel_idx}"

        b = BlindedBar(
            relative_index=rel_idx,
            relative_label=label,
            normalized_open=round(float(norm_open[i]), 4),
            normalized_high=round(float(norm_high[i]), 4),
            normalized_low=round(float(norm_low[i]), 4),
            normalized_close=round(float(norm_close[i]), 4),
            relative_volume=round(float(rel_vol[i]), 4) if pd.notna(rel_vol[i]) else None,
            normalized_sma20=round(float(norm_sma20[i]), 4) if pd.notna(norm_sma20[i]) else None,
            normalized_sma50=round(float(norm_sma50[i]), 4) if pd.notna(norm_sma50[i]) else None,
            atr_pct_14=round(float(atr_pct_14[i]), 4) if pd.notna(atr_pct_14[i]) else None,
        )
        relative_bars.append(b.to_dict())

    # 4. Pre-decision momentum and technical metrics
    t0_close = norm_close[-1]
    ret_5 = round((t0_close / norm_close[-6] - 1.0) * 100.0, 4) if num_bars >= 6 else None
    ret_10 = round((t0_close / norm_close[-11] - 1.0) * 100.0, 4) if num_bars >= 11 else None
    ret_20 = round((t0_close / norm_close[-21] - 1.0) * 100.0, 4) if num_bars >= 21 else None
    ret_60 = round((t0_close / norm_close[0] - 1.0) * 100.0, 4) if num_bars >= 61 else None

    # SPY context
    window_dates = df_window.index.tolist()
    spy_t0 = spy_closes.get(as_of)
    spy_ret_20 = None
    stock_minus_spy_20 = None
    if spy_t0 is not None and len(window_dates) >= 21:
        date_t20 = window_dates[-21]
        spy_t20 = spy_closes.get(date_t20)
        if spy_t20 is not None and spy_t20 > 0:
            spy_ret_20 = round((spy_t0 / spy_t20 - 1.0) * 100.0, 4)
            if ret_20 is not None:
                stock_minus_spy_20 = round(ret_20 - spy_ret_20, 4)

    tech_metrics = {
        "pre_decision_normalized_close_t0": round(float(t0_close), 4),
        "return_5_bars_pct": ret_5,
        "return_10_bars_pct": ret_10,
        "return_20_bars_pct": ret_20,
        "return_60_bars_pct": ret_60,
        "relative_volume_t0": round(float(rel_vol[-1]), 4) if pd.notna(rel_vol[-1]) else None,
        "atr_pct_14_t0": round(float(atr_pct_14[-1]), 4) if pd.notna(atr_pct_14[-1]) else None,
        "above_sma20_t0": bool(t0_close >= norm_sma20[-1]) if pd.notna(norm_sma20[-1]) else None,
        "above_sma50_t0": bool(t0_close >= norm_sma50[-1]) if pd.notna(norm_sma50[-1]) else None,
    }

    spy_context = {
        "spy_return_20_bars_pct": spy_ret_20,
        "stock_minus_spy_20_bars_pct": stock_minus_spy_20,
        "benchmark": "SPY",
    }

    warnings: list[str] = []
    if num_bars < 61:
        warnings.append(f"Lookback history contains {num_bars} bars (< 61 sessions).")

    stage_a = StageAPacket(
        case_id=candidate.case_id,
        relative_bars=relative_bars,
        technical_metrics=tech_metrics,
        spy_context=spy_context,
        data_quality_warnings=warnings,
    )

    # 5. Build Stage B packet with approved PIT fields
    mkt_cap = eligibility_row.get("market_cap") if eligibility_row else None
    cohort_type = eligibility_row.get("cohort_type", "established") if eligibility_row else "established"
    trading_sessions = eligibility_row.get("trading_history_sessions", 252) if eligibility_row else 252

    pit_mkt_cap_cohort = get_market_cap_cohort(mkt_cap)
    pit_trading_cohort = f"{cohort_type} ({trading_sessions}+ sessions history)"

    earnings_status = earnings_row.get("schedule_status", "unknown") if earnings_row else "unknown"
    announcement_timing = earnings_row.get("announcement_timing") if earnings_row else None
    sessions_to_earnings = earnings_row.get("sessions_to_earnings") if earnings_row else None

    pit_context = {
        "security_type": "U.S. Common Stock (Operating Company)",
        "market_cap_cohort": pit_mkt_cap_cohort,
        "trading_history_cohort": pit_trading_cohort,
        "pit_earnings_schedule_status": earnings_status,
        "pit_earnings_announcement_timing": announcement_timing,
        "pit_sessions_to_next_earnings": sessions_to_earnings,
        "reported_financial_facts": "unavailable_in_local_artifacts (fail-closed null)",
        "analyst_revisions": "unavailable_in_local_artifacts (fail-closed null)",
        "catalyst_news_feed": "unavailable_in_local_artifacts (fail-closed null)",
    }

    stage_b = StageBPacket(
        case_id=candidate.case_id,
        stage_a=stage_a.to_dict(),
        pit_context=pit_context,
        data_confidence_status="verified_local_pit_artifacts_only",
    )

    # 6. Build Answer Key Record
    answer_key = AnswerKeyRecord(
        case_id=candidate.case_id,
        sample_stratum=candidate.sample_stratum,
        immutable_security_id=candidate.immutable_security_id,
        ticker=candidate.ticker_at_decision,
        decision_date=candidate.as_of_date,
        cutoff_time=candidate.cutoff_time,
        episode_id=candidate.episode_id,
        clean_target_reached=candidate.clean_target_reached,
        target_progress_ratio=round(candidate.target_progress_ratio, 4),
        near_miss=candidate.near_miss,
        adverse_excursion=candidate.adverse_excursion,
        mfe_pct=round(candidate.mfe_pct, 4) if candidate.mfe_pct is not None else None,
        mae_pct=round(candidate.mae_pct, 4) if candidate.mae_pct is not None else None,
        time_to_target=candidate.time_to_target,
    )

    return stage_a, stage_b, answer_key
