# TradeX Trading Feature Review

This review evaluates each major feature from a stock-trading perspective: what question it tries to answer, whether the implementation answers it, what it is missing, and what should be done with it.

---

## 1. Intraday trading

### What it tries to answer
"Which stocks are setting up for a significant same-day or next-day swing, preceded by volume/volatility accumulation?"

### How it works
- Data: 5-minute bars over the last 5 trading days (`fetcher.TIMEFRAMES["intraday"]`).
- Indicators: RSI(14), MACD, EMA20/50, Bollinger Bands, ATR, 20-bar volume SMA.
- Signals (from `tradex/signals/intraday.py`):
  - Volume ratio ≥ 2.0 (full) or ≥ 1.5 (half)
  - BB width in the top 20% of its recent range
  - RSI between 55 and 75 (or 25–45 oversold-bounce half credit)
  - MACD histogram crossing from negative to positive
- Output: a 0–100 score and a list of reasons.

### Assessment
The current intraday score is **a collection of common bullish indicators**, not a coherent intraday setup. It conflates several different ideas:

- A "volume surge" on a 5-minute bar is meaningless without reference to the *time of day*; 9:35am volume is expected to be high, 2:00pm volume is not.
- BB width rank over a 5-day 5m window is sensitive to the exact lookback and does not distinguish between a genuine squeeze and normal overnight gaps.
- RSI 55–75 is a momentum zone, but it ignores whether the stock has already moved 3% in the last 15 minutes (chasing) or is pulling back into support.
- A MACD crossover on 5m bars can fire dozens of times per day in noisy stocks.

### Critical missing elements
- VWAP / anchored VWAP
- Relative volume by time of day
- Premarket volume and opening-range behavior
- Liquidity, bid-ask spread, average daily volume, float
- ATR-based position sizing and stop placement
- Market/sector context (SPY, QQQ, sector ETFs)
- Time of day and extended-hours vs. regular-hours handling
- Incomplete current-candle handling

### Verdict
**Promising concept, requires redesign.** The indicators are reasonable inputs, but they need to be assembled into a specific, testable setup (e.g., "open-drive above VWAP on relative volume, first pullback to VWAP in a strong market"). The current score is too generic to be actionable.

---

## 2. Short-term trading (days to weeks)

### What it tries to answer
"Which stocks have momentum/trend confirmation on the daily timeframe and are pulling back to a support level?"

### How it works
- Data: daily bars over the last 60 trading days.
- Signals (from `tradex/signals/short_term.py`):
  - Price > EMA20 > EMA50
  - Volume ratio ≥ 1.3
  - RSI 50–70
  - MACD positive and expanding
  - Price within 1.5% of EMA20 while EMA20 > EMA50

### Assessment
This is the most defensible of the three timeframes because the inputs are standard swing-trading concepts. However, it still has major gaps:

- **No market regime filter.** Buying pullbacks in a strong bull market is different from buying them in a choppy or bear market.
- **No relative strength.** A stock can look technically healthy while underperforming SPY or its sector.
- **No entry/exit rules.** The score says "pullback to EMA20 in uptrend" but not how to enter, where the stop is, or what the target is.
- **No earnings or news proximity** beyond the simple calendar filter.
- **Volume ratio is on the current daily bar**, which at 10:00am is not comparable to a full-session average.
- **60-day window** is reasonable for a swing setup but short for assessing trend quality.

### Verdict
**Keep but improve.** Before raising the score threshold or adding indicators, define the exact setup to validate: e.g., "buy the first pullback to the rising 20-day EMA after a breakout on above-average volume, with the 50-day EMA rising, in an uptrending market." Then backtest with explicit stops and targets.

---

## 3. Long-term trading (weeks to months)

### What it tries to answer
"Which stocks are in a healthy secular uptrend with accumulation and consolidation?"

### How it works
- Data: weekly bars over the last 2 years.
- Signals (from `tradex/signals/long_term.py`):
  - Price above EMA50
  - RSI 40–65
  - 8-period average volume ratio ≥ 1.15
  - MACD above signal
  - BB width in bottom 25% of recent range

### Assessment
The implementation is essentially a **slower version of the short-term scorer** using weekly bars. It does not incorporate:

- Sector rotation or relative performance
- Drawdown / risk-of-ruin context
- Earnings growth, valuation, or fundamental trend
- Market regime (bull/bear/sideways)
- Position sizing or holding-period assumptions

A "long-term" screen that ignores whether the broader market is in an uptrend and whether the sector is leading is not reliable. The 8-week volume average is also too short to call "accumulation."

### Verdict
**Redesign or deprioritize.** If long-term is retained, it should either become a pure trend-following screen (price > 40-week MA, relative strength vs. SPY, sector strength) or explicitly incorporate limited fundamental data. Do not present it as a strategy until validated.

---

## 4. Cross-timeframe features

### 4.1 Multi-timeframe confluence (`tracker/confluence.py`)

**Concept:** A stock scoring well on intraday, short, and long timeframes simultaneously is higher conviction than one scoring well on only one.

**Current implementation issues:**
- Weights are renormalized when a timeframe is missing, so a single available timeframe can produce the full confluence score.
- The tier label "all timeframes aligned" can fire when only one timeframe is present and scores ≥ 50.
- Empty results cause a `KeyError` (`pd.DataFrame([]).sort_values("confluence_score")`) — a confirmed crash.
- There is no handling for conflicting timeframes (e.g., intraday bullish but short-term bearish).
- The weights (0.30 / 0.40 / 0.30) are not validated or user-tunable.

**Verdict:** **Keep but redesign.** Confluence is a useful *idea*, but the current formula is misleading and can produce "high conviction" results from a single timeframe.

### 4.2 Coil detector (`tracker/analyzer.py`)

**Concept:** A stock that appears in scans multiple times without a large price move is "coiling" and may be about to break out.

**Current implementation issues:**
- `store.record_signals` only stores rows that pass `min_score`, so a deteriorating setup is never observed.
- `appearances` is a count of `signal_history` rows, not distinct trading sessions. Three scans in one day count as three appearances.
- `coil_strength` includes `appearances * 5`, so more frequent scanning mechanically raises coil strength.
- The 3% breakout threshold is arbitrary and does not account for ATR or normal volatility.
- The score-trend slope uses raw scan sequence indices, not time, so irregular scan intervals bias the slope.

**Verdict:** **Redesign.** The concept is valuable, but the current metric is a function of scan frequency, not market behavior.

### 4.3 Historical pattern matching (`patterns/*`)

**Concept:** If a stock's recent 10-day price/volume shape looks like the average shape that preceded past run-ups, it may be setting up for a similar move.

**Current implementation issues:**
- **Survivorship bias:** the mining universe is a static list of ~40 liquid names that have generally done well.
- **Small sample sizes:** with thresholds of 15%/12% over 5 trading days, many stocks produce few events per profile.
- **Pearson correlation of shape does not imply predictive value.** A stock can trace the same pre-move shape and then do nothing.
- **Look-ahead bias risk:** the miner uses "close at t+move_days" to label an event at time `t`. This is fine for *training*, but the matcher must only use information available at `t`.
- **Fingerprint uses `short` (daily) bars** regardless of context.

**Verdict:** **Keep for experimentation only.** Do not treat pattern similarity as a trade signal without out-of-sample backtesting.

### 4.4 Pre-market gap scanner (`premarket/gap_scanner.py`)

**Concept:** Identify stocks that have gapped significantly from the previous close before the market opens.

**Current implementation issues:**
- Uses yfinance 1-minute pre/post bars, which are delayed and can be sparse.
- Filters to bars before 13:00 UTC, a rough approximation of 9:00am ET that does not account for daylight saving or exchange pre-market hours.
- No liquidity, spread, or premarket volume filter.
- No news/earnings context; a gap on no catalyst is very different from one on earnings.
- No gap-fill vs. continuation logic beyond a static note.

**Verdict:** **Useful only as supporting context.** A gap is a starting point, not a trade. Keep the feature, but add liquidity and catalyst context and do not alert on gaps alone.

### 4.5 Options flow (`options/flow.py`)

**Concept:** Unusual options volume/activity may reveal informed positioning before a price move.

**Current implementation issues:**
- Without Unusual Whales or Tradier credentials, it falls back to free yfinance option-chain data. That is **not flow data**; it is end-of-day or delayed chain volume/OI.
- The put/call ratio is computed across the entire nearest expiry chain, mixing hedging, spreads, and directional trades.
- No sweep detection, multi-leg trade handling, or opening vs. closing activity distinction.
- Interpreting vol/OI ratio as a signal without context is risky.

**Verdict:** **Deprioritize / quarantine until validated.** In its current free-yfinance form it is more likely to mislead than help.

### 4.6 Earnings awareness (`earnings/calendar.py`)

**Concept:** Avoid setups that resolve into an earnings binary event.

**Current implementation:**
- Fetches next earnings date from yfinance and caches it for 24h.
- Returns days until earnings as calendar days from `date.today()`.
- Screener can exclude tickers with earnings within `N` days.

**Issues:**
- Does not handle rescheduled dates, ETFs, or missing dates well.
- Calendar-day vs. trading-day window is not clearly distinguished.
- Cache TTL is fixed; a user has to manually delete the cache if a date is updated.

**Verdict:** **Keep but improve.** This is a genuinely useful risk filter. Add forced refresh, better error messages, and document that it is calendar-day based.

### 4.7 Signal journal and outcome tracking (`tracker/outcome_tracker.py`)

**Concept:** Record what happened after every signal and use it to calibrate thresholds.

**Current implementation issues:**
- Outcome window is measured in daily closes for all timeframes, so a "long-term" signal is only tracked for 5 trading days, not weeks.
- The function waits too long before fetching (`end = after_date + days_forward + 7`), so outcomes are resolved days after the intended window closes.
- It crashes on yfinance MultiIndex columns.
- No slippage, stop-loss, or transaction-cost modeling.
- Win-rate calculation treats any positive return as a win, regardless of whether it was achievable after costs or within the user's holding period.

**Verdict:** **Highest-value feature once fixed.** This is the only feature that can turn TradeX from a screen into a validated strategy tool.

---

## 5. Feature-value matrix

| Feature | Intended purpose | Current value | Major problem | Unique information? | Recommendation |
|---|---|---|---|---|---|
| **Intraday score** | Find same-day / next-day swing setups | Moderate screen, not a strategy | Generic indicator bundle; no VWAP, time-of-day, liquidity | No | Redesign into a specific, testable setup |
| **Short-term score** | Find swing setups on daily bars | Moderate; most defensible timeframe | No market regime, relative strength, or entry/exit rules | No | Keep and validate with explicit setup |
| **Long-term score** | Find multi-week / multi-month trends | Low | Slower version of short-term; no fundamentals/relative strength | No | Redesign or deprioritize |
| **Confluence** | Higher conviction when multiple timeframes agree | Low due to misleading missing-timeframe behavior | Renormalization + empty-result crash | Yes, if fixed | Redesign; require all requested timeframes |
| **Coil detector** | Surface pre-breakout pressure | Low due to scan-frequency bias | Counts scans, not sessions; no deterioration visibility | Yes, conceptually | Redesign signal-history model first |
| **Pattern match** | Match current pattern to historical pre-move shapes | Low without validation | Survivorship bias; correlation ≠ prediction; small sample | No, unless validated | Quarantine as experiment |
| **Pre-market gap** | Catch overnight catalysts before open | Supporting context only | Delayed/sparse data; no liquidity/catalyst context | Some, if paired with news | Keep as context; do not alert alone |
| **Options flow** | Detect unusual directional activity | Misleading without paid data | Free yfinance chain is not flow; no sweep/spread context | Yes, if real data source used | Deprioritize / quarantine |
| **Earnings filter** | Avoid earnings binary events | Useful | Cache/refresh and date edge cases | Yes | Keep and improve |
| **Signal journal** | Calibrate signal quality | High potential, currently broken | MultiIndex crash, wrong horizon, no costs | Yes, if fixed | Fix and make central |
| **Outcome tracking** | Measure post-signal returns | High potential, currently broken | Waits too long; daily bars for all timeframes; no slippage | Yes, if fixed | Fix as priority |
| **Alerts** | Notify on threshold crosses | Low without dedup | No cooldown or persistence; can spam | No, in current form | Add alert state and cooldown |
| **Watchlists** | Persist and refresh ticker universes | Useful | None major | Yes | Keep |
| **Scoring weights** | Let users tune signal contributions | Useful for experimentation | No validation framework; easy to overfit | Yes | Keep; require backtest for changes |
