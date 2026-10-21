# DAYTRADE-003F: Market-Wide ORB Opportunity Scanner

**Task ID:** `DAYTRADE-003F-ORB-MARKETWIDE-SCANNER`  
**GitHub Issue:** [#118](https://github.com/gyairbyte/TradeX/issues/118)  
**Classification:** Research-Only Market Observation & Opportunity Discovery  
**Branch:** `antigravity/daytrade-003f-marketwide-orb-scanner`  
**Base Commit:** `df8753c239f5cedd8f2d880f81b603a60b998522` (PR #115 merge commit on `origin/main`)  
**Strategy Authority:** Zarattini, Barbon, Aziz (2024), *A Profitable Day Trading Strategy For The U.S. Equity Market* (Swiss Finance Institute RP 24-98 / SSRN 4729284)

---

## 1. Executive Summary & Objective

DAYTRADE-003F delivers a market-wide Opening Range Breakout (ORB) opportunity discovery scanner directly inside the TradeX application (located in the **Research Lab** under the **Day Trading / ORB Strategy** preview area).

When a user opens TradeX and clicks **Scan Market**:
1. TradeX automatically discovers eligible U.S. equities (NYSE and Nasdaq) without requiring the user to supply a watchlist or ticker list.
2. TradeX evaluates securities using the locked Zarattini et al. (2024) 5-minute Stocks-in-Play ORB methodology.
3. TradeX screens candidates across inexpensive daily filters before evaluating 1-minute intraday opening ranges.
4. TradeX ranks and displays the strongest qualifying opportunities (Top 20) with transparent explanations, setup direction, breakout entry levels, and theoretical risk context ($0.10 \times \text{ATR14}$ stop distance).
5. TradeX provides truthful stage-by-stage coverage accounting, explicit feed disclosures (distinguishing consolidated SIP from free-tier IEX), and an audit view of excluded securities.

### Superseding Note
The initial proposal in Issue #118 for a 25-stock watchlist scanner is superseded. DAYTRADE-003F implements broad-market discovery across the full active U.S. equity universe, while preserving the synthetic demo fixture and custom JSON upload modes for offline research and testing.

---

## 2. Technical Feasibility & Provider Limitations

Before implementation, a rigorous capability assessment of market-data providers and endpoint contracts was conducted:

### Finding A: Market-Wide Scan Feasibility via Alpaca
* **Universe Discovery:** Alpaca provides `GET /v2/assets?status=active&asset_class=us_equity`, returning the complete active U.S. equity universe on NYSE and Nasdaq (~8,000 tickers) in a single synchronous call (< 1 second). Alternatively, Massive `/v3/reference/tickers` can supply 7,987 active point-in-time exchange-filtered equities.
* **Batch Daily OHLCV:** Alpaca's multi-symbol market data endpoint (`/v2/stocks/bars`) accepts up to 100 symbols per request. Stage 1 daily bars (15 completed trading sessions, $D-15$ through $D-1$) for ~8,000 tickers require 80 batched requests.
* **Two-Stage Universe Reduction:**
  1. *Stage 1 (Inexpensive Daily Filters):* Applying $\text{ADV14} \ge 1,000,000$ shares and Welles Wilder $\text{ATR14} > \$0.50$ on daily bars through $D-1$ immediately reduces the candidate universe from ~8,000 symbols to ~950 stocks (an **88% reduction**).
  2. *Stage 2 (Intraday Opening Range & RV14):* Fetching 1-minute regular session bars (09:30–09:34 ET) for session $D$ requires 10 batched requests. Retrieving opening range volumes for the exact prior 14 completed NYSE trading sessions requires 140 batched requests. Total Stage 2 requests: 150 requests.
* **Throughput & Latency Reality:**
  - An on-demand broad-market scan makes $80 + 10 + 140 = 230$ HTTP requests.
  - At Alpaca's documented Basic rate limit of 200 requests/minute, an on-demand scan requires **approximately 70 to 120+ seconds** of network and pacing time.
  - Free-tier accounts also face a 15-minute delay on consolidated SIP data.
  - *Product Architecture Boundary:* An automated background scheduler or persistent pre-market cache daemon is **not authorized or implemented** in this PR. Sub-minute execution at 09:35 ET would require pre-market caching of the prior 14 daily and opening-range baselines, which is preserved as an explicit future architectural decision rather than unapproved background infrastructure.
  - TradeX reports actual execution timestamps: **Scan Requested At**, **Scan Completed At** (with elapsed runtime), and **Data Freshness Time** (09:34:59 ET regular-session close). Long-running scans are never falsely labeled real-time 09:35 if completed minutes later.

### Schwab API Limitation (Documented & Handled)
* The Charles Schwab Trader API is strictly **single-symbol** for price history endpoints (`/v1/markets/pricehistory`), with a strict rate limit of 120 calls per minute and no universe-listing endpoint.
* Sequentially querying ~8,000 symbols over Schwab would require **>66 minutes**, making real-time 09:35 ET market scanning architecturally impossible on Schwab.
* TradeX implements `SchwabORBProviderStub`, which fails closed with an explicit explanation rather than silently truncating or timing out.

### Market-Data Feed Transparency: Consolidated SIP vs. IEX
* **Consolidated SIP (`feed="sip"`):** Covers 100% of tape volume across all U.S. trading venues (Tape A, B, C). RV14 reflects true national institutional volume.
* **Free-Tier IEX (`feed="iex"`):** Covers only volume executed on the Investors Exchange (~2% of consolidated U.S. volume).
* **Strict Feed Consistency & No Implicit Switching:**
  - TradeX requires **explicit feed selection** prior to scanning.
  - If a 403 Forbidden entitlement error occurs on SIP, TradeX fails closed with an explicit entitlement explanation. It does **not** silently fallback to IEX or combine mixed daily SIP data with intraday IEX bars.
  - An IEX scan is always explicitly labeled **provisional** and never represented as a reproduction of the published SIP strategy:
    > *⚠️ PROVISIONAL RANKINGS (IEX FEED ONLY): TradeX evaluated X of Y securities using Alpaca free-tier IEX feed (~2% volume). Relative volume figures reflect IEX exchange activity only and may diverge from the consolidated tape. Top 20 rankings are provisional.*

### Bounded Alpaca Pagination
* In accordance with Alpaca documentation, `/v2/stocks/bars` responses may return fewer items than `limit` while additional pages remain.
* `AlpacaORBProvider` implements bounded pagination looping over `next_page_token` with token-cycle defense (`seen_tokens`) and a maximum page boundary (`max_pages = 50`) per batch to prevent infinite loops.

---

## 3. ORB Strategy & Evaluator Contract

DAYTRADE-003F directly reuses the locked research engine in `tradex.research.daytrade_orb` without modifying published thresholds, weights, or ranking policies:

| Rule Component | Requirement & Implementation |
|---|---|
| **Universe** | Broad U.S. common stocks and ADRs listed on NYSE, NYSE American, NYSE Arca, and Nasdaq (`XNYS`, `XASE`, `ARCX`, `XNAS`). |
| **Stage 1 Daily Filters** | Evaluated strictly through $D-1$ ($D-15 \dots D-1$):<br>1. $\text{ADV14} \ge 1,000,000$ shares (`compute_adv14`)<br>2. Wilder $\text{ATR14} > \$0.50$ (`compute_atr14_wilder`, requiring 15 completed daily bars $D-15 \dots D-1$) |
| **Stage 2 Price Filter** | Evaluated on **session $D$ regular-session opening print** at 09:30 ET (`or_open > $5.00`), strictly complying with Zarattini et al. (2024) and DAYTRADE-003B. Prior-session close ($D-1$) is **not** used as a hard filter, allowing gap-up stocks to qualify and gap-down stocks to be properly excluded upon opening. |
| **Opening Range** | 09:30:00–09:34:59 ET regular-session 1-minute bars (`evaluate_opening_range`). Direction:<br>• $\text{Close} > \text{Open} \implies \text{LONG}$ (prospective entry at OR High)<br>• $\text{Close} < \text{Open} \implies \text{SHORT}$ (prospective entry at OR Low)<br>• $\text{Close} == \text{Open} \implies \text{DOJI}$ (no order generated) |
| **Relative Volume** | $\text{RV14} = \frac{\text{Opening Range Volume at session } D}{\text{Mean Opening Range Volume over exact prior 14 completed XNYS sessions}}$.<br>Filter: $\text{RV14} \ge 1.0$. No substitutions with daily volume or approximate baselines. |
| **Time-Gating** | Strictly time-gated at or after 09:35:00 ET. Scans initiated prior to 09:35 ET fail closed with an explicit explanation. |
| **Ranking Policy** | 1. Relative Volume ($\text{RV14}$), descending.<br>2. Symbol, ascending (deterministic tie-breaker).<br>Top 20 candidates selected. |
| **Doji Invariant** | If a qualifying candidate has a Doji opening range, its status is `NO_ORDER_DOJI`. Pursuant to primary paper methodology, rank #21 is **not** backfilled. |
| **Protective Stop** | Displayed as theoretical offset: $0.10 \times \text{ATR14}$ relative to executed entry price (`fill ± 0.10 × ATR14`). No simulated fills or PnL are claimed. |

---

## 4. Truthful Market Coverage Accounting

TradeX tracks and reconciles data completeness across every stage of the market scanner:

1. **`universe_size_discovered`**: Total symbols returned from universe discovery.
2. **`daily_history_complete_count`**: Securities with contiguous, complete daily history ($D-15 \dots D-1$).
3. **`daily_eligible_count`**: Securities meeting ADV14 $\ge 1\text{M}$ and ATR14 $> \$0.50$.
4. **`or_observations_valid_count`**: Daily-eligible securities with valid 09:30-09:34 ET regular session prints.
5. **`rv_baseline_complete_count`**: Securities with complete 14-session prior opening range volumes.
6. **`eligible_candidates_count`**: Securities passing all filters ($\text{Open} > \$5.00$, $\text{RV14} \ge 1.0$).
7. **`missing_data_count`**: Total securities excluded due to `DATA_UNAVAILABLE` or `INTEGRITY_BLOCKED`.
8. **`securities_evaluated`**: Securities with complete, evaluable data (`universe_size_discovered - missing_data_count`).
9. **`coverage_completeness_pct`**: $\frac{\text{securities\_evaluated}}{\text{universe\_size\_discovered}} \times 100$.

### Truthful Status Classification
* **`full_market_sip`**: Requires `feed == "sip"`, `is_feed_consolidated == True`, and `coverage_completeness_pct >= 95.0%`.
* **`provisional_incomplete`**: Triggered whenever material data gaps drop completeness below 95%, explicitly disclosing that missing data prevents authoritative full-market rankings.
* **`provisional_iex`**: Triggered whenever the free-tier IEX feed is selected.
* **`failed`**: Triggered when a stage fails; the UI explicitly displays an error and never indicates a successful scan.

---

## 5. User Interface Implementation

Integrated into `tradex/ui/tabs/orb_preview.py`:

1. **Mode Switcher:**
   - **Market-Wide Live Discovery (Default):** Automated broad-market opportunity discovery.
   - **Synthetic Demo Snapshot:** 33-symbol synthetic fixture for offline demonstration and deterministic testing.
   - **Upload Custom Snapshot JSON:** Direct ingestion of validated research JSON snapshots (up to 5 MB).

2. **Scanner Provider & Feed Selection:**
   - **Alpaca Live Provider:** Features explicit feed selection:
     - `Consolidated Tape (SIP) — Published Strategy Requirement`
     - `IEX Free-Tier Feed (Provisional Heuristic Only)`
   - **Deterministic Mock Provider (Populated):** Seeded from `MockORBProvider.create_populated()` with the 33-symbol synthetic research universe, demonstrating qualifying Long, Short, and Doji setups, RV ties, and technical rejections completely offline and credential-free.

3. **Status Reporting & Timestamps:**
   - Real-time stage progress: `DISCOVERY` $\to$ `DAILY_ELIGIBILITY` $\to$ `OPENING_RANGE` $\to$ `RANKING` $\to$ `COMPLETE`.
   - Clear completion status: Success (SIP full-market), Warning (Provisional incomplete or IEX), or Error (Failed). Never claims success on incomplete or failed scans.
   - Displays **Scan Requested At**, **Scan Completed At** (with runtime elapsed), and **Data Freshness** (09:34:59 ET).

4. **Candidate Opportunity Table:**
   - Columns: `Rank`, `Symbol`, `Setup`, `OR High`, `OR Low`, `Breakout Trigger`, `RV14`, `ADV14`, `ATR14`, `Theoretical Stop Offset`, `Setup Explanation`.
   - Setup explanations clarify exactly why a stock qualified and why it holds its rank over others (e.g. *"Rank 1: Bullish OR LONG setup above $182.50; RV14 3.50x"*).
   - If rankings are provisional, the table header explicitly displays `Top N Ranked Opportunities — Provisional Rankings`.

5. **Exclusions Audit Expander:**
   - Detailed audit view showing every candidate evaluated that did not qualify for Top 20, categorized by:
     - `TECHNICAL_FILTER`: Failed Price $> \$5$, ADV14 $\ge 1\text{M}$, ATR14 $> \$0.50$, RV14 $< 1.0$, or ranked outside Top 20.
     - `DATA_UNAVAILABLE`: Incomplete daily history, missing OR prints, or missing prior OR baseline.
     - `INTEGRITY_BLOCKED`: Malformed timestamps, negative prices, or future-bar leakage ($\ge 09:35$ ET bars in opening range).

---

## 6. Strict Research Isolation

In compliance with TradeX research-governance principles:
* **Production Invariant Preserved:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains strictly empty.
* **No Production Changes:** Zero modifications to production `tradex/screener/engine.py`, `tradex/tracker/watcher.py`, `tradex/signals/`, `tradex/ui/tabs/scanner.py`, or `tradex/ui/tabs/today.py`.
* **Zero Automated Trading:** No orders, fills, broker integrations, portfolio positions, or live alerts.
* **Network-Free Unit Tests:** Automated tests mock all providers without network calls or external credentials.

---

## 7. Verification & Test Evidence

### Test Summary
* `tests/research/daytrade_orb/test_scanner.py`: 16 passed.
  - Tests gap-up ($4.90 close $\to$ $5.20 open, qualifies) and gap-down ($5.20 close $\to$ $4.90 open, excluded at OR).
  - Tests 100-symbol mock with 90 missing bars, asserting `provisional_incomplete` coverage.
  - Tests full-market SIP coverage when completeness $\ge 95\%$.
  - Tests scan requested, completed, and freshness timestamps.
* `tests/research/daytrade_orb/test_provider.py`: 12 passed.
  - Tests Alpaca pagination following `next_page_token` across pages.
  - Tests pagination cycle detection.
  - Tests 403 fail-closed entitlement error without feed switching or feed mixing.
  - Tests `MockORBProvider.create_populated()` with 33 symbols.
* `tests/ui/test_orb_scanner_ui.py`: 6 passed.
  - Tests provisional warnings on incomplete coverage and IEX feed.
  - Tests failed scan displays error status, never success.
  - Tests timestamp caption rendering.
* Full ORB test suite: **282 passed, 0 failed** in 30.81s.
* Lint verification: Scoped `ruff check tests scripts tradex/research/daytrade_orb tradex/ui/tabs/orb_preview.py` passed with **0 errors**.
