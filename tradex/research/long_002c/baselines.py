"""Frozen baseline comparators for LONG-002C.

Implements universe base rate, simple momentum, SPY-relative momentum, PIT-sector relative momentum,
volatility-aware momentum (fixed 50/50), and the legacy TradeX long-term scorer with fresh LongWeights().
Evaluates comparators on identical common observations.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from tradex.research.long_002c.models import BaselineComparatorOutput
from tradex.signals.weights import LongWeights


def compute_simple_momentum(closes: list[float], lookback: int) -> float | None:
    """Compute price momentum return over lookback sessions: close_t / close_{t-lookback} - 1."""
    if len(closes) < lookback + 1:
        return None
    past_close = closes[-(lookback + 1)]
    curr_close = closes[-1]
    if past_close <= 0:
        return None
    return curr_close / past_close - 1.0


def compute_legacy_tradex_score(history_df: pd.DataFrame) -> float:
    """Run existing TradeX long-term scorer with fresh repository defaults (no saved weights)."""
    from tradex.signals.long_term import score

    fresh_weights = LongWeights()
    result = score(history_df, weights=fresh_weights)
    return float(result.get("score", 0.0))


def evaluate_baselines_for_date(
    as_of_date: str,
    cutoff_time: str,
    securities_data: dict[str, dict[str, Any]],
    # mapping immutable_security_id -> {
    #   "ticker": str,
    #   "history_df": pd.DataFrame (daily bars up to as_of_date),
    #   "atr_14": float | None,
    #   "sector": str | None,
    #   "universe_eligible": bool
    # }
    spy_history_df: pd.DataFrame | None = None,
    sector_histories: dict[str, pd.DataFrame] | None = None,
) -> list[BaselineComparatorOutput]:
    """Evaluate all baseline comparators across common eligible observations on a single date."""
    outputs: list[BaselineComparatorOutput] = []

    # Filter to eligible securities on this date
    eligible_sec_ids = [
        sec_id
        for sec_id, d in securities_data.items()
        if d.get("universe_eligible", True) and not d.get("history_df").empty
    ]

    if not eligible_sec_ids:
        return outputs

    # 1. Base rate
    for sec_id in eligible_sec_ids:
        ticker = securities_data[sec_id].get("ticker", "")
        outputs.append(
            BaselineComparatorOutput(
                immutable_security_id=sec_id,
                as_of_date=as_of_date,
                cutoff_time=cutoff_time,
                comparator_id="universe_base_rate",
                ticker_at_decision=ticker,
                comparator_family="universe_base_rate",
                raw_score_or_return=1.0,
                cross_sectional_rank=1,
                cross_sectional_percentile=100.0,
                top_10_flag=True,
                top_25_flag=True,
            )
        )

    # Compute SPY returns for each lookback if SPY is provided
    spy_mom: dict[int, float | None] = {}
    if spy_history_df is not None and not spy_history_df.empty:
        spy_closes = spy_history_df["close"].tolist()
        for lb in [5, 10, 20, 60]:
            spy_mom[lb] = compute_simple_momentum(spy_closes, lb)

    lookbacks = [5, 10, 20, 60]

    # Pre-calculate simple momentum and ATR% for all securities
    mom_values: dict[int, dict[str, float | None]] = {lb: {} for lb in lookbacks}
    atr_pct_values: dict[str, float | None] = {}

    for sec_id in eligible_sec_ids:
        df = securities_data[sec_id]["history_df"]
        closes = df["close"].tolist()
        for lb in lookbacks:
            mom_values[lb][sec_id] = compute_simple_momentum(closes, lb)

        atr = securities_data[sec_id].get("atr_14")
        last_close = closes[-1] if closes else 0.0
        if atr is not None and last_close > 0:
            atr_pct_values[sec_id] = atr / last_close
        else:
            atr_pct_values[sec_id] = None

    # 2. Simple momentum for each lookback
    for lb in lookbacks:
        comp_id = f"simple_momentum_{lb}"
        raw_map = {sec_id: mom_values[lb][sec_id] for sec_id in eligible_sec_ids}
        valid_pairs = [(sec_id, val) for sec_id, val in raw_map.items() if val is not None]
        valid_pairs.sort(key=lambda p: p[1], reverse=True)

        n_valid = len(valid_pairs)
        for rank_idx, (sec_id, val) in enumerate(valid_pairs):
            rank = rank_idx + 1
            pct = 100.0 * (n_valid - rank_idx) / n_valid if n_valid > 0 else 0.0
            ticker = securities_data[sec_id].get("ticker", "")
            outputs.append(
                BaselineComparatorOutput(
                    immutable_security_id=sec_id,
                    as_of_date=as_of_date,
                    cutoff_time=cutoff_time,
                    comparator_id=comp_id,
                    ticker_at_decision=ticker,
                    comparator_family="simple_momentum",
                    raw_score_or_return=round(val, 6),
                    cross_sectional_rank=rank,
                    cross_sectional_percentile=round(pct, 2),
                    top_10_flag=pct >= 90.0,
                    top_25_flag=pct >= 75.0,
                )
            )

    # 3. SPY-relative momentum
    for lb in lookbacks:
        comp_id = f"spy_relative_{lb}"
        spy_val = spy_mom.get(lb)
        if spy_val is not None:
            raw_map = {}
            for sec_id in eligible_sec_ids:
                sm = mom_values[lb][sec_id]
                raw_map[sec_id] = (sm - spy_val) if sm is not None else None

            valid_pairs = [(sec_id, val) for sec_id, val in raw_map.items() if val is not None]
            valid_pairs.sort(key=lambda p: p[1], reverse=True)
            n_valid = len(valid_pairs)

            for rank_idx, (sec_id, val) in enumerate(valid_pairs):
                rank = rank_idx + 1
                pct = 100.0 * (n_valid - rank_idx) / n_valid if n_valid > 0 else 0.0
                ticker = securities_data[sec_id].get("ticker", "")
                outputs.append(
                    BaselineComparatorOutput(
                        immutable_security_id=sec_id,
                        as_of_date=as_of_date,
                        cutoff_time=cutoff_time,
                        comparator_id=comp_id,
                        ticker_at_decision=ticker,
                        comparator_family="spy_relative",
                        raw_score_or_return=round(val, 6),
                        cross_sectional_rank=rank,
                        cross_sectional_percentile=round(pct, 2),
                        top_10_flag=pct >= 90.0,
                        top_25_flag=pct >= 75.0,
                    )
                )

    # 4. PIT-sector relative momentum
    for lb in lookbacks:
        comp_id = f"pit_sector_relative_{lb}"
        raw_map = {}
        for sec_id in eligible_sec_ids:
            sec_mom = mom_values[lb][sec_id]
            sector = securities_data[sec_id].get("sector")
            sec_bench_mom = None
            if sector and sector_histories and sector in sector_histories:
                s_df = sector_histories[sector]
                if not s_df.empty:
                    sec_bench_mom = compute_simple_momentum(s_df["close"].tolist(), lb)

            if sec_mom is not None and sec_bench_mom is not None:
                raw_map[sec_id] = sec_mom - sec_bench_mom
            else:
                raw_map[sec_id] = None

        valid_pairs = [(sec_id, val) for sec_id, val in raw_map.items() if val is not None]
        valid_pairs.sort(key=lambda p: p[1], reverse=True)
        n_valid = len(valid_pairs)

        for rank_idx, (sec_id, val) in enumerate(valid_pairs):
            rank = rank_idx + 1
            pct = 100.0 * (n_valid - rank_idx) / n_valid if n_valid > 0 else 0.0
            ticker = securities_data[sec_id].get("ticker", "")
            outputs.append(
                BaselineComparatorOutput(
                    immutable_security_id=sec_id,
                    as_of_date=as_of_date,
                    cutoff_time=cutoff_time,
                    comparator_id=comp_id,
                    ticker_at_decision=ticker,
                    comparator_family="sector_relative",
                    raw_score_or_return=round(val, 6),
                    cross_sectional_rank=rank,
                    cross_sectional_percentile=round(pct, 2),
                    top_10_flag=pct >= 90.0,
                    top_25_flag=pct >= 75.0,
                )
            )

    # 5. Volatility-aware momentum (fixed 50% momentum percentile + 50% ATR% percentile)
    # Compute ATR% percentiles across valid securities
    valid_atrs = [(sec_id, v) for sec_id, v in atr_pct_values.items() if v is not None]
    valid_atrs.sort(key=lambda p: p[1], reverse=True)
    n_atr = len(valid_atrs)
    atr_pct_ranks = {
        sec_id: (100.0 * (n_atr - idx) / n_atr) for idx, (sec_id, _) in enumerate(valid_atrs)
    }

    for lb in lookbacks:
        comp_id = f"volatility_aware_momentum_{lb}"
        raw_map = {}
        # Calculate momentum percentiles
        v_mom = [(sec_id, v) for sec_id, v in mom_values[lb].items() if v is not None]
        v_mom.sort(key=lambda p: p[1], reverse=True)
        n_m = len(v_mom)
        mom_pct_ranks = {
            sec_id: (100.0 * (n_m - idx) / n_m) for idx, (sec_id, _) in enumerate(v_mom)
        }

        for sec_id in eligible_sec_ids:
            mp = mom_pct_ranks.get(sec_id)
            ap = atr_pct_ranks.get(sec_id)
            if mp is not None and ap is not None:
                # Fixed 50/50 weighting: no tuning
                raw_map[sec_id] = 0.5 * mp + 0.5 * ap
            else:
                raw_map[sec_id] = None

        valid_pairs = [(sec_id, val) for sec_id, val in raw_map.items() if val is not None]
        valid_pairs.sort(key=lambda p: p[1], reverse=True)
        n_valid = len(valid_pairs)

        for rank_idx, (sec_id, val) in enumerate(valid_pairs):
            rank = rank_idx + 1
            pct = 100.0 * (n_valid - rank_idx) / n_valid if n_valid > 0 else 0.0
            ticker = securities_data[sec_id].get("ticker", "")
            outputs.append(
                BaselineComparatorOutput(
                    immutable_security_id=sec_id,
                    as_of_date=as_of_date,
                    cutoff_time=cutoff_time,
                    comparator_id=comp_id,
                    ticker_at_decision=ticker,
                    comparator_family="volatility_aware_momentum",
                    raw_score_or_return=round(val, 4),
                    cross_sectional_rank=rank,
                    cross_sectional_percentile=round(pct, 2),
                    top_10_flag=pct >= 90.0,
                    top_25_flag=pct >= 75.0,
                )
            )

    # 6. Legacy TradeX Long-term Scorer
    legacy_map: dict[str, float | None] = {}
    for sec_id in eligible_sec_ids:
        df = securities_data[sec_id]["history_df"]
        if len(df) >= 30:
            try:
                legacy_map[sec_id] = compute_legacy_tradex_score(df)
            except Exception:  # noqa: BLE001
                legacy_map[sec_id] = None
        else:
            legacy_map[sec_id] = None

    valid_pairs = [(sec_id, val) for sec_id, val in legacy_map.items() if val is not None]
    valid_pairs.sort(key=lambda p: p[1], reverse=True)
    n_valid = len(valid_pairs)

    for rank_idx, (sec_id, val) in enumerate(valid_pairs):
        rank = rank_idx + 1
        pct = 100.0 * (n_valid - rank_idx) / n_valid if n_valid > 0 else 0.0
        ticker = securities_data[sec_id].get("ticker", "")
        outputs.append(
            BaselineComparatorOutput(
                immutable_security_id=sec_id,
                as_of_date=as_of_date,
                cutoff_time=cutoff_time,
                comparator_id="legacy_tradex_scorer",
                ticker_at_decision=ticker,
                comparator_family="legacy_tradex_scorer",
                raw_score_or_return=round(val, 2),
                cross_sectional_rank=rank,
                cross_sectional_percentile=round(pct, 2),
                top_10_flag=pct >= 90.0,
                top_25_flag=pct >= 75.0,
            )
        )

    return outputs
