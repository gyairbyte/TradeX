"""Vectorized technical and market-context feature computation for LONG-002D1."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_wilder_atr14_series(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Calculate Wilder's ATR series over split-normalized bars.

    Returns an array of length N where values prior to index `period` are NaN.
    Index `period` is the arithmetic mean of TR_1 through TR_period.
    Subsequent bars use Wilder's exponential smoothing:
    ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period.
    """
    n = len(closes)
    atrs = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return atrs

    tr_list = np.full(n, np.nan, dtype=float)
    for i in range(1, n):
        h = float(highs[i])
        l = float(lows[i])
        prev_c = float(closes[i - 1])
        if np.isnan(h) or np.isnan(l) or np.isnan(prev_c):
            continue
        tr_list[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))

    # Bar 1 through period
    first_14_tr = tr_list[1 : period + 1]
    if np.any(np.isnan(first_14_tr)):
        return atrs

    curr_atr = float(np.sum(first_14_tr) / period)
    atrs[period] = curr_atr

    for j in range(period + 1, n):
        tr_j = tr_list[j]
        if np.isnan(tr_j):
            curr_atr = np.nan
        elif not np.isnan(curr_atr):
            curr_atr = (curr_atr * (period - 1) + tr_j) / period
        atrs[j] = curr_atr

    return atrs


def compute_features_for_security_df(
    df_bars: pd.DataFrame,
    spy_closes: dict[str, float] | pd.Series | None = None,
) -> pd.DataFrame:
    """Compute R1-R4 and F1-F11 for a single security's historical daily bars.

    Parameters:
        df_bars: DataFrame sorted chronologically by date index (or containing 'date'),
                 with columns: ['open', 'high', 'low', 'close', 'volume', 'as_traded_close'].
                 'close', 'high', 'low', 'open' must be split-normalized analytical prices.
                 'as_traded_close' must be unadjusted as-traded close.
        spy_closes: mapping or Series of date -> SPY split-normalized close.

    Returns:
        DataFrame indexed by date string ('YYYY-MM-DD') with columns:
        ['return_5', 'return_20', 'return_60', 'atr_pct_14',
         'close_vs_sma20', 'close_vs_sma60', 'sma20_slope_5',
         'proximity_high20', 'proximity_high60', 'true_range_compression_5_20',
         'relative_volume_20', 'dollar_volume_trend_20_60', 'up_volume_share_20',
         'spy_return_20', 'stock_minus_spy_20']
    """
    df = df_bars.copy()
    if "date" in df.columns and df.index.name != "date":
        df = df.set_index("date")
    df = df.sort_index()

    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    ac = (
        df["as_traded_close"].to_numpy(dtype=float)
        if "as_traded_close" in df.columns
        else c
    )

    n = len(df)
    dates = [str(d) for d in df.index]

    c_s = pd.Series(c, index=dates)
    v_s = pd.Series(v, index=dates)
    ac_s = pd.Series(ac, index=dates)

    # 1. Reference Features R1-R3: Returns over 5, 20, 60 sessions
    # close_t / close_{t-k} - 1
    r1 = (c_s / c_s.shift(5) - 1.0).to_numpy(copy=True)
    r2 = (c_s / c_s.shift(20) - 1.0).to_numpy(copy=True)
    r3 = (c_s / c_s.shift(60) - 1.0).to_numpy(copy=True)

    # Invalidate negative or zero past prices
    for arr, lb in [(r1, 5), (r2, 20), (r3, 60)]:
        if n >= lb:
            past_c = c_s.shift(lb).to_numpy(copy=True)
            invalid_mask = np.isnan(past_c) | (past_c <= 0)
            arr[invalid_mask] = np.nan

    # 2. Reference Feature R4: Wilder ATR14%
    # Wilder_ATR14_t / close_t
    atr14_arr = compute_wilder_atr14_series(h, l, c, period=14)
    valid_c_mask = ~np.isnan(c) & (c > 0)
    safe_c = np.where(valid_c_mask, c, np.nan)
    r4 = atr14_arr / safe_c

    # 3. Core Candidate F1: close_vs_sma20 = close_t / SMA20_t - 1
    sma20_s = c_s.rolling(20, min_periods=20).mean()
    sma20 = sma20_s.to_numpy()
    valid_sma20 = ~np.isnan(sma20) & (sma20 > 0)
    safe_sma20 = np.where(valid_sma20, sma20, np.nan)
    f1 = c / safe_sma20 - 1.0

    # 4. Core Candidate F2: close_vs_sma60 = close_t / SMA60_t - 1
    sma60_s = c_s.rolling(60, min_periods=60).mean()
    sma60 = sma60_s.to_numpy()
    valid_sma60 = ~np.isnan(sma60) & (sma60 > 0)
    safe_sma60 = np.where(valid_sma60, sma60, np.nan)
    f2 = c / safe_sma60 - 1.0

    # 5. Core Candidate F3: sma20_slope_5 = SMA20_t / SMA20_{t-5} - 1
    sma20_past5 = sma20_s.shift(5).to_numpy()
    valid_slope_denom = ~np.isnan(sma20_past5) & (sma20_past5 > 0)
    safe_sma20_past5 = np.where(valid_slope_denom, sma20_past5, np.nan)
    f3 = sma20 / safe_sma20_past5 - 1.0

    # 6. Core Candidate F4: proximity_high20 = close_t / rolling_max_close_20_t - 1
    rmax20_s = c_s.rolling(20, min_periods=20).max()
    rmax20 = rmax20_s.to_numpy()
    valid_rmax20 = ~np.isnan(rmax20) & (rmax20 > 0)
    safe_rmax20 = np.where(valid_rmax20, rmax20, np.nan)
    f4 = c / safe_rmax20 - 1.0

    # 7. Core Candidate F5: proximity_high60 = close_t / rolling_max_close_60_t - 1
    rmax60_s = c_s.rolling(60, min_periods=60).max()
    rmax60 = rmax60_s.to_numpy()
    valid_rmax60 = ~np.isnan(rmax60) & (rmax60 > 0)
    safe_rmax60 = np.where(valid_rmax60, rmax60, np.nan)
    f5 = c / safe_rmax60 - 1.0

    # 8. Core Candidate F6: true_range_compression_5_20
    # median(TR over latest 5) / median(TR over latest 20)
    tr_arr = np.full(n, np.nan, dtype=float)
    for i in range(1, n):
        h_i = h[i]
        l_i = l[i]
        prev_c_i = c[i - 1]
        if not np.isnan(h_i) and not np.isnan(l_i) and not np.isnan(prev_c_i):
            tr_arr[i] = max(h_i - l_i, abs(h_i - prev_c_i), abs(l_i - prev_c_i))
    tr_s = pd.Series(tr_arr, index=dates)

    med_tr5_s = tr_s.rolling(5, min_periods=5).median()
    med_tr20_s = tr_s.rolling(20, min_periods=20).median()
    med_tr20 = med_tr20_s.to_numpy()
    valid_tr20 = ~np.isnan(med_tr20) & (med_tr20 > 0)
    safe_tr20 = np.where(valid_tr20, med_tr20, np.nan)
    f6 = med_tr5_s.to_numpy() / safe_tr20

    # 9. Core Candidate F7: relative_volume_20
    # volume_t / median(volume over PRIOR 20 completed sessions, excluding t)
    # Excludes t: v_s.shift(1).rolling(20, min_periods=20).median()
    med_prior_v20_s = v_s.shift(1).rolling(20, min_periods=20).median()
    med_prior_v20 = med_prior_v20_s.to_numpy()
    valid_prior_v = ~np.isnan(med_prior_v20) & (med_prior_v20 > 0)
    safe_prior_v = np.where(valid_prior_v, med_prior_v20, np.nan)
    f7 = v / safe_prior_v

    # 10. Core Candidate F8: dollar_volume_trend_20_60
    # median(as_traded_close * volume over latest 20) / median(as_traded_close * volume over latest 60) - 1
    dvol_s = ac_s * v_s
    med_dvol20_s = dvol_s.rolling(20, min_periods=20).median()
    med_dvol60_s = dvol_s.rolling(60, min_periods=60).median()
    med_dvol60 = med_dvol60_s.to_numpy()
    valid_dvol60 = ~np.isnan(med_dvol60) & (med_dvol60 > 0)
    safe_dvol60 = np.where(valid_dvol60, med_dvol60, np.nan)
    f8 = med_dvol20_s.to_numpy() / safe_dvol60 - 1.0

    # 11. Core Candidate F9: up_volume_share_20
    # sum(volume for sessions in latest 20 where close_t > close_{t-1}) / sum(volume over latest 20)
    prev_c_s = c_s.shift(1)
    is_up_session = (c_s > prev_c_s) & prev_c_s.notna() & (prev_c_s > 0)
    up_vol_s = pd.Series(np.where(is_up_session, v, 0.0), index=dates)
    sum_up_vol20_s = up_vol_s.rolling(20, min_periods=20).sum()
    sum_tot_vol20_s = v_s.rolling(20, min_periods=20).sum()
    sum_tot_vol20 = sum_tot_vol20_s.to_numpy()
    valid_tot_v20 = ~np.isnan(sum_tot_vol20) & (sum_tot_vol20 > 0)
    safe_tot_v20 = np.where(valid_tot_v20, sum_tot_vol20, np.nan)
    f9 = sum_up_vol20_s.to_numpy() / safe_tot_v20

    # 12. Market Context F10: spy_return_20
    # SPY close_t / SPY close_{t-20} - 1
    f10 = np.full(n, np.nan, dtype=float)
    if spy_closes is not None:
        if isinstance(spy_closes, pd.Series):
            spy_c_s = spy_closes.sort_index()
        else:
            spy_c_s = pd.Series(spy_closes).sort_index()
        spy_r20_s = spy_c_s / spy_c_s.shift(20) - 1.0
        # Invalidate negative past SPY close
        past_spy = spy_c_s.shift(20)
        spy_r20_s[past_spy.isna() | (past_spy <= 0)] = np.nan
        spy_aligned = pd.Series(dates, index=dates).map(spy_r20_s)
        f10 = spy_aligned.to_numpy(dtype=float)

    # 13. Redundancy Diagnostic F11: stock_minus_spy_20
    # return_20 - spy_return_20
    f11 = r2 - f10

    # Invalidate where either is NaN
    nan_mask = np.isnan(r2) | np.isnan(f10)
    f11[nan_mask] = np.nan

    out_df = pd.DataFrame(
        {
            "return_5": r1,
            "return_20": r2,
            "return_60": r3,
            "atr_pct_14": r4,
            "close_vs_sma20": f1,
            "close_vs_sma60": f2,
            "sma20_slope_5": f3,
            "proximity_high20": f4,
            "proximity_high60": f5,
            "true_range_compression_5_20": f6,
            "relative_volume_20": f7,
            "dollar_volume_trend_20_60": f8,
            "up_volume_share_20": f9,
            "spy_return_20": f10,
            "stock_minus_spy_20": f11,
        },
        index=dates,
    )

    return out_df
