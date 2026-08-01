# TradeX Validation Plan

The goal of validation is to determine which TradeX features actually provide a tradable edge, and under what conditions. Validation must be separated from implementation: a feature can be coded correctly and still be unprofitable or misleading.

## Core principle

No feature should be treated as a trading signal until it has been tested with:

1. A **specific, written hypothesis**.
2. **Point-in-time data** (no lookahead).
3. A **realistic universe** with survivorship-bias controls.
4. Explicit **entry, stop, and target rules**.
5. **Transaction costs and slippage**.
6. A **benchmark** (e.g., SPY buy-and-hold, equal-weight sector index).
7. A **train/validation/test split** or walk-forward methodology.
8. Enough **samples** to draw a conclusion.

## General methodology

### 1. Data

- **Primary source:** Use the intended production provider (Yahoo for back-of-the-envelope, Alpaca/Schwab/polygon for cleaner data).
- **Period:** Use at least 5–10 years of data, covering bull, bear, and sideways regimes.
- **Universe:** Use point-in-time constituents. Do not use current S&P 500 membership for historical tests.
- **Survivorship bias:** Use delisted-ticker data where possible, or at minimum acknowledge and bound the bias.
- **Lookahead controls:** Any label, regime, or sector classification must use only information known at the signal date.

### 2. Train / validation / test split

| Period | Purpose | Typical length |
|---|---|---|
| Train (in-sample) | Discover/optimize signal parameters | 5–7 years |
| Validation | Tune hyperparameters and thresholds | 1–2 years |
| Test (out-of-sample) | Measure final performance | 1–3 years |

Use **walk-forward testing** where the model is retrained on a rolling window and evaluated on the subsequent period. This better simulates live use than a single static split.

### 3. Execution model

- **Entry:** Use the close of the signal bar or the next bar open, depending on the strategy. Document which is used.
- **Stop:** Use ATR-based or fixed-percentage stops that are consistent with the timeframe.
- **Target:** Use a fixed target, trailing stop, or time-based exit.
- **Holding period:** Match the timeframe (1 day for intraday, 3–10 days for short, weeks/months for long).
- **Costs:** Include $0.005–$0.01 per share slippage and $0.005 per share commission (adjust for account size).
- **Position sizing:** Equal-weight or volatility-targeted; avoid concentration in one sector.

### 4. Metrics

- **Win rate** (gross and net of costs)
- **Expectancy** per trade
- **Profit factor**
- **Sharpe ratio** (annualized, using daily returns)
- **Maximum drawdown**
- **Average trade return and distribution**
- **Score-bucket analysis** (e.g., does the 80–100 bucket outperform the 40–59 bucket?)
- **Benchmark excess return**
- **Statistical significance** (t-statistic, confidence intervals)

---

## Per-feature validation plans

### A. Intraday score

**Hypothesis:** A stock with volume surge, MACD crossover, RSI 55–75, and BB expansion on 5m bars tends to move in the direction of the signal within the next 1–4 hours.

**Data needed:** 1-minute or 5-minute historical bars for a liquid universe, at least 2 years.

**Entry/exit:**
- Entry: next 5m bar open after signal bar.
- Stop: 1× ATR or 0.5%.
- Target: 2× risk or 4-hour time stop.

**Controls:**
- Time-of-day segmentation (pre-market, open, midday, close).
- Sector and market regime (SPY trend above/below VWAP).
- Liquidity filter (avg daily volume > 1M, spread < 0.1%).

**Acceptance:**
- Net expectancy > $0.02 per share after costs.
- Win rate > 45% with positive expectancy.
- Statistically significant across at least 200 trades.

**What would justify removal:** If 80+ score bucket has negative expectancy or underperforms a simple "buy first 5m breakout on volume" baseline.

---

### B. Short-term (swing) score

**Hypothesis:** A stock in a healthy uptrend (price > EMA20 > EMA50) with confirming volume and RSI 50–70 that pulls back to EMA20 tends to resume the uptrend over the next 3–10 trading days.

**Data needed:** Daily OHLCV for a broad, point-in-time US equity universe, 10+ years.

**Entry/exit:**
- Entry: next-day open after signal.
- Stop: 1.5× ATR below entry or close below EMA50.
- Target: 3× risk or 10-day time stop.

**Controls:**
- Market regime (SPY above/below 200-day MA).
- Sector relative strength.
- Earnings proximity.

**Acceptance:**
- Net CAGR > SPY + 3% with lower max drawdown, or positive alpha in regressions.
- Score buckets are monotonic (higher score → higher return).

**What would justify removal:** If the score adds no predictive power beyond a simple EMA20/EMA50 trend filter.

---

### C. Long-term score

**Hypothesis:** Weekly price above EMA50 with MACD above signal and healthy RSI identifies multi-week uptrends with favorable risk/reward.

**Data needed:** Weekly OHLCV, 10+ years, broad universe.

**Entry/exit:**
- Entry: next weekly open.
- Stop: 2× weekly ATR or weekly close below EMA50.
- Target: trailing stop or 12-week time stop.

**Controls:**
- Market regime.
- Sector leadership.
- Fundamental trend (optional: earnings estimate revision).

**Acceptance:**
- Positive net expectancy over full market cycles.
- Avoids large drawdowns in bear regimes.

**What would justify removal:** If the signal is indistinguishable from a simple price-above-40-week-MA rule.

---

### D. Multi-timeframe confluence

**Hypothesis:** A stock scoring well on intraday, short, and long timeframes simultaneously has a higher probability of a favorable move than one scoring well on any single timeframe.

**Data needed:** Same as individual timeframes.

**Method:**
- Build confluence score using *only* days where all three timeframes are available.
- Compare the confluence score distribution to each individual timeframe score.
- Run trades on "high confluence" setups using the short-term execution model.

**Acceptance:**
- High-confluence bucket has significantly higher win rate and expectancy than the best single-timeframe bucket.
- Missing-timeframe cases are not labeled as high confluence.

**What would justify redesign:** If confluence does not outperform the best single timeframe after costs, the weighting and missing-data handling need to change.

---

### E. Coil detector

**Hypothesis:** A stock that appears in scans on multiple distinct trading days without a large price move, and whose score is stable or rising, is more likely to break out in the next 1–5 days.

**Data needed:** Signal history produced by the redesigned store (all observations, distinct session IDs).

**Method:**
- Define a "coil episode" as a sequence of distinct trading sessions.
- Define the trigger event (e.g., 3rd session with score ≥ 50 and price change < 3% from first session).
- Measure forward returns from the close of the trigger session.

**Controls:**
- Do not count scan frequency.
- Compare to a baseline of "any passing signal" to isolate the value of repeated appearances.

**Acceptance:**
- Coil-triggered trades have higher expectancy than a random passing signal.
- Results are robust to the breakout threshold (2%, 3%, 4%).

**What would justify removal:** If repeated scan appearances add no predictive power beyond the latest score.

---

### F. Historical pattern matching

**Hypothesis:** A stock whose recent price/volume/indicator shape is similar to the average pre-event shape of past run-ups is more likely to experience a similar run-up in the next 5 trading days.

**Data needed:** 10+ years daily data for a point-in-time universe; delisted tickers where possible.

**Method:**
- Mine pre-event windows exactly as implemented.
- Build fingerprints on the training period only.
- Evaluate out-of-sample: for every date in validation/test, compute similarity, and trade the top-N matches.
- Compare to a baseline that buys all stocks meeting the same raw event criteria.

**Controls:**
- Survivorship-bias-free mining.
- Regime and sector segmentation.
- Different lookback and event-threshold parameters.

**Acceptance:**
- Top-decile similarity stocks produce materially higher returns than bottom-decile.
- Results hold out-of-sample.

**What would justify removal:** If Pearson similarity to a fingerprint has no predictive power, the feature should not be shown as a signal.

---

### G. Pre-market gap scanner

**Hypothesis:** Large pre-market gaps on above-average premarket volume tend to continue in the direction of the gap during the first 30 minutes of regular trading.

**Data needed:** Pre-market 1-minute bars with volume, ideally from a real-time provider; 2+ years.

**Entry/exit:**
- Entry: 1 minute after open.
- Stop: 1× ATR or 1%.
- Target: 2× risk or 30-minute time stop.

**Controls:**
- Catalyst filter (earnings, news, analyst action).
- Liquidity and spread filter.
- Market direction at open.

**Acceptance:**
- Net positive expectancy after premarket spread/slippage costs.
- Works only in specific gap-size/liquidity buckets.

**What would justify removal:** If free yfinance data is too delayed/sparse to support actionable gaps.

---

### H. Options flow

**Hypothesis:** Unusual options volume/OI or sweep activity predicts near-term directional moves.

**Data needed:** Real options flow (Unusual Whales, Cboe, or similar), 1+ year.

**Method:**
- Define "unusual" thresholds on training data.
- Test predictive value for next 1–5 day stock returns.
- Control for stock liquidity and earnings proximity.

**Acceptance:**
- Top-decile flow events have statistically significant excess returns after costs.

**What would justify removal:** If only free yfinance chain data is available, the feature should be disabled or clearly labeled as "chain volume only, not flow."

---

## Minimum sample-size guidance

| Metric | Minimum sample |
|---|---|
| Win rate estimate | 100 trades |
| Expectancy estimate | 200+ trades |
| Score-bucket monotonicity | 50+ trades per bucket |
| Regime-specific results | 50+ trades per regime |
| Pattern-match fingerprint | 30+ events per fingerprint |

If a strategy produces fewer samples, report wide confidence intervals and do not make strong claims.

---

## Proposed validation backlog (in order)

1. **Fix correctness issues** so the signal journal can collect reliable data.
2. **Build a backtesting harness** with point-in-time data, costs, and a simple execution model.
3. **Validate the short-term score first** — it is the most defensible starting point.
4. **Validate coil detector** after the history redesign.
5. **Validate confluence** after individual timeframes are validated.
6. **Re-evaluate pattern match, pre-market gaps, and options flow** based on out-of-sample results.
