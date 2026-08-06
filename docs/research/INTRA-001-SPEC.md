# INTRA-001: Long open-drive VWAP pullback continuation

This file is the human-readable research specification for `INTRA-001`. The canonical, machine-readable locked specification is [`docs/research/specs/INTRA-001-v1.json`](./specs/INTRA-001-v1.json). Any future study artifacts must reference the SHA-256 and commit that first added this file.

**Status:** `pre_registered_not_executed`  
**Spec version:** `1`  
**JSON SHA-256:** `f858b634ce35919a277e9a88e7ef4caf3947e7e6dc047e9eacd8d7bf23540d9b`

This PR does **not** implement the setup, the intraday backtester, the data snapshotter, the production scorer, any dashboard change, or any trading integration. It locks exactly what a future study must do and the evidence it must produce.

---

## 1. Status and authority

`INTRA-001` is a **research-only** pre-registration. No production signal, score, weight, threshold, rank, eligibility rule, alert, or default is changed by this specification. Production promotion requires a separate Gary-approved production PR after `INTRA-001D` and only if every validation and holdout gate defined below passes unchanged.

This specification is the source of truth for the future implementation of:

- `INTRA-001B` — intraday data and manifest infrastructure
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

Evaluate after the first six completed five-minute bars, at 10:00 AM Eastern. The ticker qualifies when all of the following are true:

- Return from the 9:30 AM session open to the 10:00 AM close is at least `+0.75%`.
- The 10:00 AM close is above session VWAP.
- Cumulative regular-session volume from 9:30 AM through 10:00 AM is at least `1.50×` the median volume over the same first six bars during the prior 20 complete sessions.
- No required bar from 9:30 AM through 10:00 AM is missing.
- All input bars pass OHLCV validation.

The opening-drive state becomes fixed at 10:00 AM and must not be recomputed using later information.

### 5.5 Pullback and VWAP reclaim

Search from the first completed bar after 10:00 AM through the bar completing at 11:30 AM Eastern. The first bar satisfying all of the following is the reclaim bar:

- Bar low \<= session VWAP calculated for that completed bar.
- Bar close strictly above that VWAP.
- Bar close \> bar open.
- Bar close remains at or above the 9:30 AM session open.
- The opening-drive qualification remains valid.
- No prior bar in the pullback window already satisfied the reclaim definition.

The signal becomes known only at the reclaim bar’s completion.

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

Use the current production `tradex.signals.intraday.score`:

- Pass an explicit fresh `IntradayWeights()` instance.
- Never load `~/.tradex/weights.json`.
- Evaluate completed five-minute bars only.
- Restrict potential signals to 10:00 AM through 11:30 AM Eastern.
- Use the first score of at least `40` per ticker-session.
- Enter at the next five-minute bar open.
- Apply the same liquidity rules, stop formula, 1.5R target, costs, one-trade-per-session rule, and time exit as the candidate.

This baseline measures whether the concrete setup adds value beyond the existing generic score.

### 6.2 Baseline B — Simple VWAP reclaim

Use the same:

- Liquidity requirements
- Pullback window
- Reclaim-bar definition
- Entry
- Stop
- Target
- Costs
- Exit rules

But do **not** require:

- The `+0.75%` opening-drive return
- The `1.50×` opening-volume condition

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

## 9. Sample minimums

Validation and holdout must each contain:

| Requirement | Minimum |
|---|---|
| Executed candidate trades | 300 |
| Represented stock symbols | 25 |
| Represented ETFs | 8 |
| Candidate trades in the stock stratum | 100 |
| Candidate trades in the ETF stratum | 75 |
| Single ticker share of candidate trades | \<= 10% |
| Single ticker share of candidate net profit | \<= 20% |

Failure to meet sample minimums produces an `inconclusive` outcome, not a pass.

---

## 10. Validation gates

The candidate may proceed to holdout evaluation only when all of the following pass on validation:

1. Sample minimums are met.
2. Candidate pooled net expectancy at 5 bps per side is positive.
3. Candidate median per-symbol net expectancy exceeds the current-score baseline by at least `0.05R`.
4. Candidate median per-symbol net expectancy exceeds the simple-VWAP baseline by at least `0.03R`.
5. Candidate median per-symbol profit factor is at least `1.05`.
6. Candidate median per-symbol profit factor is not below either baseline.
7. At least `55%` of represented symbols have positive candidate expectancy.
8. At least `55%` of represented symbols outperform the current-score baseline.
9. Candidate maximum drawdown is not worse than the current-score baseline by more than `2` percentage points.
10. Both stock and ETF strata have nonnegative pooled expectancy.
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
| **Supported for promotion consideration** | All validation and holdout gates pass. |
| **Not supported** | Data and sample requirements are met, but one or more predefined performance gates fail. |
| **Inconclusive** | One or more sample minimums are not met, stock and ETF strata materially disagree, or uncertainty is too high to support or reject the hypothesis. |
| **Invalid** | Holdout leakage, future-bar use, post-hoc threshold changes, silent provider substitution, material timestamp errors, unresolved split/corporate-action errors, missing required provenance, or non-reproducible outputs. |

A result of `supported` is research-only and does not itself authorize production promotion.

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

### 16.1 Capability table

| Provider / source | Historical 5m date coverage | Full regular-session OHLCV | Consolidated vs. venue volume | Security-master availability | Delisted-symbol availability | Corporate-action behavior | Rate limits / pagination | Engineering impact | Satisfies full locked contract? | Evidence source |
|---|---|---|---|---|---|---|---|---|---|---|
| **Yahoo Finance (yfinance)** | Last ~60 days for 5m; intraday not available for the full 2022–2025 range. | Yes, but only via `period`/`interval` presets with no date-ranged 5m support. | Volume is provider-aggregated; consolidated/venue status not exposed. | No security master; no point-in-time membership. | Delisted symbols are not reliably queryable. | `auto_adjust=True` applies provider adjustments; no explicit split/dividend policy flag. | No authentication, but rate-limited and undocumented. | Small, but insufficient data depth. | **No** — 60-day 5m limit violates the dataset requirement. | yfinance `history()` docstring and issue #1389: 5m data must be within the last 60 days. |
| **Alpaca Market Data API** | Historical bars since 2016; end must be at least 15 minutes old for SIP without Algo Trader Plus. | Yes; supports 5m aggregations and date-ranged `start`/`end` with `feed=iex` or `feed=sip`. | Explicit `feed` parameter (`iex` or `sip`) and `stock_adjustment` parameter disclose volume/adjustment source. | Assets API lists current active assets; no historical-point-in-time membership. | Delisted / merged symbols may be queried if the symbol is known, but no guaranteed historical constituent list. | `stock_adjustment` supports `raw`, `split`, `dividend`, `spin-off`, `all`; `asof` maps symbol renames. | Basic: 200 req/min; Algo Trader Plus: 10,000 req/min; `limit` max 10,000 per page with `next_page_token` pagination. | Moderate: requires API keys, optional paid SIP tier, and pagination for multi-year 5m data. | **No alone** — lacks point-in-time universe membership and guaranteed delisted coverage, but best current candidate for OHLCV. | Alpaca Market Data API docs (`about-market-data-api`, `stockbars` reference). |
| **Interactive Brokers (TWS API)** | Varies by subscription; API requires Level 1 streaming data. Historical 5m requests are duration- and bar-size constrained. | Yes, for subscribed instruments using `whatToShow=TRADES` and `useRTH=True`. | Volume from historical bar data is filtered (excludes off-NBBO trades); VWAP may differ from real time. | No security master via TWS API; contracts must be constructed manually. | No historical data for securities that are no longer trading. | `TRADES` returns split-adjusted values depending on TWS settings; limited control. | Max 50 simultaneous historical requests; pacing violations for small bars; 5m typically limited to ~1 week per request by the bar-size/duration table. | High: requires local TWS/IB Gateway, market-data subscriptions, and request pacing logic. | **No** — no delisted data, no point-in-time universe, and 5m duration limits make multi-year collection impractical. | TWS API `historical_data.html` and `historical_limitations.html`. |
| **Schwab Market Data API** | `get_price_history_every_five_minutes` appears to return roughly nine months of 5m candles; `periodType=day` with `frequencyType=minute` is limited to period `<= 10`. | Yes, for U.S. equities and ETFs; `need_extended_hours_data=False` can restrict to regular session. | Volume source and consolidation policy are not explicitly documented. | `searchInstruments` supports symbol/CUSIP search but is not a point-in-time security master. | No documented support for delisted symbols. | `auto_adjust` / provider adjustment behavior not configurable through `schwab-py` wrapper. | Undocumented; OAuth token and app registration required; 5m date bounds are not reliably honored. | Moderate: requires Schwab brokerage account and OAuth app. | **No** — 5m coverage is too shallow, date bounds are unreliable, and no point-in-time universe/delisted support. | `schwab-py` docs (`get_price_history_every_five_minutes` description) and Schwab OpenAPI price-history parameters. |
| **External point-in-time universe / security master (e.g., CRSP/Compustat, QuantRocket, Polygon.io SIP)** | Not an OHLCV provider by itself; provides historical constituents, delisted symbols, and security-type provenance. | N/A — OHLCV must come from another source. | N/A | Yes — this is the category that can provide point-in-time membership and security-type provenance. | Yes — purpose-built for survivorship-bias and delisting control. | Varies by vendor; must be locked and disclosed. | Varies by vendor. | Moderate to high: may require paid vendor access or manual construction. | **Partial** — satisfies the universe/constituent contract but must be combined with a 5m OHLCV provider. | Domain knowledge of vendor offerings; no single current TradeX provider provides this. |

### 16.2 Recommended data-source decision

**None of the current TradeX providers satisfies the full locked `INTRA-001` data contract on its own.** The data-source decision is therefore an `INTRA-001B` prerequisite, not something this specification can hide or bypass.

The most feasible path is:

1. Use **Alpaca Market Data API with the Algo Trader Plus SIP feed** for consolidated 5m OHLCV from 2022–2025, with explicit `feed=sip` and `stock_adjustment` locked to `all` or `split`.
2. Source a **separate point-in-time U.S. equity universe and security-type master** (e.g., CRSP/Compustat, a vendor such as QuantRocket, or a manually maintained historical constituent list) to define the monthly top-50 stock stratum, enforce security-type exclusions, and handle delisted symbols.
3. If no feasible point-in-time universe/delisted source is available, the real-data study must be declared **not promotion-eligible** and the outcome recorded as `inconclusive` or `invalid`.

Do not weaken the 2022–2025 five-minute requirement merely to fit the current `fetcher.py` five-day intraday preset.

---

## 17. Implementation phases

The following phases are defined but not implemented in this PR.

### 17.1 INTRA-001B — Intraday data and manifest infrastructure

- Approved provider integration
- Date-ranged five-minute snapshot
- Point-in-time universe manifest
- Session normalization
- Data-quality validation
- No strategy evaluation

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
JSON SHA-256: f858b634ce35919a277e9a88e7ef4caf3947e7e6dc047e9eacd8d7bf23540d9b
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
