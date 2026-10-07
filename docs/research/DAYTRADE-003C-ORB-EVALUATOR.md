# DAYTRADE-003C: ORB Source-Fidelity Amendment & Deterministic Synthetic Evaluator Foundation

## 1. Executive Summary & Governance Audit

Task ID: `DAYTRADE-003C-ORB-EVALUATOR-001`  
Upstream Strategy: `DAYTRADE-003B-ORB-SIP5M`  
Upstream Task ID: `DAYTRADE-003B-ORB-PREREG-001`  
Upstream Spec Path: [`docs/research/specs/DAYTRADE-003B-ORB-v1.json`](file:///docs/research/specs/DAYTRADE-003B-ORB-v1.json)  
**Locked Upstream Spec SHA-256:** `62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0`  
Resolution Spec Path: [`docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json`](file:///docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json)  
**Resolution Spec SHA-256:** `20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`  
Classification: `research_only_implementation_readiness`  
Base Commit SHA: `61639a49c50da9fe626754bbc0980070dbaf8a3c`  

### Governance Boundaries Confirmed
- Real market-data acquisition: **NO**
- External provider API calls: **NO**
- Private dataset access: **NO**
- Development execution: **NO**
- Validation execution: **NO**
- Holdout access: **NO**
- Production promotion: **NO**
- Registry state: `APPROVED_PRODUCTION_STRATEGIES == ()` strictly preserved.

This task moves the preregistered Stocks-in-Play 5-minute Opening Range Breakout (ORB) strategy toward executable readiness without reopening parameter optimization, searching for variants, or initiating unauthorized provider queries.

---

## 2. Upstream Immutability & Audit Trail

The historical preregistration artifacts created under DAYTRADE-003B:
- [`docs/research/specs/DAYTRADE-003B-ORB-v1.json`](file:///docs/research/specs/DAYTRADE-003B-ORB-v1.json)
- [`docs/research/DAYTRADE-003B-ORB.md`](file:///docs/research/DAYTRADE-003B-ORB.md)

remain **strictly byte-for-byte unmodified**. The upstream spec hash matches its canonical value:
```
62f5028c1b11a392aeb596c4e05b8c1f194cc5cec3af1a9406f4fe16c80460c0
```

All implementation clarifications, source-fidelity corrections, and execution rules are codified additively in [`docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json`](file:///docs/research/specs/DAYTRADE-003C-ORB-RESOLUTION-v1.json) (`20b43665ae214cfc988c41f818ea67b74052c4a0513e5ca9f2e276105f082bb6`), establishing an unbroken cryptographic audit trail prior to any empirical market-data access.

---

## 3. Pre-Data Source-Fidelity Correction: Relative Volume Lookback

**Correction Tag:** `SOURCE_FIDELITY_CORRECTION_PRE_DATA_ACCESS`

### The Discrepancy
The narrative in the DAYTRADE-003B specification described the Relative Volume denominator as using prior completed "eligible" sessions for symbol $j$.

### Primary Source Evidence
The primary paper (Zarattini, Barbon, Aziz 2024, SSRN 4729284) defines Relative Volume as:
$$\text{RV}(D, j) = \frac{\text{OpeningRangeVolume}(D, j)}{\frac{1}{14} \sum_{k=1}^{14} \text{OpeningRangeVolume}(D-k, j)}$$

This denotes **exactly the immediately preceding 14 completed regular trading sessions** for symbol $j$. It does not condition those 14 sessions on passing the $\$5.00$ price filter, passing the 1,000,000 ADV hurdle, passing the $\$0.50$ ATR hurdle, having $\text{RV} \ge 1.0$, being selected in the Top 20, or generating an executed trade.

### Locked TradeX Convention
1. Relative volume history requires the immediately preceding 14 completed regular XNYS trading sessions for the symbol, determined via canonical exchange calendar (`tradex.market.hours._calendar()`).
2. Observations are strongly typed via `OpeningRangeVolumeObservation(symbol, session_date, volume)`.
3. If any required prior opening-range observation in those 14 completed XNYS sessions is missing, duplicate, or dates are gapped: **FAIL CLOSED**.
4. The evaluator will **never** silently search further backward to find 14 "eligible" or "valid" sessions. Older replacement sessions cannot repair intermediate gaps.
5. Target session $D$ is strictly excluded from its own lookbacks.
6. Because no empirical market data has been accessed for DAYTRADE-003, this correction is recorded strictly prior to data access.

---

## 4. Resolution of Implementation Semantics

### AMB-02: ATR14 Calculation Convention
- **Classification:** `LOCKED_TRADEX_IMPLEMENTATION_CONVENTION`
- **Method:** Welles Wilder 14-session Average True Range.
- **Formulas:**
  $$\text{TR}_t = \max(\text{high}_t - \text{low}_t, |\text{high}_t - \text{close}_{t-1}|, |\text{low}_t - \text{close}_{t-1}|)$$
  $$\text{ATR}_{14} = \frac{1}{14} \sum_{i=1}^{14} \text{TR}_i \quad (\text{initial mean of first 14 TRs})$$
  $$\text{ATR}_t = \frac{(\text{ATR}_{t-1} \times 13) + \text{TR}_t}{14} \quad (\text{subsequent sessions})$$
- **Point-in-Time Boundary:** For session $D$, only data through session $D-1$ is utilized. Session $D$ prices never enter its own ATR calculation.
- **History Requirement:** Requires at least 15 continuous daily sessions leading up to $D-1$ to compute 14 True Range values without gaps. If insufficient, fails closed (non-computable).

### AMB-03: Position Sizing & Multi-Position 4x Portfolio Leverage
- **Classification:** `SOURCE_LINKED_SIZING_METHOD_AND_TRADEX_PORTFOLIO_CONVENTION`
- **Source Methodology:** Zarattini & Aziz (2023), SSRN 4416622.
- **Single-Position Sizing:**
  For session-start equity $A$, entry price $P$, and stop distance $R = 0.10 \times \text{ATR14}$:
  $$\text{risk\_shares} = \lfloor \frac{A \times 0.01}{R} \rfloor$$
  $$\text{leverage\_shares} = \lfloor \frac{4.0 \times A}{P} \rfloor$$
  $$\text{desired\_shares} = \min(\text{risk\_shares}, \text{leverage\_shares})$$
  Rejected if $R \le 0$, $P \le 0$, or $\text{desired\_shares} \le 0$. No fractional shares.
- **Portfolio-Level 4x Leverage Ceiling:**
  At all times:
  $$\text{gross\_open\_notional} \le 4.0 \times A$$
  When order triggers:
  $$\text{available\_gross\_capacity} = (4.0 \times A) - \text{current\_open\_gross\_notional}$$
  $$\text{actual\_shares} = \min(\text{desired\_shares}, \lfloor \frac{\text{available\_gross\_capacity}}{P} \rfloor)$$
  If $\text{actual\_shares} \le 0$, the order is recorded as `CAPACITY_REJECTED`.
- **Same-Timestamp Priority:**
  If multiple orders trigger in the same minute bar, priority is assigned by:
  1. Higher Relative Volume rank first (rank 1 before rank 2);
  2. Ticker ascending tie-break.
- **Capacity Recycling Invariant:**
  When a position closes, its gross notional capacity becomes available for later timestamps. For a position opened and stopped within the **same** minute bar, capacity is **not** recycled within that same minute; it is released beginning with the next minute.
- **Equity Compounding:**
  Session-start equity $A$ is fixed throughout session $D$. Compounding occurs strictly at session close:
  $$A_{D+1} = A_D + \text{net\_daily\_PnL}$$

### AMB-09: Commission Structure
- **Classification:** `RESOLVED_FOR_V1`
- **Rate:** $\$0.0035$ per share per executed side ($0.0070$ per share round-trip, 0 bps slippage under Scenario A).
- **Application:** Applied on both ENTRY and EXIT fills.
- **Round-Trip:** $2 \times q \times \$0.0035$ for $q$ shares.
- **Ticket Minimums:** Zero broker ticket minimums in v1. Preregistered slippage scenarios B (2 bps) and C (5 bps) provide formal execution cost hurdles.

### AMB-10: Corporate Actions / Price Basis
- **Classification:** `LOCKED_TRADEX_DATA_CONVENTION`
- **Policy:** Both daily OHLCV and intraday 1-minute OHLCV use **RAW / UNADJUSTED** prices and volumes.
- **Rationale:** Preserves point-in-time correctness, matches the primary paper's explicitly unadjusted IQFeed intraday convention, and prevents distortion between adjusted daily ATR thresholds and raw intraday execution prints.

### AMB-01: Universe Semantics & Stage-A Candidate Completeness
- **Classification:** `LOCKED_TRADEX_UNIVERSE_CONVENTION`
- **Target Universe:** All point-in-time provider records in the equity market whose primary exchange is NYSE or Nasdaq and which are active on the queried historical session date, including historically delisted securities.
- **Exclusion Policy:** No arbitrary post-hoc exclusion of ADRs, REITs, or CEFs. Provider type codes are preserved in metadata for downstream auditing.
- **Candidate Provider Path:** Massive/Polygon `/v3/reference/tickers` point-in-time active-as-of-date endpoint.
- **Candidate Pool Completeness Rule:** For every active member of the PIT universe on session $D$, all Stage-A required inputs (exact 14 completed daily bars for ADV, contiguous daily history for ATR14, exact dated 14 prior OR volume observations, and all 5 opening range minutes 09:30..09:34 ET) must be complete and valid. Any missing, corrupt, gapped, or misaligned data causes the entire session to **FAIL CLOSED** as `non_computable`. Genuine technical filter failures ($\text{price} \le 5$, $\text{ADV} < 1\text{M}$, $\text{ATR} \le 0.50$, $\text{RV} < 1.0$) remain normal non-qualification.

### Exchange Early-Close Sessions
- **Classification:** `LOCKED_TRADEX_SESSION_CONVENTION`
- **Policy:** Excluded from formal DAYTRADE-003 evaluation. Enforced via canonical `tradex.market.hours.get_market_session`. Early-close sessions return deterministic `EXCLUDED_EARLY_CLOSE`. Non-session calendar dates fail closed as `non_computable`. Regular full sessions only (09:30 to 16:00 ET). Exclusions are recorded deterministically in dataset manifests and study results.

### Top-20 Selection & No-Backfill Invariant
- At 09:35 ET, candidates satisfying:
  1. $\text{open} > \$5.00$
  2. $\text{ADV14} \ge 1,000,000$
  3. $\text{ATR14} > \$0.50$
  4. $\text{RV14} \ge 1.0$
  are sorted by RV descending (ticker ascending tie-break) and the Top 20 are selected.
- Selection occurs strictly **before** observing later price triggers or outcomes.
- If a selected Top-20 candidate is a Doji ($\text{OR\_open} == \text{OR\_close}$), it produces `NO_ORDER_DOJI`.
- **There is NO BACKFILL from rank #21.**

### State-Aware Stage-B Trade Path Validation
- **Minute Bar Iteration:** Iterates canonical sequence of regular session trading minutes 09:35..15:59 ET (385 minutes).
- **State-Aware Requirements:** Minute bars are strictly required ONLY while a candidate has an active pending order or an open position.
- **Dead/Completed States:** Candidates with `NO_ORDER_DOJI`, stopped out positions, EOD liquidated positions, or capacity rejected orders do NOT require future minute bars.
- **Fail-Closed Integrities:** Duplicate minute timestamps, NY date mismatches, symbol mismatches, or missing bars for active states fail closed as `non_computable`.

---

## 5. Lean Two-Stage Data Acquisition Architecture

To avoid acquiring complete intraday tick/minute bars for ~7,000 symbols across thousands of trading sessions, TradeX locks a two-stage data pipeline:

```
[Point-in-Time Universe: ~7,000 Equities]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│ Stage A: Candidate Construction (Decided at 09:35 ET)  │
│ - Raw daily OHLCV history for ADV14 & ATR14            │
│ - 09:30-09:34 5-minute OHLCV for session D             │
│ - First 5-minute volume history for prior 14 sessions  │
│ - PIT universe active-as-of-date metadata              │
└────────────────────────────────────────────────────────┘
                   │
                   ▼  (Select Top 20 by RV >= 1.0)
┌────────────────────────────────────────────────────────┐
│ Stage B: Trade-Path Acquisition (Top 20 Symbols Only)  │
│ - Full regular-session 1-minute bars (09:35 - 16:00)   │
│ - Stop-entry evaluation                                │
│ - Protective stop monitoring                           │
│ - Same-bar ambiguity detection                         │
│ - 15:59 EOD liquidation                                │
└────────────────────────────────────────────────────────┘
```

Stage-B acquisition depends strictly on Stage-A information available at 09:35. No future price outcomes influence candidate acquisition.

---

## 6. Deterministic Synthetic Evaluator Architecture

The research package lives in [`tradex/research/daytrade_orb/`](file:///tradex/research/daytrade_orb/):

| Module | Responsibility |
|---|---|
| [`models.py`](file:///tradex/research/daytrade_orb/models.py) | Typed immutable domain models: `DailyBar`, `MinuteBar`, `Candidate`, `RankedCandidate`, `OrderIntent`, `Trade`, `SessionResult`, `StudyResult`. |
| [`spec.py`](file:///tradex/research/daytrade_orb/spec.py) | Cryptographic loader and SHA-256 verifier for 003B and 003C specs. Fails closed on drift. |
| [`indicators.py`](file:///tradex/research/daytrade_orb/indicators.py) | Pure deterministic computations for ADV14, Wilder ATR14, and 14-session RV. |
| [`ranking.py`](file:///tradex/research/daytrade_orb/ranking.py) | 5-minute opening range evaluation, candidate qualification, Top-20 ranking, and no-backfill rules. |
| [`execution.py`](file:///tradex/research/daytrade_orb/execution.py) | 3-step conditional stop triggers, adverse gap-through fills, same-bar conservative collision, and cost calculations. |
| [`portfolio.py`](file:///tradex/research/daytrade_orb/portfolio.py) | Multi-position simulation, portfolio 4x leverage ceiling, same-minute priority, and capacity recycling. |
| [`metrics.py`](file:///tradex/research/daytrade_orb/metrics.py) | Study metrics, session-date block bootstrap (2,000 resamples, seed 20261007), and 5-step disposition precedence. |
| [`evaluator.py`](file:///tradex/research/daytrade_orb/evaluator.py) | End-to-end evaluator orchestrator and fail-closed holdout authorization guard. |
| [`dataset_contract.py`](file:///tradex/research/daytrade_orb/dataset_contract.py) | Two-stage dataset manifest schema, cryptographic hashing, and invariant validation. |

---

## 7. Metrics & Statistical Validation Protocol

### Daily Return Series & Non-Computable Session Isolation
Every valid regular full session enters the daily return series. Valid trading sessions where zero orders triggered contribute exactly **`0.0`** daily return and are included in the bootstrap. Corrupted or non-computable sessions do **not** enter the return series and do **not** masquerade as 0.0; instead, if any required full session is non-computable, the study automatically derives an integrity failure and Step 1 fails closed as **`INVALID`**. Furthermore, the block bootstrap fails closed if any non-computable session is encountered. Exchange early-close sessions are deterministically excluded (`EXCLUDED_EARLY_CLOSE`).

### Daily Turnover Metric
Daily two-sided traded notional turnover is computed as:
$$\text{DailyTurnover} = \frac{\sum (\text{entry\_notional} + \text{exit\_notional})}{\text{equity}}$$
The study metric `daily_turnover` is the mean daily turnover across all valid included full regular sessions. The maximum portfolio gross leverage used (`max_leverage_used`) is maintained and tracked as a separate metric.

### Session-Date Cluster Bootstrap
- **Cluster Variable:** `session_date` (resamples entire session dates with replacement).
- **Replicates:** 2,000.
- **Seed:** `20261007`.
- **Target Quantity:** Mean daily portfolio net return under Scenario B.
- **Confidence Interval:** 95th percentile interval ($2.5^{\text{th}}$ and $97.5^{\text{th}}$ percentiles).

### Locked Validation Disposition Hierarchy
1. **`INVALID`**: Material integrity, lookahead, non-computable required session, or execution violation.
2. **`INCONCLUSIVE`**: Evidence sufficiency failure ($< 100$ regular sessions with candidates, $< 500$ triggered trades, or $< 50$ unique securities traded).
3. **`NOT_SUPPORTED`**: Mean daily Scenario-B net return $\le 0.0$.
4. **`PROMISING_NOT_CONFIRMED`**: Mean daily Scenario-B net return $> 0.0$, but 95% bootstrap CI lower bound $\le 0.0$.
5. **`SUPPORTED`**: Mean daily Scenario-B net return $> 0.0$ AND 95% bootstrap CI lower bound $> 0.0$.

### Fail-Closed Holdout Guard
Holdout data access is permitted **strictly if** `validation_disposition == SUPPORTED`. All other dispositions (`INVALID`, `INCONCLUSIVE`, `NOT_SUPPORTED`, `PROMISING_NOT_CONFIRMED`, missing) reject access and raise `HoldoutAccessDeniedError`.

---

## 8. Verification Evidence

### Automated Test Coverage
- `tests/research/daytrade_orb/test_spec.py` (7 tests)
- `tests/research/daytrade_orb/test_indicators.py` (12 tests)
- `tests/research/daytrade_orb/test_ranking.py` (6 tests)
- `tests/research/daytrade_orb/test_execution.py` (5 tests)
- `tests/research/daytrade_orb/test_portfolio.py` (10 tests)
- `tests/research/daytrade_orb/test_metrics_and_bootstrap.py` (7 tests)
- `tests/research/daytrade_orb/test_evaluator_and_data_quality.py` (7 tests)
- `tests/research/daytrade_orb/test_dataset_contract.py` (2 tests)

Total targeted synthetic tests: **56 passing tests**.  
Combined targeted research test suite: **137 passing tests**.  
Ruff linting: **Clean (0 errors)** across all tests, scripts, and research packages.

---

## 9. Next Actions & Strict Boundaries

1. **No Market Data Acquisition:** Real Stage-A or Stage-B market data acquisition is NOT authorized in this task.
2. **No Empirical Execution:** Development, validation, and holdout splits remain strictly unexecuted.
3. **No Production Modification:** Production registry remains empty (`APPROVED_PRODUCTION_STRATEGIES == ()`).
4. **Next Recommended Task:** Bounded data-feasibility probe and acquisition tooling readiness, subject to Gary and independent ChatGPT review.
