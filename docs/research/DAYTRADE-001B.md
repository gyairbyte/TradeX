# DAYTRADE-001B: Extreme Downside 1-Minute Reversal Research Specification

This document is the human-readable research contract and pre-registration specification for `DAYTRADE-001B`. The canonical, machine-readable locked specification is [`docs/research/specs/DAYTRADE-001B-v1.json`](./specs/DAYTRADE-001B-v1.json). Any future execution, study artifacts, or analysis must reference this specification, its SHA-256, and its base commit.

* **Task ID:** `DAYTRADE-001B`
* **Classification:** Research-only / pre-registration (zero production impact)
* **Status:** `pre_registered_not_executed`
* **Spec Version:** `1`
* **JSON SHA-256:** `6977066c93e3f7b89f22fa2e7e9b00af808cc7cb2f5c00e1626672640b9a4ba5`
* **Base Commit SHA:** `089be61a8ad0c5b9e7b2909dd2f3e2f3e460b03b`

> [!IMPORTANT]
> **Zero Network / Zero Execution Invariant:**
> This specification PR performs **zero market-data requests**, contacts no external APIs, does not construct datasets, and evaluates no historical returns. It strictly locks the hypothesis, methodology, data contract, parameters, statistical tests, validation gates, and holdout conditions prior to any data observation.
> Future execution (`DAYTRADE-001C` or equivalent) remains unauthorized until this specification is reviewed and merged.

---

## 1. Status, Authority, and Scope

`DAYTRADE-001B` is an authorized research-design slice following Gary Yang's approval to advance the `DAYTRADE-001` program after `DAYTRADE-001A` (PR #86).

* **No Production Changes:** This specification alters no production code, scorers, indicators, weights, thresholds, alerts, candidate persistence, Journal logic, or dashboard surfaces.
* **Registry Invariant:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains strictly preserved in `tradex/strategies/registry.py`.
* **No Automatic Promotion:** Even if future validation and holdout phases pass every gate, this study cannot authorize production promotion directly (`production_promotion_eligible = false`).
* **Multi-Resolution Boundary:** DAYTRADE-001A defined the architectural hierarchy (`DAILY → TICK_133 → MINUTE_1 → TICK_50 → execution`). `DAYTRADE-001B` isolates and tests exclusively whether the **1-minute statistical phenomenon exists**. Neither 133-tick nor 50-tick data acquisition is authorized.

---

## 2. Objective and Falsifiable Hypothesis

The goal of this study is to pre-register a rigorous, falsifiable event-study test for the first empirical DAYTRADE hypothesis:

> **Hypothesis:** Among the fixed Dow 30 research universe, an unusually extreme negative completed 1-minute return is followed by a positive short-horizon reversal that exceeds comparable non-event intraday returns after realistic execution friction.

### Key Study Characterization
* **Study Type:** `event_study`.
* **Not an Executable Backtest:** This study evaluates unconditional forward return distributions following extreme-move events. It does not model portfolio capital allocation, position sizing, simultaneous trade limits, or trailing stops.
* **Overlapping Events:** Multiple tickers (or the same ticker on consecutive minutes) may generate events simultaneously. Overlapping events are permitted, fully tracked, and explicitly reported.
* **Acceptable Outcomes:** A finding of `unsupported`, `inconclusive`, or `invalid` is scientifically valid and fully acceptable. The protocol is designed to eliminate post-hoc optimization and confirmation bias.

---

## 3. Direction and Asymmetry

* **Direction:** Long-side reversal only.
* **Event Phenomenon:** The study investigates whether an acute downward price dislocation produces an immediate positive bounce.
* **Asymmetry:** No symmetric short-side hypothesis (fading upside spikes) is tested in version 1. Upside dynamics involve distinct order-flow and momentum characteristics that must be evaluated under a separate, independently pre-registered hypothesis if pursued later.

---

## 4. Universe and Survivorship Disclosures

### 4.1 Fixed Universe Definition
The universe is locked to the 30 symbols in the repository preset:
`tradex.watchlists.presets.DOW30`

The exact frozen constituent list is:
```text
MMM, AXP, AMGN, AMZN, AAPL, BA, CAT, CVX, CSCO, KO,
DIS, GS, HD, HON, IBM, JNJ, JPM, MCD, MRK, MSFT,
NKE, NVDA, PG, CRM, SHW, TRV, UNH, VZ, V, WMT
```

### 4.2 Constituent Survivorship and Selection Limitations
* **Preset Vintage:** The preset is a static snapshot taken in May 2026.
* **Retrospective Limitation:** Applying a 2026 constituent list to 2025 historical data introduces survivorship bias and constituent-selection lookahead (e.g., historical Dow index changes during 2024–2026 are not dynamically reconstructed).
* **Scope Decision:** DAYTRADE-001B explicitly accepts this limitation for this initial bounded exploratory study to keep data acquisition lean and deterministic.
* **Evidence Cap:** Due to this known survivorship limitation, the maximum evidence confidence rating this study can ever achieve is:
  `maximum_evidence_confidence = limited_but_usable_evidence`
* **Constituent Reconstruction Prohibited:** Historical point-in-time constituent reconstruction is out of scope for v1.

---

## 5. Proposed Future Data Contract

Future execution must conform to the following locked data contract:

| Dimension | Locked Specification |
|---|---|
| **Provider** | Alpaca Market Data API (`alpaca`) |
| **Feed** | `sip` (Securities Information Processor consolidated tape) |
| **Timeframe** | `1Min` (1-minute bars) |
| **Adjustment Policy** | `split` (split-adjusted only; no dividend adjustments to intraday prices) |
| **Calendar & Sessions** | `XNYS` regular trading sessions only (09:30–16:00 ET) |
| **Timezone** | `America/New_York` |

### Provider and Storage Constraints
1. **No Fallback Allowed:** If the locked `sip` feed cannot be accessed (e.g., entitlement or credential restriction), the execution engine must halt and record a provider/entitlement blocker. Silent fallback to `iex`, `yahoo`, `schwab`, `ibkr`, or any other feed is strictly prohibited.
2. **Git Storage Prohibited:** Raw market data files must never be committed to Git.
3. **Storage Location:** Future raw and processed datasets must reside outside the tracked repository tree, under `~/.tradex/research/daytrade_001b/` or an explicitly configured external path.

---

## 6. Date Coverage and Dataset Splits

The study spans 13 calendar months partitioned into four non-overlapping chronological periods:

```
[ Warm-up: 2024-12-02 -> 2025-01-01 ]  (~20 trading days: historical trailing window only)
       ↓
[ Development: 2025-01-02 -> 2025-06-30 ]  (Diagnostic only; parameters locked)
       ↓
[ Validation: 2025-07-01 -> 2025-09-30 ]   (Formal gate evaluation)
       ↓ (Conditional on Validation == 'supported')
[ Holdout: 2025-10-01 -> 2025-12-31 ]      (Untouched final evaluation)
```

### Split Boundaries and Partitioning Discipline
* **Warm-up Acquisition:** `2024-12-02` through `2025-01-01`. Supplies the initial 20 completed regular sessions for trailing baseline calculations. **Zero events or signals may originate from warm-up data.**
* **Development Split:** `2025-01-02` through `2025-06-30`. Used strictly for code diagnostic checks, pipeline verification, and distributional sanity. All study parameters remain locked.
* **Validation Split:** `2025-07-01` through `2025-09-30`. The primary evaluation dataset for pre-registered validation gates.
* **Untouched Holdout Split:** `2025-10-01` through `2025-12-31`. Remains strictly unparsed and unread until validation passes all gates.
* **Boundary Guard:** Forward outcome horizons must never cross a split boundary. Observations near the end of a split without complete forward bars inside that split are truncated.

---

## 7. Session Semantics and Timestamp Availability

* **Calendar:** NYSE regular trading sessions under the `XNYS` calendar.
* **Session Window:** 09:30:00 to 16:00:00 Eastern Time.
* **Early-Close Sessions:** Early-close sessions (e.g., post-Thanksgiving, Christmas Eve) are excluded in their entirety.
* **Extended Hours:** Premarket (before 09:30) and after-hours (after 16:00) bars are excluded.
* **No Missing Bar Interpolation:** Missing bars must not be synthetically filled or interpolated.
* **Timestamp Normalization:** Every bar is represented with two distinct timestamps:
  * `bar_start`: Beginning of the 1-minute interval.
  * `available_at`: End of the 1-minute interval when the bar close is finalized.
  * *Rule:* A 1-minute bar starting at 09:35 is not available until 09:36:00. The signal from completed minute $t$ is known only at `available_at`.

---

## 8. Extreme-Move Event Definition

The extreme downside move definition is fixed and deterministic:

### 8.1 Trailing Window and Percentile Specification
For each ticker evaluated on trading day $D$:
1. Calculate completed regular-session 1-minute close-to-close returns:
   $$R_t = \frac{\text{close}_t - \text{close}_{t-1}}{\text{close}_{t-1}}$$
2. Form the trailing reference distribution from the **previous 20 completed regular sessions** for that ticker.
3. Determine the empirical **0.1st percentile** of those historical 1-minute returns:
   * **Percentile scale:** `percentile_points = 0.1`
   * **Quantile scale:** `quantile = 0.001` (one-tenth of one percent; NOT the 10th percentile / 0.10).
4. Classify completed minute $t$ as an event when:
   $$\text{return}_t \le \text{empirical\_quantile}(\text{trailing\_20\_sessions}, 0.001)$$

### 8.2 Prohibition on Parameter Fishing
No alternative cutoffs may be evaluated:
* No alternative percentiles (e.g., 0.5%, 1.0%, 5.0%).
* No standard-deviation / z-score multipliers (e.g., $-3\sigma$, $-4\sigma$).
* No fixed percentage cutoffs (e.g., $-1.0\%$, $-2.0\%$).
* No ATR thresholds or rolling volatility bands.

---

## 9. Eligible Event Times

* **Opening Minute Ineligibility:** The 09:30 opening bar (09:30–09:31) is ineligible as an event bar. The opening minute frequently reflects overnight auction resolution and gap pricing rather than a within-session dislocation.
* **Earliest Event Bar:** Minute starting at `09:31` (completing and available at `09:32`).
* **Latest Event Bar:** Minute starting at `15:54` (completing at `15:55`).
  * *Reasoning:* Entry occurs at 15:55 open. The maximum forward horizon of 5 minutes requires bars from 15:55 to 16:00 to complete inside the regular session.
* **Session Close Boundary:** No forward outcome window may extend beyond the 16:00:00 session close.

---

## 10. Information Availability and Execution Timing

Strict point-in-time execution timing is mandatory:

```
Minute t (Event Bar):   [ 09:35:00 ------------------- 09:36:00 ]
                                                       ▲
                                            Event Detected Here
                                            (at available_at)

Minute t+1 (Entry Bar):                         [ 09:36:00 ------------------- 09:37:00 ]
                                                ▲                              ▲
                                        Hypothetical Entry             Primary 1m Exit
                                           (Next Open)                  (Entry Close)
```

1. **Signal Availability:** The event condition is evaluated and confirmed only after minute $t$ has completely closed (at `available_at`).
2. **Next-Bar Execution:** Hypothetical entry occurs at the **open of minute $t+1$**.
3. **Prohibition on Same-Bar / Close Execution:** Assuming entry at the close of minute $t$ is strictly prohibited. Fills cannot use the same price that established the signal.

---

## 11. Outcome Horizons

Exactly three forward horizons are locked:

### 11.1 Primary Endpoint: 1-Minute Forward Return
* **Entry:** Open of minute $t+1$.
* **Exit:** Close of minute $t+1$.
* **Formula:**
  $$R_{\text{forward, 1m}} = \frac{\text{close}_{t+1} - \text{open}_{t+1}}{\text{open}_{t+1}}$$
* **Role:** This is the sole primary endpoint. All validation and holdout support gates evaluate this horizon.

### 11.2 Secondary Endpoints (Descriptive Evidence Only)
* **2-Minute Forward Return:** Entry at minute $t+1$ open; exit at minute $t+2$ close.
* **5-Minute Forward Return:** Entry at minute $t+1$ open; exit at minute $t+5$ close.
* **Role:** Secondary endpoints provide descriptive evidence on reversal decay and persistence. They do not determine validation or holdout pass/fail status.
* **No Horizon Grid Search:** Evaluating an open grid of arbitrary forward minutes (e.g., 3m, 7m, 10m, 15m) is prohibited.

---

## 12. Execution Friction Assumptions

All net performance metrics must incorporate realistic execution friction:

* **Primary Friction Assumption:** `2.0 basis points per side` ($0.02\%$ per side, or $4.0\text{ bps}$ round-trip).
  $$\text{Net Return} = R_{\text{gross}} - 0.0004$$
* **Sensitivity Scenarios:**
  * Zero-cost baseline: `0.0 bps per side` ($0.0\text{ bps}$ round-trip).
  * Stressed friction: `5.0 bps per side` ($10.0\text{ bps}$ round-trip).
* **Commissions:** No separate commissions modeled beyond the all-in friction rate.
* **Reporting:** Gross returns and all three net friction scenarios must be reported side by side.

---

## 13. Baseline and Control Methodology

To determine whether the observed reversal is a genuine event effect or simply typical intraday behavior:

* **Baseline Definition:** For each ticker, compare each event observation's forward return with all **non-event observations from the same ticker and the same minute-of-day within the same dataset split**.
* **Exclusion of Events:** Event observations must be strictly excluded from the baseline reference set.
* **No Unvalidated Proxies:** Production TradeX heuristic scores or user weights must not be used as the comparison benchmark.
* **Reported Metrics:**
  1. Absolute Event Net Return ($R_{\text{event}}$).
  2. Event-minus-Baseline Difference ($R_{\text{event}} - R_{\text{baseline}}$).

---

## 14. Required Metrics

Future execution reports across development, validation, and holdout must present at minimum:

1. Eligible minute count
2. Event count
3. Represented ticker count
4. Events per ticker
5. Events per month
6. Maximum single-ticker event concentration (%)
7. Overlapping event count and overlapping rate (%)
8. Mean gross forward return (1m / 2m / 5m)
9. Median gross forward return (1m / 2m / 5m)
10. Win rate (% positive) at each horizon
11. Mean net forward return under all locked friction scenarios (0 bps, 2 bps, 5 bps)
12. Median net forward return under all locked friction scenarios
13. Same-ticker / time-of-day baseline mean and median return
14. Event-minus-baseline mean and median uplift
15. Per-ticker primary net return and event count
16. Monthly primary net return and event count
17. Data-quality audit summary (missing, duplicate, malformed, excluded counts)
18. Provider provenance summary (requests, pages, retries, timestamps)

---

## 15. Statistical Inference and Confidence Intervals

To account for clustering and intra-session correlation across events:

* **Method:** Cluster bootstrap resampling by **ticker-session**. All events occurring for the same ticker on the same trading session are treated as a cluster and sampled together.
* **Resample Count:** `2,000` bootstrap replications.
* **Deterministic Random Seed:** `20260925`.
* **Confidence Level:** Two-sided `95%` confidence interval (percentile bootstrap method).
* **Evaluated Quantities:**
  1. Mean primary 1-minute net return (under 2 bps/side friction).
  2. Mean primary 1-minute event-minus-baseline difference.

---

## 16. Validation Support Gates

The validation split is classified as **`supported`** if and only if **all five** of the following gates pass simultaneously:

| Gate | Criterion | Threshold |
|---|---|---|
| **1. Sample Gate** | Eligible event count and breadth | $\ge 300\text{ events}$ across $\ge 15\text{ tickers}$ |
| **2. Concentration Gate** | Maximum single-ticker contribution | No single ticker $> 15.0\%$ of all validation events |
| **3. Primary Net-Effect Gate** | Mean 1m net return (2 bps/side) | Mean $> 0$ **and** 95% Clustered CI lower bound $> 0$ |
| **4. Baseline-Uplift Gate** | Mean 1m event-minus-baseline return | Mean $> 0$ **and** 95% Clustered CI lower bound $> 0$ |
| **5. Ticker Breadth Gate** | Cross-sectional consistency | $\ge 60.0\%$ of represented tickers have positive mean net return |

No gates may be relaxed or modified after inspecting validation data.

---

## 17. Holdout Rule

* **Gated Evaluation:** The untouched holdout split (`2025-10-01` to `2025-12-31`) may only be unsealed and evaluated if the validation split achieves the disposition **`supported`**.
* **Identical Criteria:** The holdout split must satisfy the exact same five gates without modification.
* **Zero Post-Hoc Tuning:** No parameter, threshold, universe, cost, or window adjustments are permitted between validation and holdout.
* **Failure Policy:** If validation fails any gate, holdout data must remain unread, unparsed, and untouched, and the study terminates with disposition `rejected` or `inconclusive`.

---

## 18. Study Dispositions

The study report must conclude with one of four locked dispositions:

* **`supported`:** All sample minimums and all five validation (and conditional holdout) gates pass.
* **`rejected`:** Data and methodology are valid and sufficiently sampled, but the primary hypothesis yields non-positive net expectancy or non-positive uplift over the baseline.
* **`inconclusive`:** The study cannot form a definitive conclusion due to:
  * Fewer than 300 eligible events or fewer than 15 represented tickers.
  * Ticker concentration exceeding 15%.
  * Effect direction is positive but the 95% confidence interval crosses zero.
  * Data coverage is usable but insufficient to meet validity thresholds.
* **`invalid`:** The study execution violates methodological integrity, including:
  * Lookahead bias or future-bar leakage.
  * Holdout partition unsealed before validation was confirmed `supported`.
  * Timestamp normalization errors or entry at the event-bar close.
  * Split contamination (outcomes crossing split boundaries).
  * Silent provider or feed substitution.
  * Corrupted, unverified, or non-reproducible data.

---

## 19. Data-Quality Requirements

Normal NYSE sessions must expect 390 completed regular-session 1-minute bars (09:30–16:00).
1. **Session Missing-Bar Limit:** If a ticker-session has a missing-bar rate $> 5.0\%$ ($> 19$ missing bars), exclude that ticker-session entirely.
2. **Session Duplicate-Bar Limit:** If a ticker-session has a duplicate-bar rate $> 1.0\%$ ($> 3$ duplicate bars), exclude that ticker-session entirely.
3. **Malformed Timestamps:** Timestamps failing strict parsing or timezone validation fail closed for affected rows and are recorded.
4. **Split Data-Sufficiency Gate:** If $> 5.0\%$ of ticker-sessions in a split are excluded due to data-quality defects, the split disposition cannot be `supported` (it resolves to `inconclusive` or `invalid`).

---

## 20. Research Integrity Safeguards

This specification explicitly mitigates structural research risks:

| Risk Dimension | Safeguard Enforced |
|---|---|
| **Lookahead Bias** | Strict separation of signal bar (`available_at`) from execution bar (`open_{t+1}`). |
| **Execution Price Bias** | Fills assume next-bar open; fills at signal-bar close are strictly prohibited. |
| **Split Leakage** | Chronological partitions; outcomes never cross split boundaries. |
| **Holdout Contamination** | Holdout sealed until validation achieves `supported`. |
| **Survivorship / Selection Bias** | Fully disclosed; fixed 2026 snapshot accepted; evidence capped at `limited_but_usable_evidence`. |
| **Feed Inconsistency** | Locked to Alpaca SIP; zero feed fallback permitted. |
| **Corporate Actions** | Split adjustments applied; cash dividends excluded from intraday returns. |
| **Calendar / DST Anomalies** | XNYS exchange calendar enforced; early closes excluded; timezone pinned to `America/New_York`. |
| **Overlapping Events** | Explicitly audited, reported, and clustered in bootstrap inference. |
| **Observation Dependence** | Ticker-session cluster bootstrap prevents overstating statistical significance. |
| **Parameter P-Hacking** | Single locked percentile cutoff (0.1st percentile = quantile 0.001); no grid search. |
| **Horizon Fishing** | Exactly one primary endpoint (1m); secondary endpoints (2m, 5m) descriptive only. |
| **Execution Friction** | Primary 2 bps/side friction enforced; gross-only results cannot support hypothesis. |
| **Concentration Distortion** | Single ticker capped at $\le 15\%$ of events; $\ge 60\%$ ticker breadth required. |
| **Saved Weight Entanglement** | Production TradeX heuristic scores quarantined; neutral non-event baseline used. |
| **Reproducibility** | Deterministic random seed (`20260925`), deterministic spec JSON, zero credentials in code. |

---

## 21. Bounded Future Execution Budget

`DAYTRADE-001B` executes **zero network calls**.
For future execution (`DAYTRADE-001C` or equivalent), the budget is strictly bounded:
* **Time Span:** One evaluation year (2025) plus approximately one month of warm-up (December 2024).
* **Universe:** Fixed DOW 30 only (30 tickers).
* **Resolution:** 1-minute bars only (no tick data).
* **Feed:** Alpaca SIP only.
* **HTTP Retries:** Maximum 1 retry per failed page.
* **Audit:** Total requests, pages, retries, and bytes must be recorded in execution metadata.
* **Hard Stop:** Open-ended polling or indefinite retries are prohibited.

---

## 22. Production Boundary and Stratification

* **Multi-Resolution Staging:** DAYTRADE-001 tests the 1-minute statistical reversal effect in isolation. If supported, separate future specifications will test whether 133-tick context improves setup quality and whether 50-tick data improves entry timing.
* **Production Invariant:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains true. No automated trading, strategy registry modifications, or user-facing screener changes may result from this study.
