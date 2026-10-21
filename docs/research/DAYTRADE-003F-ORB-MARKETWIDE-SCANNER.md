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
5. TradeX provides comprehensive coverage accounting, explicit feed disclosures (distinguishing consolidated SIP from free-tier IEX), and an audit view of excluded securities.

### Superseding Note
The initial proposal in Issue #118 for a 25-stock watchlist scanner is superseded. DAYTRADE-003F implements broad-market discovery across the full active U.S. equity universe, while preserving the synthetic demo fixture and custom JSON upload modes for offline research and testing.

---

## 2. Technical Feasibility & Capability Assessment

Before implementation, a rigorous technical feasibility assessment of market-data providers and endpoint contracts was conducted:

### Finding A: Market-Wide Scan Feasibility via Alpaca
* **Universe Discovery:** Alpaca provides `GET /v2/assets?status=active&asset_class=us_equity`, returning all active U.S. equities across NYSE and Nasdaq (~8,000 tickers) in a single synchronous call (< 1 second). Alternatively, Massive `/v3/reference/tickers` supplies 7,987 active equity tickers.
* **Batch Daily OHLCV:** Alpaca's multi-symbol market data endpoint (`/v2/stocks/bars`) accepts up to 100 symbols per request. Stage 1 daily bars (15 completed trading sessions, $D-15$ through $D-1$) for ~8,000 tickers require 80 batched requests (~24 seconds).
* **Two-Stage Universe Reduction:**
  1. *Stage 1 (Daily Filters):* Applying Opening Price $> \$5.00$, $\text{ADV14} \ge 1,000,000$ shares, and $\text{ATR14} > \$0.50$ on daily bars through $D-1$ immediately reduces the candidate universe from ~8,000 symbols to ~950 stocks (an **88% reduction**).
  2. *Stage 2 (Opening Range & RV14):* Fetching 1-minute regular session bars (09:30–09:34 ET) for session $D$ requires 10 batched requests. Retrieving opening range volumes for the exact prior 14 completed NYSE trading sessions requires 140 batched requests. Total Stage 2 requests: 150 requests (~45 seconds).
* **Pre-Market Warmup Advantage:** Because the 14 prior completed daily and opening-range volumes are fixed before the opening bell, they can be cached pre-market. A live scan executed at or after 09:35 ET needs only retrieve the 5 1-minute bars for session $D$ across the daily-eligible subset (~10 requests, **~3 seconds** execution time).

### Schwab API Limitation
* The Charles Schwab Trader API is strictly **single-symbol** for price history endpoints (`/v1/markets/pricehistory`), with a rate limit of 120 calls per minute.
* Schwab provides no universe listing endpoint for equity discovery.
* Scanning ~8,000 stocks sequentially over Schwab would require >66 minutes, making live 09:35 ET market scanning impossible.
* TradeX implements `SchwabORBProviderStub` which clearly surfaces this architectural limitation to the user and guides them to use Alpaca or Mock providers for broad scanning.

### Market-Data Feed Transparency: Consolidated SIP vs. IEX
* **Consolidated SIP (`feed="sip"`):** Covers 100% of tape volume across all U.S. exchanges (Tape A, B, C). RV14 calculations accurately reflect true institutional market volume.
* **Free-Tier IEX (`feed="iex"`):** Covers only volume executed on the Investors Exchange (~2% of consolidated U.S. equity tape).
* **Disclosure Governance:** TradeX never claims IEX data represents the true market-wide opening range volume. When `feed="iex"` is active, the UI renders a prominent warning: *"Provisional — IEX Free-Tier Feed. Free-tier IEX captures ~2% of consolidated tape volume. Relative volume figures reflect IEX exchange activity only and may diverge from the consolidated tape. Top 20 rankings are provisional."*

---

## 3. ORB Strategy & Evaluator Contract

DAYTRADE-003F directly reuses the locked research engine in `tradex.research.daytrade_orb` without modifying published thresholds, weights, or ranking policies:

| Rule Component | Requirement & Implementation |
|---|---|
| **Universe** | Broad U.S. common stocks and ADRs listed on NYSE, NYSE American, NYSE Arca, and Nasdaq (`XNYS`, `XASE`, `ARCX`, `XNAS`). |
| **Eligibility Filters** | Prior 14 completed regular trading sessions ($D-14 \dots D-1$):<br>1. $\text{Opening Price} > \$5.00$<br>2. $\text{ADV14} \ge 1,000,000$ shares (`compute_adv14`)<br>3. Wilder $\text{ATR14} > \$0.50$ (`compute_atr14_wilder`, requiring 15 completed daily bars $D-15 \dots D-1$) |
| **Opening Range** | 09:30:00–09:34:59 ET regular-session 1-minute bars (`evaluate_opening_range`). Direction:<br>• $\text{Close} > \text{Open} \implies \text{LONG}$ (prospective entry at OR High)<br>• $\text{Close} < \text{Open} \implies \text{SHORT}$ (prospective entry at OR Low)<br>• $\text{Close} == \text{Open} \implies \text{DOJI}$ (no order generated) |
| **Relative Volume** | $\text{RV14} = \frac{\text{Opening Range Volume at session } D}{\text{Mean Opening Range Volume over exact prior 14 completed XNYS sessions}}$.<br>Filter: $\text{RV14} \ge 1.0$. No substitutions with daily volume or approximate baselines. |
| **Time-Gating** | Strictly time-gated at or after 09:35:00 ET. Scans initiated prior to 09:35 ET fail closed with an explicit explanation. |
| **Ranking Policy** | 1. Relative Volume ($\text{RV14}$), descending.<br>2. Symbol, ascending (deterministic tie-breaker).<br>Top 20 candidates selected. |
| **Doji Invariant** | If a qualifying candidate has a Doji opening range, its status is `NO_ORDER_DOJI`. Pursuant to primary paper methodology, rank #21 is **not** backfilled. |
| **Protective Stop** | Displayed as theoretical offset: $0.10 \times \text{ATR14}$ relative to executed entry price (`fill ± 0.10 × ATR14`). No simulated fills or PnL are claimed. |

---

## 4. User Interface Implementation

The scanner UI is integrated seamlessly into `tradex/ui/tabs/orb_preview.py`:

1. **Mode Switcher:**
   - **Market-Wide Live Discovery (Default):** Automated broad-market opportunity discovery.
   - **Synthetic Demo Snapshot:** 33-symbol synthetic fixture for offline demonstration and deterministic testing.
   - **Upload Custom Snapshot JSON:** Direct ingestion of validated research JSON snapshots (up to 5 MB).

2. **Main Action:**
   - Prominent **Scan Market** button. No ticker or watchlist entry fields.
   - Real-time progress display tracking scanner stages: `DISCOVERY` $\to$ `DAILY_ELIGIBILITY` $\to$ `OPENING_RANGE` $\to$ `RANKING` $\to$ `COMPLETE`.

3. **Coverage & Provenance Card:**
   - Universe Size Discovered
   - Securities Evaluated
   - Daily Eligible Count
   - Qualifying OR Candidates
   - Top-N Ranked (e.g. 20)
   - As-of Timestamp and Session Date
   - Active Provider and Market-Data Feed
   - Coverage Completeness Percentage

4. **Candidate Opportunity Table:**
   - Columns: `Rank`, `Symbol`, `Setup`, `OR High`, `OR Low`, `Breakout Trigger`, `RV14`, `ADV14`, `ATR14`, `Theoretical Stop Offset`, `Setup Explanation`, `Feed`, `As-Of Time`.
   - Setup explanations clarify exactly why a stock qualified and why it holds its rank over others (e.g. *"Rank 1: Bullish OR LONG setup above $182.50; RV14 3.50x."*).

5. **Exclusions Audit Expander:**
   - Detailed audit view showing every candidate evaluated that did not qualify for Top 20, categorized by:
     - `TECHNICAL_FILTER`: Failed Price $> \$5$, ADV14 $\ge 1\text{M}$, ATR14 $> \$0.50$, or RV14 $< 1.0$.
     - `DATA_UNAVAILABLE`: Incomplete or missing daily/minute observations.
     - `INTEGRITY_BLOCKED`: Malformed timestamps, negative prices, or future-bar leakage.

---

## 5. Architecture & Code Structure

```
tradex/
├── research/
│   └── daytrade_orb/
│       ├── __init__.py          # Public exports for scanner and providers
│       ├── provider.py          # ORBMarketDataProvider Protocol, MockORBProvider,
│       │                        # AlpacaORBProvider, SchwabORBProviderStub, factory
│       ├── scanner.py           # run_market_scan orchestrator, ScanStage,
│       │                        # ScanProgress, MarketScanResult, CandidatePreviewRow
│       ├── indicators.py        # compute_adv14, compute_atr14_wilder, compute_relative_volume
│       ├── ranking.py           # evaluate_opening_range, evaluate_candidate, rank_and_select_top_20
│       ├── preview.py           # Evaluation pipeline and ExclusionCategory
│       └── models.py            # DailyBar, MinuteBar, OpeningRange, Candidate, RankedCandidate
└── ui/
    └── tabs/
        └── orb_preview.py       # Streamlit UI with Market-Wide Live Discovery mode
```

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
* `tests/research/daytrade_orb/test_scanner.py`: 12 passed in 0.26s.
* `tests/research/daytrade_orb/test_provider.py`: 9 passed in 0.17s.
* `tests/ui/test_orb_scanner_ui.py`: 4 passed in 0.18s.
* Full ORB suite (`tests/research/daytrade_orb` + related UI tests): **273 passed, 0 failed** in 29.61s.
* Lint verification: Scoped `ruff check tests scripts tradex/research/daytrade_orb tradex/ui/tabs/orb_preview.py` passed with **0 errors**.
