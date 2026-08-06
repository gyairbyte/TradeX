# INTRA-001: Long open-drive VWAP pullback continuation

This file is the human-readable research specification for `INTRA-001`. The canonical, machine-readable locked specification is [`docs/research/specs/INTRA-001-v1.json`](./specs/INTRA-001-v1.json). Any future study artifacts must reference the SHA-256 and commit that first added this file.

**Status:** `pre_registered_not_executed`  
**Spec version:** `1`  
**JSON SHA-256:** `239274cc650b21e215c91085d2a89e671e05d504200ac6daa4b70be60b8c81ef`

This PR does **not** implement the setup, the intraday backtester, the data snapshotter, the production scorer, any dashboard change, or any trading integration. It locks exactly what a future study must do and the evidence it must produce.

---

## 1. Status and authority

`INTRA-001` is a **research-only** pre-registration. No production signal, score, weight, threshold, rank, eligibility rule, alert, or default is changed by this specification. Production promotion requires a separate Gary-approved production PR after `INTRA-001D` and only if every validation and holdout gate defined below passes unchanged.

This specification is the source of truth for the future implementation of:

- `INTRA-001B` — intraday data and manifest infrastructure (begins after the approved `SHORT-001` Schwab real-data study is completed)
- `INTRA-001C` — research detector and execution engine
- `INTRA-001D` — locked real-data study

---

## 2. Objective

Pre-register one concrete, falsifiable intraday setup:

> Among sufficiently liquid U.S.-listed equities and ETFs exhibiting a confirmed bullish opening drive, a first regular-session pullback to and reclaim of session VWAP between 10:00 AM and 11:30 AM Eastern produces superior net expectancy and comparable or better drawdown than both the existing production intraday score and a simple VWAP-reclaim baseline.

The study is:

- Long-only
- U.S. regular-session only
- Five-minute bars
- One candidate trade per ticker per session
- Research-only

Short setups are out of scope for this version.

---

## 3. Current production intraday behavior

`tradex/signals/intraday.py` produces a 0–100 additive indicator score from four weighted components (`tradex/signals/weights.py::IntradayWeights` defaults):

| Component | Default weight | Firing condition |
|---|---|---|
| Volume surge | 30 | current-bar volume \>= 2× 20-bar average; half weight at \>= 1.5× |
| Bollinger Band expansion | 20 | `bb_width` rank percentile \> 0.8 |
| RSI momentum | 20 | RSI in 55–75 (or 25–45 for oversold bounce, at 0.75× weight) |
| MACD crossover | 30 | `macd_diff` crosses above zero |

The scorer returns `score`, `reasons`, `last_close`, `volume_ratio`, and `rsi`. It does **not** compute session VWAP, opening-drive state, time-of-day eligibility, pullback/reclaim sequences, entry timing, stop placement, profit target, same-bar execution policy, end-of-day liquidation, or intraday liquidity filters.

`tradex/screener/engine.py` maps `"intraday"` to `intraday.score` and passes no context or execution parameters. No dashboard control, watcher, alert, confluence, or ranking path applies an open-drive VWAP policy.

---

## 4. Current data and backtest limitations

- `tradex/data/fetcher.py` defines `TIMEFRAMES["intraday"]` as `{"period": "5d", "interval": "5m"}`. The named intraday preset therefore retrieves five trading days of five-minute bars.
- `tradex/data/history.py` provides explicit date-ranged history only for **daily** bars (`interval="1d"`). Alpaca and IBKR are explicitly not supported for date-ranged daily history and raise `ProviderCapabilityError`.
- `tradex/backtest/engine.py` is a point-in-time, daily-bar backtester. Its `BacktestConfig` operates on generic bars and records `signal_time`, next-open entry, stop/target/time exits, and `max_holding_bars`. The engine does not model session VWAP, intraday time-of-day windows, regular-session bar availability, or five-minute execution semantics.

Therefore `INTRA-001` cannot responsibly begin as a direct rewrite of `tradex/signals/intraday.py`. The data contract, execution model, and study methodology must be locked first.

---

## 5. Locked candidate setup

### 5.1 Session

| Field | Value |
|---|---|
| Exchange calendar | `XNYS` |
| Timezone | `America/New_York` |
| Bar interval | Five minutes |
| Regular session | 9:30 AM – 4:00 PM Eastern |
| Early-close sessions | Excluded from the primary study |
| Pre-market / after-hours bars | Excluded |
| Session VWAP | Resets at the beginning of every regular session |
| Decision rule | Use only completed bars |
| Timestamp convention | Provider timestamps must be documented as bar-start or bar-end; normalize to `bar_start` and `available_at`; a five-minute bar beginning at 10:00 AM is not available until 10:05 AM |

### 5.2 VWAP formula

```text
typical_price              = (high + low + close) / 3
cumulative_price_volume    = cumulative_sum(typical_price * volume)
cumulative_volume          = cumulative_sum(volume)
session_vwap               = cumulative_price_volume / cumulative_volume
```

Sessions with zero or invalid cumulative volume are rejected or explicitly flagged. End-of-day volume must not be used in an earlier calculation.

### 5.3 Liquidity eligibility

A ticker-session is eligible only when, using data known before that session:

- Prior regular-session close is at least `$5.00`.
- Prior 20 completed sessions’ median regular-session dollar volume is at least `$50,000,000`.
- At least 20 complete prior sessions exist for time-of-day volume baselines.
- The current session has valid, nonzero five-minute volume.
- The symbol is not OTC, a warrant, a right, a unit, or preferred stock.

The specification requires a documented security-type source to enforce these exclusions.

### 5.4 Opening-drive qualification

Evaluate after the first six completed five-minute bars, at 10:00 AM Eastern. The opening-drive state is computed from those six bars and is then frozen. It must not be recomputed using any bar after 10:00 AM. The ticker qualifies when all of the following are true:

- Return from the 9:30 AM session open to the 10:00 AM close is at least `+0.75%`.
- The 10:00 AM close is above session VWAP.
- Cumulative regular-session volume from 9:30 AM through 10:00 AM is at least `1.50×` the median volume over the same first six bars during the prior 20 complete sessions.
- No required bar from 9:30 AM through 10:00 AM is missing.
- All input bars pass OHLCV validation.

The frozen opening-drive qualification is referenced by the pullback/reclaim logic; it is never recomputed after 10:00 AM.

### 5.5 Pullback and VWAP reclaim

Search from the first completed bar after 10:00 AM through the bar completing at 11:30 AM Eastern. The first bar satisfying all of the following is the reclaim bar:

- Bar low \<= session VWAP calculated for that completed bar.
- Bar close strictly above that VWAP.
- Bar close \> bar open.
- Bar close remains at or above the 9:30 AM session open.
- The opening-drive qualification remains valid.
- No prior bar in the pullback window already satisfied the reclaim definition.

The signal becomes known only at the reclaim bar’s completion. The reclaim logic uses the frozen 10:00 AM opening-drive qualification; it must not recompute that qualification from post-10:00 AM bars.

### 5.6 Entry

- Enter at the next available five-minute bar’s open.
- Do not assume an entry on the reclaim bar.
- If the next bar is missing, do not execute a trade.
- If the next bar’s open is already at or below the predetermined stop, reject the trade as unexecutable.
- No more than one candidate trade may execute per ticker per session.
- No overlapping positions for the same ticker.

### 5.7 Stop

At signal time:

```text
stop_buffer = max(0.01, reclaim_close * 0.0005)
stop_price  = reclaim_low - stop_buffer
```

The stop must be strictly below the anticipated entry. The stop is fixed after entry.

### 5.8 Target

After the actual entry fill is known:

```text
risk_per_share = entry_fill - stop_price
target_price   = entry_fill + (1.5 * risk_per_share)
```

Trades with nonpositive or invalid risk are rejected.

### 5.9 Exit order

For every bar after entry:

1. Gap through stop at bar open: exit at the open.
2. Gap through target at bar open: exit at the open.
3. Intrabar stop or target touch.
4. If stop and target are both touched in one bar, use `stop_first`.
5. Time exit at the close of the bar ending at 3:45 PM Eastern.
6. If the expected time-exit bar is missing, exit at the last valid regular-session close before the exchange close.
7. Never hold overnight.

### 5.10 Costs

Primary evaluation:

| Cost | Value |
|---|---|
| Entry slippage | 5 bps |
| Exit slippage | 5 bps |
| Commission | 0 bps |

Required sensitivity scenarios (per side):

- 0 bps
- 2.5 bps
- 5 bps
- 10 bps

Slippage is adverse on both entry and exit.

---

## 6. Baselines

### 6.1 Baseline A — Current production intraday score

Use the current production `tradex.signals.intraday.score` with an explicit fresh `IntradayWeights()` instance and **no** `~/.tradex/weights.json`:

- Evaluate completed five-minute bars only.
- Restrict potential signals to 10:00 AM through 11:30 AM Eastern.
- The **signal bar** is the first completed five-minute bar in that window on which `intraday.score` reaches at least `40` for the ticker-session.
- Enter at the next five-minute bar open.
- Stop is derived from the signal bar, not a reclaim bar:
  ```text
  stop_buffer = max(0.01, signal_bar_close * 0.0005)
  stop_price  = signal_bar_low - stop_buffer
  ```
- Target is the same 1.5R formula as the candidate:
  ```text
  risk_per_share = entry_fill - stop_price
  target_price   = entry_fill + (1.5 * risk_per_share)
  ```
- Apply the same liquidity rules, costs, one-trade-per-session rule, and time-exit rules as the candidate.
- Skip the trade if the next bar is missing or its open is at or below the stop.

This baseline measures whether the concrete setup adds value beyond the existing generic score.

### 6.2 Baseline B — Simple VWAP reclaim

Use the same liquidity rules, pullback window, entry, stop, target, costs, one-trade-per-session rule, and exit rules as the candidate. The reclaim bar must satisfy the same price and VWAP conditions as the candidate:

- Bar low \<= session VWAP for that completed bar.
- Bar close strictly above that VWAP.
- Bar close \> bar open.
- Bar close remains at or above the 9:30 AM session open.
- No prior bar in the pullback window already satisfied the reclaim definition.

Baseline B does **not** require:

- The `+0.75%` opening-drive return.
- The `1.50×` opening-volume condition.
- Any ongoing opening-drive qualification check during the pullback window.

This baseline measures whether the opening-drive requirements add value beyond a generic VWAP reclaim.

---

## 7. Universe construction

### 7.1 ETF stratum

Fixed list of 13 ETFs:

`SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, SMH`

### 7.2 Stock stratum

At the beginning of each calendar month:

1. Identify U.S.-listed common stocks eligible under the security-type rules.
2. Use only information available before the first session of that month.
3. Rank by median regular-session dollar volume over the previous 20 complete sessions.
4. Include the top 50 qualifying stocks.
5. Require prior close of at least `$5.00`.
6. Preserve monthly point-in-time membership in a locked universe manifest.
7. Include symbols that later delist when the data source supports them.
8. Do not construct the historical universe from today’s index constituents.

If the available provider cannot support this universe contract, the real study is not promotion-eligible.

---

## 8. Date range and splits

| Split | Start | End |
|---|---|---|
| Dataset | `2022-01-03` | `2025-12-31` |
| Development | `2022-01-03` | `2023-06-30` |
| Validation | `2023-07-03` | `2024-06-28` |
| Holdout | `2024-07-01` | `2025-12-31` |

The splits are chronological and non-overlapping. The holdout must not be inspected during implementation or candidate debugging.

---

## 9. Sample minimums and data sufficiency

### 9.1 Sample minimums

Validation and holdout must each contain:

| Requirement | Minimum |
|---|---|
| Executed candidate trades | 300 |
| Represented stock symbols | 25 |
| Represented ETFs | 8 |
| Candidate trades in the stock stratum | 100 |
| Candidate trades in the ETF stratum | 75 |
| Paired-symbol overlap for gate 8 | >= 15 |
| Single ticker share of candidate trades | \<= 10% |
| Single ticker share of candidate net profit | \<= 20% |

A **represented symbol** has at least one executed candidate trade in the split. Symbols with zero trades do not count toward the represented-symbol minimums, toward paired-symbol overlap, or toward per-symbol aggregations.

Concentration rules use **per-symbol aggregated contributions**, not individual trades:
- Trade-count concentration = maximum per-symbol trade count / total candidate trades.
- Net-profit concentration (when total net R > 0) = maximum positive per-symbol total net R / total net R across the split. Losing symbols cannot be the numerator.
- Absolute-loss concentration (when total net R \<= 0) = maximum absolute negative per-symbol total net R / sum of absolute per-symbol total net R for losing symbols. Profitable symbols cannot be the numerator.

Failure to meet any sample minimum produces an `inconclusive` outcome.

### 9.2 Data-sufficiency thresholds

The data contract for a split must also satisfy:

| Quality check | Maximum allowed |
|---|---|
| Missing-bar rate per symbol | \<= 5% of expected regular-session bars |
| Zero-volume-bar rate per symbol | \<= 10% of expected regular-session bars |
| Duplicate-bar rate per symbol | \<= 1% of expected regular-session bars |
| Symbols rejected for data quality | \<= 5% of the monthly universe |

Exceeding these **data-sufficiency** thresholds (missing bars, zero-volume bars, duplicate bars, or too many symbols rejected for data quality) makes the split `inconclusive`.

**Provider or provenance violations** — silent provider substitution, missing manifest/provenance, material timestamp errors, manifest mismatch, or any other data-contract violation — make the split `invalid`, not `inconclusive`.

---

## 10. Validation gates

The candidate may proceed to holdout evaluation only when all of the following pass on validation. Expectancy, profit factor, and drawdown are computed under the locked `calculation_policy` in `INTRA-001-v1.json`.

1. Sample and data-sufficiency minimums are met.
2. Candidate pooled net expectancy (pooled mean net R multiple) at 5 bps per side is positive.
3. Candidate median per-symbol net expectancy (median of per-symbol mean net R) exceeds the current-score baseline by at least `0.05R`.
4. Candidate median per-symbol net expectancy exceeds the simple-VWAP baseline by at least `0.03R`.
5. Candidate median per-symbol profit factor is at least `1.05` (`no_loss_positive` ranks as `+∞` and passes; `no_profit` (0.0) fails; `no_trade` symbols excluded; median computable only when at least half of candidate-represented symbols have a computable per-symbol profit factor).
6. Candidate median per-symbol profit factor is not below either baseline (`no_loss_positive` beats any finite value; equal medians pass; `no_trade` symbols excluded).
7. At least `55%` of represented symbols have positive candidate mean net expectancy.
8. At least `55%` of paired symbols (with both candidate and current-score baseline trades) outperform the current-score baseline by mean net expectancy, and the paired-symbol overlap is at least `15`.
9. Candidate **median per-symbol maximum drawdown** is not worse than the current-score baseline by more than `2` percentage points.
10. Both stock and ETF strata have nonnegative pooled expectancy (pooled mean net R \>= 0).
11. Candidate pooled expectancy remains nonnegative at 10 bps per side.
12. Concentration limits are met.

Do not evaluate the holdout if validation fails.

---

## 11. Holdout gates

Evidence supports promotion consideration only if every validation gate also passes unchanged on the untouched holdout. In addition:

- No threshold, setup rule, universe rule, entry, stop, target, exit, or cost assumption may change after validation results are reviewed.
- The holdout may be run only once for this locked specification.
- A passing holdout does not authorize production integration.

---

## 12. Outcome definitions

| Outcome | Condition |
|---|---|
| **Supported for promotion consideration** | All sample/data-sufficiency rules are met and all validation and holdout gates pass. |
| **Not supported** | All sample and data-sufficiency rules are met, but one or more predefined performance gates fail. |
| **Inconclusive** | One or more sample minimums are not met; or data-sufficiency thresholds (missing-bar, zero-volume, duplicate-bar, or symbol-rejection rates) are exceeded; or the split does not contain at least one executed candidate trade in both the stock and ETF strata; or a required median per-symbol statistic cannot be computed because fewer than half of represented symbols have a computable value; or the profit-factor median is not computable because fewer than half of represented symbols have a computable per-symbol profit factor; or gate 8 paired-symbol overlap is below `15`. |
| **Invalid** | Holdout leakage, future-bar use, post-hoc threshold or rule changes, validation gates changed after viewing results, holdout evaluated before validation gates passed, silent provider substitution, missing required provenance or manifest, material timestamp errors, manifest or data-contract violation, unresolved split/corporate-action errors, or non-reproducible outputs. |

A result of `supported` is research-only and does not itself authorize production promotion.

---

## 12.5 Calculation and aggregation rules

All metrics use a **per-symbol research ledger** and a single fixed risk unit per trade. The same rules apply to the candidate, Baseline A, and Baseline B.

### Position sizing

- Each executed trade is sized to **one risk unit**.
- `risk_per_share = net_entry_price - stop_price`.
- `shares = 1 / risk_per_share`.
- No account compounding; each trade is evaluated against a notional 100-unit account where `1R = 1%`.
- Simultaneous trades across different symbols are allowed; each symbol has its own ledger and no cross-symbol capital allocation is modeled.

### Net price formulas

- `entry_fill = entry_open * (1 + entry_slippage_bps/10000 + entry_commission_bps/10000)`
- `exit_fill = exit_price * (1 - exit_slippage_bps/10000 - exit_commission_bps/10000)`
- Slippage and commission (if any) are adverse on both entry and exit.
- The primary cost scenario has `commission_bps = 0`, so the per-side cost is the adverse slippage only.

### Net R multiple and return

- `profit_per_trade = exit_fill - entry_fill`
- `risk_per_trade = entry_fill - stop_price`
- `net_R_multiple = profit_per_trade / risk_per_trade`
- `total_return_R = chronological cumulative sum of net_R_multiple` for a ledger.
- Because the account is 100 units and `1R = 1%`, `total_return_pct = total_return_R`.
- `equity_curve = 100 + total_return_R`.
- `running_peak = cumulative maximum of equity_curve`.
- `drawdown_series = 100 * (equity_curve - running_peak) / running_peak`.
- `maximum_drawdown_pct = minimum value of drawdown_series` (<= 0).

### Per-symbol and pooled aggregation

- A **represented symbol** has at least one executed trade in the split. Only represented symbols count toward `represented_stock_symbols_min` and `represented_etfs_min`.
- Symbols with zero trades are excluded from per-symbol statistics, from equal-weighted/median aggregations, and from represented-symbol sample-minimum counts.
- `pooled_expectancy` = mean `net_R_multiple` across all executed trades in the split.
- `median_per_symbol_expectancy` = median of per-symbol mean `net_R_multiple` across represented symbols.
- `equal_weighted_per_symbol_mean_expectancy` = mean of per-symbol mean `net_R_multiple` across represented symbols.
- `positive_symbol_rate` = fraction of represented symbols with mean `net_R_multiple` > 0.
- `outperform_baseline_symbol_rate` = fraction of paired symbols (with both candidate and baseline trades) whose candidate mean `net_R_multiple` exceeds the baseline mean.
- `median_per_symbol_total_return` = median of per-symbol `total_return_R`.
- `median_per_symbol_maximum_drawdown` = median of per-symbol `maximum_drawdown_pct`.
- `overall_maximum_drawdown` = maximum drawdown of the pooled global ledger, reported for diagnostics only.
- Validation gate 9 uses **median per-symbol maximum drawdown**; the candidate is not worse than the current-score baseline by more than 2 percentage points (`candidate - baseline <= 2.0` pp).

### Profit factor

- `gross_profit` = sum of positive `net_R_multiple` values for the symbol.
- `gross_loss` = sum of negative `net_R_multiple` values for the symbol.
- **Finite case:** `profit_factor = gross_profit / abs(gross_loss)` when `gross_loss < 0`. If `gross_profit == 0` and `gross_loss < 0`, the value is `0.0` (no-winner case).
- **No-loss-positive case:** `gross_loss == 0` and `gross_profit > 0`. `profit_factor` is `null` (JSON-safe). It is treated as `+∞` for comparison and median ranking, so it passes any positive finite threshold and any "not below baseline" comparison against a finite or other no-loss-positive value.
- **No-trade case:** `gross_profit == 0` and `gross_loss == 0`. `profit_factor` is `null`; the symbol is excluded from median and from paired/overlap computations and does not count toward computable-symbol minimums.
- **Median computability:** at least half of candidate-represented symbols (rounded up) must have a computable per-symbol profit factor (finite or no-loss-positive). If this is not met, the profit-factor gate is not computable and the split is `inconclusive`.
- **Ordering for gates 5 and 6:** `no_profit (0.0) < finite positive values < no_loss_positive (+∞)`, with `no_trade` excluded.
- **Gate 5:** passes if the median ordered value is `no_loss_positive` or a finite value >= `1.05`. `no_profit (0.0)` fails.
- **Gate 6:** passes if the candidate median ordered value is >= the baseline median ordered value. `no_loss_positive` beats any finite value; equal medians pass.

### Concentration

- **Trade-count concentration**: maximum per-symbol executed trade count / total executed trades in the split \<= 10%.
- **Net-profit concentration** (when total net R across the split is positive): maximum per-symbol total net R among symbols with positive per-symbol total net R / total net R across the split \<= 20%. Losing symbols cannot be the numerator.
- **Absolute-loss concentration** (when total net R across the split is zero or negative): maximum absolute per-symbol total net R among symbols with negative per-symbol total net R / sum of absolute per-symbol total net R for all symbols with negative per-symbol total net R in the split \<= 20%. Profitable symbols cannot be the numerator.
- All concentration numerators use **per-symbol aggregated contributions**, not individual trades.

### Gate 8 paired-symbol comparison

- Population = represented symbols that have at least one executed candidate trade **and** at least one executed corresponding baseline trade for the baseline being compared.
- Minimum paired-symbol overlap = 15. If overlap is below this, gate 8 is not computable and the split is `inconclusive`.
- `outperform_baseline_symbol_rate` = count of paired symbols with candidate mean `net_R_multiple` > baseline mean `net_R_multiple` / count of paired symbols.
- If a symbol has no baseline trade, it is excluded from the paired comparison for that baseline.

---

## 13. Data contract

The locked study must require:

- Five-minute OHLCV bars
- Complete regular-session history
- Provider provenance
- Explicit consolidated-versus-venue-specific volume disclosure
- Timestamp convention
- Timezone
- Corporate-action and adjustment policy
- Duplicate-bar reporting
- Missing-bar reporting
- Zero-volume reporting
- Exchange calendar version
- Security-type provenance
- Point-in-time universe membership
- Delisted-symbol handling
- Dataset manifest
- SHA-256 hash for every source file
- No silent provider fallback
- No mixing providers within one locked study

Data-sufficiency thresholds are locked in `INTRA-001-v1.json`:

| Quality check | Maximum allowed |
|---|---|
| Missing-bar rate per symbol | \<= 5% of expected regular-session bars |
| Zero-volume-bar rate per symbol | \<= 10% of expected regular-session bars |
| Duplicate-bar rate per symbol | \<= 1% of expected regular-session bars |
| Symbols rejected for data quality | \<= 5% of the monthly universe |

Exceeding these **data-sufficiency** thresholds makes the split `inconclusive`. Provider or provenance violations (silent provider substitution, missing manifest/provenance, material timestamp errors, manifest mismatch, etc.) make the split `invalid`.

---

## 14. Required future artifacts

`INTRA-001D` must produce:

```text
study.json
spec.lock.json
manifest.lock.json
universe_manifest.csv
data_quality.csv
session_features.csv
signals.csv
trades.csv
candidate_metrics.csv
baseline_metrics.csv
ticker_comparison.csv
monthly_comparison.csv
cost_sensitivity.csv
report.md
```

All programmatic outputs must be JSON-safe, schema-stable, deterministic, and free of `NaN` or `Infinity`.

---

## 15. Research integrity requirements

The specification explicitly addresses:

- Lookahead bias
- Same-bar ambiguity
- Timestamp semantics
- Session boundaries
- DST changes
- Early-close sessions
- Missing bars
- Duplicate bars
- Zero-volume bars
- Trading halts
- Corporate actions
- Adjusted versus unadjusted prices
- Survivorship bias
- Delisting bias
- Point-in-time universe membership
- Venue-specific versus consolidated volume
- Provider changes
- Slippage
- Liquidity and capacity
- Overlapping positions
- Multiple comparisons
- Parameter fishing
- Regime dependence
- Saved user weights
- Hidden local configuration
- Determinism

---

## 16. Provider feasibility review

### 16.1 Conclusion

**None of the current TradeX providers satisfies the full locked `INTRA-001` data contract on its own.** A separate point-in-time U.S. equity universe and security-type master is required before the real-data study can be promotion-eligible. This data-source decision is an `INTRA-001B` prerequisite.

### 16.2 Capability table

Evidence type is marked **documented** for items taken directly from an official API contract or library documentation, and **empirical** for items observed from testing the current wrapper or endpoint behavior. Empirical observations may change.

| Provider / source | Historical 5m date coverage | Full regular-session OHLCV | Consolidated vs. venue volume | Security-master availability | Delisted-symbol availability | Corporate-action behavior | Rate limits / pagination | Engineering impact | Satisfies full locked contract? | Evidence type and citations |
|---|---|---|---|---|---|---|---|---|---|---|
| **Yahoo Finance (yfinance)** | Last ~60 days for 5m; intraday not available for the full 2022-2025 range. | Yes via `period`/`interval` presets; no date-ranged 5m support. | Provider-aggregated; consolidated/venue status not exposed. | No security master; no point-in-time membership. | Delisted symbols not reliably queryable. | `auto_adjust=True` applies provider adjustments; no explicit split/dividend policy flag. | No auth, but rate-limited and undocumented. | Small, but insufficient depth. | **No** - 60-day 5m limit violates the dataset. | Documented library limitation: [yfinance `history()` wiki](https://github.com/ranaroussi/yfinance/wiki/Ticker#history), [yfinance issue tracker](https://github.com/ranaroussi/yfinance/issues). |
| **Alpaca Market Data API** | Historical bars since 2016; end must be at least 15 minutes old for SIP without Algo Trader Plus subscription.[^alpaca-sip] | Yes; supports 5m aggregations and date-ranged `start`/`end` with `feed=iex` or `feed=sip`. | Explicit `feed` (`iex` or `sip`) and `stock_adjustment` disclose volume/adjustment source. | Assets API lists current active assets; no historical-point-in-time membership. | Delisted/merged symbols may be queried if the symbol is known, but no guaranteed historical constituent list. | `stock_adjustment` supports `raw`, `split`, `dividend`, `spin-off`, `all`; `asof` maps symbol renames.[^alpaca-adj] | Basic: 200 req/min; Algo Trader Plus: 10,000 req/min; `limit` max 10,000 per page with `next_page_token` pagination.[^alpaca-rate] | Moderate: requires API keys, optional paid SIP tier, pagination for multi-year 5m data. | **No alone** - best current OHLCV candidate, but lacks point-in-time universe and guaranteed delisted coverage. | Documented API capability: [Alpaca Market Data API](https://docs.alpaca.markets/docs/about-market-data-api), [Stock Bars reference](https://docs.alpaca.markets/reference/stockbars). |
| **Interactive Brokers (TWS API)** | Requires Level 1 streaming subscription and running TWS/IB Gateway; 5m duration constrained by bar-size/duration table. | Yes for subscribed instruments with `whatToShow=TRADES` and `useRTH=True`. | Volume from historical bars is filtered (excludes off-NBBO trades); VWAP may differ from real time. | No security master via TWS API; contracts built manually. | No historical data for securities no longer trading. | `TRADES` split-adjustment depends on TWS settings; limited programmatic control. | Max 50 simultaneous historical requests; pacing; 5m typically limited to ~1 week per request. | High: requires local TWS/IB Gateway, subscriptions, pacing logic. | **No** - no delisted data, no point-in-time universe, 5m duration limits make multi-year collection impractical. | Documented API capability/constraint: [TWS API Historical Data](https://interactivebrokers.github.io/tws-api/historical_data.html), [Historical Limitations](https://interactivebrokers.github.io/tws-api/historical_limitations.html). |
| **Schwab Market Data API** | `get_price_history_every_five_minutes` appears to return roughly nine months of 5m candles; `periodType=day` with `frequencyType=minute` limited to period `<= 10`. Date-bound filtering is not reliably honored.[^schwab-empirical] | Yes for U.S. equities/ETFs; `need_extended_hours_data=False` can restrict to regular session. | Volume source and consolidation policy not explicitly documented. | `searchInstruments` supports symbol/CUSIP search; not a point-in-time security master. | No documented delisted support. | `auto_adjust` / provider adjustment behavior not configurable through `schwab-py`. | Undocumented; OAuth token and app registration required. | Moderate: requires Schwab brokerage account and OAuth app. | **No** - 5m coverage too shallow, date bounds unreliable, no point-in-time universe/delisted support. | Documented parameter limits: [Schwab Market Data API](https://developer.schwab.com/products/market-data-api), [schwab-py docs](https://github.com/jfernandrez/schwab-py). The nine-month depth and unreliable date-bound filtering are **empirical observations** from wrapper testing and are not guaranteed by Schwab. |
| **External point-in-time universe / security master** | Not an OHLCV provider; provides historical constituents and security-type provenance. | N/A | N/A | Can provide point-in-time membership and security-type provenance if the source contract supports it. | Can provide delisted-symbol coverage if the source contract supports it. | Varies by source; must be locked and disclosed. | Varies by source. | Moderate to high: may require paid vendor access or manual construction. | **Partial** - satisfies the universe/constituent contract only when combined with a 5m OHLCV provider. | This specification does **not** name a specific vendor. `INTRA-001B` must cite the selected source's contract and methodology and demonstrate that it provides historical monthly constituents, security-type provenance, delisted coverage, and point-in-time membership as of the first session of each calendar month. |

[^alpaca-sip]: SIP feed and 15-minute non-subscriber delay are described in Alpaca Market Data documentation; the Algo Trader Plus subscription is required for live SIP.
[^alpaca-adj]: `stock_adjustment` and `asof` parameters are documented in the Alpaca Stock Bars reference.
[^alpaca-rate]: Rate limits and `next_page_token` pagination are documented in the Alpaca Market Data API documentation.
[^schwab-empirical]: The ~9-month depth and unreliable date-bound filtering are empirical observations from testing `schwab-py` and are not guaranteed by Schwab.

### 16.3 Recommended data-source decision

**None of the current TradeX providers satisfies the full locked `INTRA-001` data contract on its own.** The data-source decision is therefore an `INTRA-001B` prerequisite.

The most feasible path is:

1. Use **Alpaca Market Data API with the Algo Trader Plus SIP feed** for consolidated 5m OHLCV from 2022-2025, with explicit `feed=sip` and `stock_adjustment` locked to `all` or `split`.
2. Source a **separate point-in-time U.S. equity universe and security-type master** that can demonstrate historical monthly constituents, security-type provenance, delisted-symbol coverage, and point-in-time membership as of the first session of each calendar month.
3. If no feasible point-in-time universe/delisted source is available, the real-data study must be declared **not promotion-eligible** and the outcome recorded as `inconclusive` or `invalid`.

Do not weaken the 2022-2025 five-minute requirement merely to fit the current `fetcher.py` five-day intraday preset.

## 17. Implementation phases

The following phases are defined but not implemented in this PR. INTRA-001B resumes after the approved `SHORT-001` Schwab real-data study is completed.

### 17.1 INTRA-001B - Intraday data and manifest infrastructure

- Approved provider integration
- Date-ranged five-minute snapshot
- Point-in-time universe manifest
- Session normalization
- Data-quality validation
- No strategy evaluation
- **Note:** This phase begins after the approved `SHORT-001` Schwab real-data study; the data-source decision is a prerequisite and must be locked before any INTRA-001 detector code is written

### 17.2 INTRA-001C — Research detector and execution engine

- Session VWAP
- Opening-drive state
- Pullback/reclaim detector
- Intraday execution model
- Current-score and simple-VWAP baselines
- Synthetic tests only
- No real holdout evaluation

### 17.3 INTRA-001D — Locked real-data study

- Build manifest from approved source
- Run development and validation
- Run holdout only if validation gates pass
- Commit safe reproducibility artifacts
- Record `supported`, `rejected`, `inconclusive`, or `invalid` outcome

### 17.4 Separate production PR

Only when:

- Both validation and holdout gates pass
- Methodology remains valid
- Gary explicitly approves production consideration

Must then define exact changes to the production scorer, scores or eligibility, weights, thresholds, ranking, screener behavior, UI, alerts, and rollback plan.

---

## 18. Production boundary

- This PR changes no production code.
- This PR changes no trading behavior.
- This PR adds no research implementation code.
- This PR retrieves no real market data.
- The existing production intraday score, weights, thresholds, and screener behavior remain unchanged.
- No dashboard control, watcher, alert, confluence, or ranking path is added for `INTRA-001`.

---

## 19. Machine-readable protocol

The canonical locked values are in `docs/research/specs/INTRA-001-v1.json`.

```text
JSON SHA-256: 239274cc650b21e215c91085d2a89e671e05d504200ac6daa4b70be60b8c81ef
```

Future study artifacts must record this SHA-256 and the commit that first added it.

---

## 20. Limitations and assumptions

- The study is long-only; short setups are out of scope.
- The universe uses monthly point-in-time membership. Without an external historical constituent source, survivorship and delisting biases cannot be eliminated.
- The 5 bps per side slippage assumption is a research default, not a guarantee of real fill performance.
- Volume used for liquidity and VWAP is the volume reported by the locked provider; venue-specific versus consolidated volume must be documented.
- Trading halts, auctions, and partial fills are not explicitly modeled.
- The candidate setup assumes one active trade per ticker per session; overlapping positions are prohibited.
- A passing study result is research-only and does not authorize production promotion without a separate Gary-approved production PR.
