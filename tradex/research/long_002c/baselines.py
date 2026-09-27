"""Frozen baseline comparators for LONG-002C.

Implements universe base rate, simple momentum, SPY-relative momentum, PIT-sector relative momentum,
volatility-aware momentum (fixed 50/50), and the legacy TradeX long-term scorer with fresh LongWeights().
Evaluates comparators on identical common observations.
"""
from __future__ import annotations

import bisect
from typing import Any

import numpy as np
import pandas as pd

from tradex.research.long_002c.models import (
    BaselineComparatorOutput,
    OutcomeLabelRecord,
)
from tradex.signals.indicators import add_indicators
from tradex.signals.long_term import score
from tradex.signals.weights import LongWeights


def compute_simple_momentum(closes: list[float], lookback: int) -> float | None:
    """Compute price momentum return over lookback sessions: close_t / close_{t-lookback} - 1."""
    if len(closes) < lookback + 1:
        return None
    past_close = closes[-(lookback + 1)]
    curr_close = closes[-1]
    if past_close <= 0 or not np.isfinite(past_close) or not np.isfinite(curr_close):
        return None
    return curr_close / past_close - 1.0


def compute_simple_momentum_series(
    closes: np.ndarray | list[float], lookback: int
) -> list[float | None]:
    """Compute price momentum return over lookback sessions for all historical prefixes.

    Equivalent to calling compute_simple_momentum(closes[:k+1], lookback)
    for all 0 <= k < len(closes). Prefixes of length < lookback + 1 evaluate to None.
    """
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    if n < lookback + 1:
        return [None] * n

    res: list[float | None] = [None] * lookback
    curr = arr[lookback:]
    past = arr[:-lookback]

    valid = (past > 0) & np.isfinite(past) & np.isfinite(curr)
    safe_past = np.where(valid, past, 1.0)
    moms = curr / safe_past - 1.0

    for val, is_v in zip(moms, valid):
        res.append(float(val) if is_v else None)

    return res


def compute_legacy_tradex_score(history_df: pd.DataFrame, weights: LongWeights | None = None) -> float:
    """Run existing TradeX long-term scorer with fresh repository defaults (no saved weights)."""
    effective_weights = weights if weights is not None else LongWeights()
    result = score(history_df, weights=effective_weights)
    return float(result.get("score", 0.0))


def compute_legacy_tradex_scores_series(
    history_df: pd.DataFrame, weights: LongWeights | None = None
) -> list[float | None]:
    """Compute legacy TradeX score causally for each prefix of history_df.

    Equivalent to calling compute_legacy_tradex_score(history_df.iloc[:k+1], weights)
    for all 0 <= k < len(history_df). Prefixes of length < 30 evaluate to None.
    Causal expanding Bollinger Band width percentile rank matches Pandas Series.rank(pct=True).iloc[-1].
    """
    if history_df is None or history_df.empty:
        return []

    n = len(history_df)
    if n < 30:
        return [None] * n

    effective_weights = weights if weights is not None else LongWeights()

    try:
        df_ind = add_indicators(history_df)
    except Exception:  # noqa: BLE001
        return [None] * n

    scores: list[float | None] = [None] * n

    close_arr = df_ind["close"].to_numpy(dtype=float)
    ema50_arr = df_ind["ema_50"].to_numpy(dtype=float)
    rsi_arr = df_ind["rsi"].to_numpy(dtype=float)
    macd_arr = df_ind["macd"].to_numpy(dtype=float)
    macd_sig_arr = df_ind["macd_signal"].to_numpy(dtype=float)
    bb_width_arr = df_ind["bb_width"].to_numpy(dtype=float)

    vol_ratio_s = df_ind["volume_ratio"]
    vol_ratio_mean8 = vol_ratio_s.rolling(8, min_periods=1).mean().to_numpy(dtype=float)

    sorted_bb: list[float] = []

    for i in range(n):
        bw = bb_width_arr[i]
        if not np.isnan(bw):
            bisect.insort(sorted_bb, bw)
            left = bisect.bisect_left(sorted_bb, bw)
            right = bisect.bisect_right(sorted_bb, bw)
            bb_pct = (left + right + 1) / (2.0 * len(sorted_bb))
        else:
            bb_pct = np.nan

        if i >= 29:
            sig = 0
            if close_arr[i] > ema50_arr[i]:
                sig += effective_weights.secular_uptrend
            if 40.0 <= rsi_arr[i] <= 65.0:
                sig += effective_weights.rsi_healthy
            if vol_ratio_mean8[i] >= 1.15:
                sig += effective_weights.volume_accumulation
            if macd_arr[i] > macd_sig_arr[i]:
                sig += effective_weights.macd_bullish
            if bb_pct < 0.25:
                sig += effective_weights.bb_coil
            scores[i] = float(min(sig, 100))

    return scores


def evaluate_baselines_for_date(
    as_of_date: str,
    cutoff_time: str,
    securities_data: dict[str, dict[str, Any]],
    # mapping immutable_security_id -> {
    #   "ticker": str,
    #   "history_df": pd.DataFrame (daily bars up to as_of_date),
    #   "atr_14": float | None,
    #   "sector": str | None,
    #   "universe_eligible": bool (retained for audit),
    #   "raw_outcome_eligible": bool,
    #   "has_history": bool (optional, PERF-003),
    #   "precomputed_legacy_score": float | None (optional, PERF-003),
    #   "precomputed_momentum": dict[int, float | None] (optional, PERF-003),
    #   "precomputed_atr_pct": float | None (optional, PERF-003),
    # }
    spy_history_df: pd.DataFrame | None = None,
    sector_histories: dict[str, pd.DataFrame] | None = None,
    *,
    spy_momentum: dict[int, float | None] | None = None,
) -> list[BaselineComparatorOutput]:
    """Evaluate all baseline comparators across common eligible observations on a single date."""
    outputs: list[BaselineComparatorOutput] = []

    # Filter to eligible securities on this date (strictly requires raw_outcome_eligible is True)
    eligible_sec_ids = [
        sec_id
        for sec_id, d in securities_data.items()
        if (
            d.get("raw_outcome_eligible", False) is True
            and (
                d.get("has_history", False)
                or (d.get("history_df") is not None and not d.get("history_df").empty)
            )
        )
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
    if spy_momentum is not None:
        spy_mom = spy_momentum
    elif spy_history_df is not None and not spy_history_df.empty:
        spy_closes = spy_history_df["close"].tolist()
        for lb in [5, 10, 20, 60]:
            spy_mom[lb] = compute_simple_momentum(spy_closes, lb)

    lookbacks = [5, 10, 20, 60]

    # Pre-calculate simple momentum and ATR% for all securities
    mom_values: dict[int, dict[str, float | None]] = {lb: {} for lb in lookbacks}
    atr_pct_values: dict[str, float | None] = {}

    for sec_id in eligible_sec_ids:
        sec_d = securities_data[sec_id]
        pre_mom = sec_d.get("precomputed_momentum")
        if pre_mom is not None:
            for lb in lookbacks:
                mom_values[lb][sec_id] = pre_mom.get(lb)
        else:
            df = sec_d.get("history_df")
            closes = df["close"].tolist() if (df is not None and not df.empty) else []
            for lb in lookbacks:
                mom_values[lb][sec_id] = compute_simple_momentum(closes, lb)

        if "precomputed_atr_pct" in sec_d:
            atr_pct_values[sec_id] = sec_d["precomputed_atr_pct"]
        else:
            df = sec_d.get("history_df")
            closes = df["close"].tolist() if (df is not None and not df.empty) else []
            atr = sec_d.get("atr_14")
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
    local_weights = LongWeights()
    for sec_id in eligible_sec_ids:
        sec_d = securities_data[sec_id]
        if "precomputed_legacy_score" in sec_d:
            legacy_map[sec_id] = sec_d["precomputed_legacy_score"]
        else:
            df = sec_d.get("history_df")
            if df is not None and len(df) >= 30:
                try:
                    legacy_map[sec_id] = compute_legacy_tradex_score(df, weights=local_weights)
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


def select_winning_baseline(
    baseline_outputs: list[BaselineComparatorOutput],
    outcomes: list[OutcomeLabelRecord],
    primary_cutoff_time: str | None = "20:30",
) -> dict[str, Any]:
    """Empirically select the strongest baseline comparator using the locked primary-endpoint decile lift rule.

    Locked evaluation criteria:
    - Evaluated on the common observation set across all candidate comparators.
    - Primary population: 20:30 observations by default (primary_cutoff_time).
    - Primary endpoint: Clean +10% within 10 sessions (clean_target_reached on +10%/10).
    - Primary metric: Top-decile (top 10%) clean-target rate and lift vs universe base rate.
    - Secondary metric: Top-quartile (top 25%) clean-target rate and lift.
    - Tie-break: Higher top-decile lift -> higher top-quartile lift -> simpler/shorter lookback.
    """
    # 1. Map observation key (sec_id, date, cutoff) to primary clean target outcome
    primary_outcomes: dict[tuple[str, str, str], bool] = {
        (o.immutable_security_id, o.as_of_date, o.cutoff_time): o.clean_target_reached
        for o in outcomes
        if o.target_pct == 10.0
        and o.horizon_sessions == 10
        and (primary_cutoff_time is None or o.cutoff_time == primary_cutoff_time)
    }

    if not primary_outcomes:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_primary_outcomes",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_primary_outcomes",
            "table": {},
        }

    # Group baseline records by comparator
    by_comp: dict[str, dict[tuple[str, str, str], BaselineComparatorOutput]] = {}
    for b in baseline_outputs:
        key = (b.immutable_security_id, b.as_of_date, b.cutoff_time)
        by_comp.setdefault(b.comparator_id, {})[key] = b

    candidate_ids = [cid for cid in by_comp if cid != "universe_base_rate"]
    if not candidate_ids:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_candidate_comparators",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_candidate_comparators",
            "table": {},
        }

    PERMITTED_WINNER_FAMILIES = {
        "simple_momentum",
        "spy_relative",
        "sector_relative",
        "volatility_aware_momentum",
    }

    # Intersect ONLY comparator families eligible to win (excluding legacy_tradex_scorer)
    winner_candidate_ids = [
        cid for cid in candidate_ids
        if any(b.comparator_family in PERMITTED_WINNER_FAMILIES for b in by_comp[cid].values())
    ]
    if not winner_candidate_ids:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_candidate_comparators",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_candidate_comparators",
            "table": {},
        }

    # 2. Compute strict common observation set across winner-eligible comparators and primary outcomes
    common_keys = set(primary_outcomes.keys())
    for cid in winner_candidate_ids:
        common_keys &= set(by_comp[cid].keys())

    if not common_keys:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_common_observations",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_common_observations",
            "table": {},
        }

    # 3. Base rate on common observations
    common_clean_count = sum(1 for k in common_keys if primary_outcomes.get(k, False))
    common_total = len(common_keys)
    base_rate = common_clean_count / common_total if common_total > 0 else 0.0

    # 4. Evaluate each candidate on common observations
    table: dict[str, dict[str, Any]] = {}
    candidate_metrics: list[dict[str, Any]] = []


    family_simplicity_rank = {
        "simple_momentum": 1,
        "spy_relative": 2,
        "volatility_aware_momentum": 3,
        "sector_relative": 4,
        "legacy_tradex_scorer": 5,
    }

    for cid in sorted(candidate_ids):
        comp_records = by_comp[cid]
        comp_family = next(iter(comp_records.values())).comparator_family

        # Lookback extraction for tie-break
        lookback = 999
        for part in cid.split("_"):
            if part.isdigit():
                lookback = int(part)
                break

        valid_common_keys = [k for k in common_keys if k in comp_records]
        if not valid_common_keys:
            continue

        top_10_keys = [k for k in valid_common_keys if comp_records[k].top_10_flag]
        top_25_keys = [k for k in valid_common_keys if comp_records[k].top_25_flag]

        top_10_clean = sum(1 for k in top_10_keys if primary_outcomes.get(k, False))
        top_25_clean = sum(1 for k in top_25_keys if primary_outcomes.get(k, False))

        top_10_rate = (top_10_clean / len(top_10_keys)) if top_10_keys else 0.0
        top_25_rate = (top_25_clean / len(top_25_keys)) if top_25_keys else 0.0

        top_10_lift = (top_10_rate / base_rate) if base_rate > 0 else 1.0
        top_25_lift = (top_25_rate / base_rate) if base_rate > 0 else 1.0

        is_winner_eligible = comp_family in PERMITTED_WINNER_FAMILIES

        metrics = {
            "comparator_id": cid,
            "comparator_family": comp_family,
            "winner_eligible": is_winner_eligible,
            "lookback": lookback,
            "common_observations_evaluated": len(valid_common_keys),
            "base_rate": round(base_rate, 6),
            "top_10_count": len(top_10_keys),
            "top_10_clean_count": top_10_clean,
            "top_10_rate": round(top_10_rate, 6),
            "top_10_lift": round(top_10_lift, 4),
            "top_25_count": len(top_25_keys),
            "top_25_clean_count": top_25_clean,
            "top_25_rate": round(top_25_rate, 6),
            "top_25_lift": round(top_25_lift, 4),
            "simplicity_rank": family_simplicity_rank.get(comp_family, 99),
        }
        table[cid] = metrics
        candidate_metrics.append(metrics)

    if not candidate_metrics:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_evaluated_metrics",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_evaluated_metrics",
            "table": table,
        }

    # 5. Filter for permitted winner families (legacy_tradex_scorer is comparator only)
    winner_eligible_metrics = [m for m in candidate_metrics if m["winner_eligible"]]
    if not winner_eligible_metrics:
        return {
            "winner_comparator_id": None,
            "winner_family": None,
            "status": "inconclusive_no_permitted_winner",
            "selection_status": "inconclusive",
            "selection_reason": "inconclusive_no_permitted_winner",
            "table": table,
        }

    # Locked tie-breaking order among eligible winner families:
    # 1. Higher top-decile lift
    # 2. Higher top-quartile lift
    # 3. Simpler family (lower simplicity rank)
    # 4. Shorter lookback (lower lookback integer)
    winner_eligible_metrics.sort(
        key=lambda m: (
            -m["top_10_lift"],
            -m["top_25_lift"],
            m["simplicity_rank"],
            m["lookback"],
        )
    )

    winner = winner_eligible_metrics[0]
    return {
        "winner_comparator_id": winner["comparator_id"],
        "winner_family": winner["comparator_family"],
        "status": "winner_selected",
        "selection_status": "winner_selected",
        "selection_reason": f"Selected {winner['comparator_id']} with top-10 lift {winner['top_10_lift']:.2f}x",
        "common_observations_count": common_total,
        "universe_base_rate": round(base_rate, 6),
        "winner_top_10_lift": winner["top_10_lift"],
        "winner_top_25_lift": winner["top_25_lift"],
        "comparators_evaluated": len(candidate_metrics),
        "selection_ranking": [m["comparator_id"] for m in winner_eligible_metrics],
        "table": table,
    }
