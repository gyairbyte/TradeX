# DAYTRADE-002A: Early-to-Late Intraday Momentum Research Specification

This document is the human-readable research contract and preregistration specification for `DAYTRADE-002A`. The canonical, machine-readable locked specification is [`docs/research/specs/DAYTRADE-002A-v1.json`](./specs/DAYTRADE-002A-v1.json). Any future execution, study artifacts, or analysis must reference this specification, its SHA-256, and its base commit.

* **Task ID:** `DAYTRADE-002A`
* **Classification:** Research-only / preregistration (zero production impact)
* **Status:** `preregistered_not_executed`
* **Spec Version:** `1`
* **JSON SHA-256:** `dfad19dc6c88a009e05ef4a42a8b7ad9c64838ca84cdfd64a830a7f70f127127`
* **Base Commit SHA:** `0a0805fd918bb7a45bb46d29d8c3470ce0c6bf27`

> [!IMPORTANT]
> **Zero Network / Zero Execution Invariant:**
> This specification PR performs **zero market-data requests**, contacts no external APIs, does not construct datasets, does not implement an evaluator, and evaluates no historical returns. It strictly locks the hypothesis, methodology, data contract, parameters, statistical tests, validation gates, and holdout conditions prior to any data observation.
> Future evaluator implementation (`DAYTRADE-002B` or equivalent) and study execution remain unauthorized until this specification is reviewed and merged.

---

## 1. Status, Authority, and Scope

`DAYTRADE-002A` is an authorized research-design specification defining a new day-trading hypothesis following the completion of the `DAYTRADE-001` program.

* **No Production Changes:** This specification alters no production code, scorers, indicators, weights, thresholds, alerts, candidate persistence, Journal logic, or dashboard surfaces.
* **Registry Invariant:** `APPROVED_PRODUCTION_STRATEGIES == ()` remains strictly preserved in `tradex/strategies/registry.py`.
* **No Automatic Promotion:** Even if future validation and holdout phases pass every gate, this study cannot authorize production promotion directly (`production_promotion_eligible = false`).
* **Multi-Resolution Boundary:** This study tests exclusively whether the **1-minute ETF statistical phenomenon exists** across regular trading sessions. Neither 133-tick nor 50-tick data acquisition is authorized.
* **No Evaluator Implementation:** This assignment specifies the research contract only. Evaluator construction (`DAYTRADE-002B` or equivalent) is explicitly out of scope.

---

## 2. Objective and Falsifiable Hypothesis

The goal of this study is to preregister a rigorous, falsifiable event-study test for a new DAYTRADE hypothesis:

> **Hypothesis:** Among a frozen universe of highly liquid U.S. market and sector ETFs, an unusually strong first-half-hour directional move predicts a same-direction return during the final half-hour of the same regular trading session that remains positive after realistic execution friction and exceeds comparable non-event sessions.

### Key Study Characterization
* **Study Type:** `event_study`.
* **Not an Executable Backtest:** This study evaluates unconditional forward return distributions across the final half-hour following qualified first-half-hour moves. It does not model portfolio capital allocation, leverage, simultaneous trade capacity constraints, or dynamic intraday stop-loss management.
* **Simultaneous Events:** Because all executions occur during the identical final half-hour (15:30 open to 15:59 close), multiple ETFs on a given day naturally generate simultaneous events. Cross-ETF events are permitted, fully tracked, and explicitly reported without suppression.
* **Acceptable Outcomes:** A finding of `rejected`, `inconclusive`, or `invalid` is scientifically valid and fully acceptable. The protocol is designed to eliminate post-hoc optimization and confirmation bias.

---

## 3. Why This Is a New Hypothesis & Mandatory Disclosures

`DAYTRADE-001` evaluated an entirely different hypothesis:
```text
extreme negative completed 1-minute move
→ enter long next minute
→ expect immediate short-horizon reversal
```
That candidate did not establish empirical support:
* Development split: `rejected` (Step 3: negative mean net return, negative uplift, only 6.67% positive tickers);
* Validation split: `inconclusive` (Step 2: data-quality exclusion rate 7.83% exceeded 5.0% tolerance);
* Holdout split: `unread_not_acquired` (correctly sealed and unacquired).

`DAYTRADE-002` must **not** be described as a tuned, tweaked, or inverted version of `DAYTRADE-001`.

The new hypothesis concerns:
```text
strong first-half-hour directional information (09:30–10:00 ET)
→ 5.5-hour information gap (10:00–15:30 ET)
→ final-half-hour same-direction continuation (15:30–16:00 ET)
```

This differs fundamentally in:
1. **Signal Horizon:** 30-minute cumulative move incorporating overnight/opening information vs. 1-minute acute price dislocation.
2. **Execution Horizon:** Final half-hour (15:30 open to 15:59 close; 29 minutes) vs. immediate next-minute open to next-minute close.
3. **Universe:** 15 highly liquid U.S. broad-market and SPDR sector ETFs vs. 30 Dow Jones Industrial Average single-stock equities.
4. **Timing:** 10:00 ET signal availability followed by a 5.5-hour information gap before 15:30 ET entry vs. immediate next-bar execution.
5. **Economic Mechanism:** Institutional information diffusion, portfolio hedging flow, and end-of-day rebalancing continuation vs. temporary order-book liquidity shock bounce.
6. **Holding Period:** 29 minutes vs. 1 minute.
7. **Dataset Period:** Fresh 2026 observations vs. 2025 observations.

### Mandatory Hypothesis-Generation Disclosure
> [!IMPORTANT]
> **Hypothesis-Generation Disclosure:**
> DAYTRADE-002 was conceived after DAYTRADE-001 results were known.
> Therefore:
> - DAYTRADE-001 results serve as hypothesis-generating context only;
> - **None of the 2025 DAYTRADE-001 development, validation, or holdout observations may serve as confirmatory evidence for DAYTRADE-002;**
> - The confirmatory DAYTRADE-002 period is fresh 2026 data (`2026-01-02` through `2026-08-31`);
> - No outcome, parameter, or threshold from DAYTRADE-001 determines a DAYTRADE-002 threshold or parameter.

---

## 4. Literature Motivation

The specification cites the following academic literature as motivation only, not as proof that TradeX will reproduce the findings:

1. **Gao, Han, Li & Zhou — *Market Intraday Momentum***  
   *Journal of Financial Economics*, 2018. DOI: [`10.1016/j.jfineco.2018.05.009`](https://doi.org/10.1016/j.jfineco.2018.05.009)  
   Reports empirical evidence that the first half-hour market return predicts the last half-hour return, including among heavily traded index and sector ETFs, with stronger predictability on high-volume and high-volatility days.
2. **Heston, Korajczyk & Sadka — *Intraday Patterns in the Cross-section of Stock Returns***  
   *Journal of Finance*, 2010. DOI: [`10.1111/j.1540-6261.2010.01573.x`](https://doi.org/10.1111/j.1540-6261.2010.01573.x)  
   Documents persistent intraday return continuation patterns across regular trading intervals while demonstrating that ultra-short-horizon reversals often reflect bid-ask bounce and transient liquidity provision.
3. **Rosa — *Understanding Intraday Momentum Strategies***  
   *Journal of Futures Markets*, 2022. DOI: [`10.1002/fut.22375`](https://doi.org/10.1002/fut.22375)  
   Shows that certain documented intraday momentum anomalies attenuate or disappear out-of-sample and emphasizes strict dependency on market regime, execution costs, and signal specification.

These sources motivate strict out-of-sample validation and conservative friction modeling rather than weaker promotion gates.

---

## 5. Frozen Universe

### 5.1 Universe Specification
The universe is locked to the 15 liquid ETFs in the repository preset:
`tradex.watchlists.presets.SECTOR_ETFS`

The exact frozen constituent list is:
```text
XLK, XLV, XLF, XLY, XLP, XLE, XLI, XLB, XLU, XLRE, XLC, SPY, QQQ, IWM, DIA
```
* **Universe Size:** Exactly 15 symbols.
* **Snapshot Vintage:** May 2026 (`2026-05`).
* **Reconstitution Policy:** Frozen static snapshot; no dynamic refresh during reproducible studies.
* **Research Source of Truth:** The JSON symbol list is the research source of truth. The source preset provides provenance only. Specification validity does not depend on future runtime preset values.
* **Universe Rationale:** Deep liquidity, continuous quoting, minimal bid-ask spread friction, and absence of single-stock corporate earnings shocks.

---

## 6. Proposed Future Data Contract

Future execution must conform to the following locked data contract:

| Dimension | Locked Specification |
|---|---|
| **Provider** | Alpaca Market Data API (`alpaca`) |
| **Feed** | `sip` (Securities Information Processor consolidated tape) |
| **Timeframe** | `1Min` (1-minute bars) |
| **Adjustment Policy** | `split` (split-adjusted only; cash dividends excluded from intraday prices) |
| **Calendar & Sessions** | `XNYS` regular trading sessions only (09:30–16:00 ET) |
| **Timezone** | `America/New_York` |

### Provider and Storage Constraints
1. **No Fallback Allowed:** If the locked `sip` feed cannot be accessed, the execution engine must halt closed and record a provider/entitlement blocker. Silent fallback to `iex`, `yahoo`, `schwab`, `ibkr`, or any other feed is strictly prohibited.
2. **Git Storage Prohibited:** Raw market data files must never be committed to Git.
3. **Storage Location:** Future raw and processed datasets must reside outside the tracked repository tree, under `~/.tradex/research/daytrade_002a/` or an explicitly configured external path.
4. **Zero Provider Calls in DAYTRADE-002A:** This task makes zero provider requests.

---

## 7. Date Coverage, Partitions, and Session Adjacency

The confirmatory study spans eight calendar months of 2026, preceded by an end-of-2025 context anchor:

```
[ Context Anchor: 2025-12-31 ]  (Supplies prior regular-session close for 2026-01-02 signal)
       ↓
[ Warmup: 2026-01-02 -> 2026-01-30 ]  (Threshold history only; zero signals, events, or outcomes)
       ↓
[ Development: 2026-02-02 -> 2026-04-30 ]  (Diagnostic only; parameters locked)
       ↓
[ Validation: 2026-05-01 -> 2026-06-30 ]   (Formal preregistered gate evaluation)
       ↓ (Conditional on Validation == 'supported')
[ Holdout: 2026-07-01 -> 2026-08-31 ]      (Untouched final evaluation)
```

### Partition Governance Rules
* **Context Anchor:** `2025-12-31`. Context only. Solely supplies the previous-session close for the first 2026 first-half-hour return. It must never generate an event, baseline observation, or outcome.
* **Warmup:** `2026-01-02` through `2026-01-30`. Used solely to build the rolling 20-valid-session signal threshold history. Zero warmup observations may generate events, enter baselines, or enter development metrics.
* **Development:** `2026-02-02` through `2026-04-30`. Diagnostic only. All study parameters remain locked.
* **Validation:** `2026-05-01` through `2026-06-30`. Formal preregistered gate evaluation.
* **Holdout:** `2026-07-01` through `2026-08-31`. Completely unread, unparsed, unacquired, and uninspected unless validation earns exactly `supported`.
* **Current Month Exclusion:** September 2026 is excluded because the month is incomplete.
* **Session Adjacency:** Partition boundaries are exchange-session aware under the `XNYS` calendar. Non-trading days (exchange holidays such as New Year's Day 2026-01-01 and calendar weekends such as 2026-01-31 / 2026-02-01) intervene between civil dates without violating session adjacency.
* **Split Boundary Integrity:** All events and forward outcomes must remain strictly inside their target split.

---

## 8. First-Half-Hour Signal Return

For ticker $i$ on regular session $D$:
$$\text{first\_half\_hour\_return}(i, D) = \frac{\text{close}(i, D, \text{09:59 bar})}{\text{close}(i, \text{previous\_regular\_session}, \text{15:59 bar})} - 1$$

### Implementation Semantics
1. **Previous Regular-Session Close:** Close of the 15:59 one-minute bar (interval `[15:59:00, 16:00:00)` ET) from the immediately preceding valid regular session. It is the minute-bar close, not assumed to equal the official closing-auction or daily close.
2. **Current-Session 09:59 Bar:** Close of the 1-minute bar starting at 09:59:00 ET and ending at 10:00:00 ET (`[09:59:00, 10:00:00)` ET).
3. **Information Captured:** Incorporates overnight gap information, opening auction discovery, and the first 30 minutes of continuous trading, consistent with the literature-motivated signal.
4. **Availability:** The signal is fully known at **10:00:00 ET**.
5. **Prohibited Information:**
   * Bars timestamped 10:00:00 ET or later;
   * Current-session future volume;
   * Current-session final-half-hour data;
   * Revised end-of-day information.

---

## 9. Signal Strength Threshold

For each ticker $i$ and regular session $D$:
$$\text{abs\_threshold}(i, D) = \text{80th percentile of } |\text{first\_half\_hour\_return}| \text{ from previous 20 valid completed sessions}$$

### Implementation Lock
```python
numpy.quantile(history, q=0.80, method="linear")
```

### History Rules
* **Exact Window:** Exactly the previous 20 valid completed regular trading sessions for that ticker.
* **Exclusions:** Current session $D$ is excluded; future sessions are excluded.
* **Data-Quality Exclusions:** Ticker-sessions excluded by locked data-quality rules do not count toward the 20 valid sessions.
* **Calendar Days Prohibited:** Civil calendar days cannot substitute for valid trading sessions.
* **No Parameter Search:** No alternative percentiles (e.g., 70th, 85th, 90th), lookback windows (e.g., 10, 30, 60 sessions), or return definitions may be evaluated.

---

## 10. Event Definition and Direction

A ticker-session $(i, D)$ is classified as an event when:
$$|\text{first\_half\_hour\_return}(i, D)| \ge \text{abs\_threshold}(i, D) \quad \text{and} \quad \text{first\_half\_hour\_return}(i, D) \neq 0$$

### Direction Assignment
* **LONG Event:** $\text{first\_half\_hour\_return}(i, D) > 0$
* **SHORT Event:** $\text{first\_half\_hour\_return}(i, D) < 0$

### Symmetry
This is a single symmetric directional hypothesis.
* Long and short sides are not optimized separately.
* Long and short sub-cohorts are reported separately as diagnostics, but the preregistered primary endpoint evaluates all qualifying signed events pooled together.

---

## 11. Information Timing and Execution Assurances

Strict point-in-time discipline governs the information timeline:

```
09:30 ET       10:00 ET                                15:30 ET               16:00 ET
  |---------------|---------------------------------------|----------------------|
    Signal Window          5.5-Hour Information Gap          Outcome Window
    (09:30–10:00)           (No Action / No Rules)           (15:30–16:00)
                  ▲                                       ▲                      ▲
           Signal Available                             Entry                  Exit
              (10:00 ET)                             (15:30 Open)           (15:59 Close)
```

1. **Signal Availability:** Available at **10:00:00 ET**. No trade occurs at 10:00 ET.
2. **Intentional Information Gap:** A 5.5-hour gap elapses between signal detection and execution. The strategy specifically tests whether the early directional information persists into the final half-hour.
3. **Prohibition on Intervening Information:** No price, volume, VWAP, volatility, or headline information between 10:00 ET and 15:30 ET may be used to alter event eligibility, direction, entry eligibility, or sizing.
4. **Entry Timing:** Open of the 15:30 bar (15:30:00 ET).
5. **Exit Timing:** Close of the 15:59 bar. The 15:59 bar close is the closing price of the one-minute interval `[15:59:00, 16:00:00)`; it is not assumed to equal the official closing-auction or daily close.
6. **Locked Execution Assumptions:**
   * `stop_loss = none`
   * `take_profit = none`
   * `intraday_position_only = true`
   * `same_bar_entry_allowed = false`
   * `entry_after_signal = true`
   * `position_crosses_session_boundary = false`
   * `official_closing_auction_price_used = false`

---

## 12. Primary Outcome Return

The trading window spans the final 29 minutes of the regular session:
$$\text{Interval: } 15:30\text{ open} \longrightarrow 15:59\text{ close}$$

* **Minute-Bar Close Reference:** The 15:59 minute-bar close is the locked exit reference (`[15:59:00, 16:00:00)` ET). The official closing auction price is not used (`official_closing_auction_price_used = false`).

### Gross Signed Return
* For **LONG** events:
  $$\text{gross\_signed\_return} = \frac{\text{exit\_price}}{\text{entry\_price}} - 1$$
* For **SHORT** events:
  $$\text{gross\_signed\_return} = 1 - \frac{\text{exit\_price}}{\text{entry\_price}}$$
* Equivalent algebraic representation:
  $$\text{gross\_signed\_return} = \text{sign} \times \left(\frac{\text{exit\_price}}{\text{entry\_price}} - 1\right)$$
  where $\text{sign} = +1$ for LONG and $-1$ for SHORT.
* **Boundary Rule:** Fills and exits must not cross the 16:00:00 regular-session boundary.

---

## 13. Execution Friction Assumptions

All net performance metrics incorporate realistic execution friction:

* **Primary Friction Assumption:** `2.0 basis points per side` ($0.02\%$ per side, or $4.0\text{ bps}$ round-trip).
  $$\text{net\_return} = \text{gross\_signed\_return} - 0.0004$$
* **Sensitivity Scenarios:**
  * Zero-cost baseline: `0.0 bps per side` ($0.0\text{ bps}$ round-trip).
  * Stressed friction: `5.0 bps per side` ($10.0\text{ bps}$ round-trip).
* **Commissions:** Zero additional commissions beyond the fixed friction model.
* **No Post-Hoc Tuning:** Cost models must not be altered after viewing results.

---

## 14. Matched Baseline and Control Methodology

The baseline tests whether **unusually strong** early moves add predictive value beyond ordinary same-direction sessions.

### 14.1 Eligible Baseline Observations
For each event observation, qualifying baseline observations must strictly satisfy:
* **Same Ticker:** Drawn from the same ETF.
* **Same Dataset Split:** Drawn from the identical split partition.
* **Same Direction:** Same first-half-hour sign ($\text{return} > 0$ for long events; $\text{return} < 0$ for short events).
* **Non-Event Sessions:** $|\text{first\_half\_hour\_return}| < \text{abs\_threshold}$.
* **Valid Regular Session:** Non-early-close session meeting all data-quality requirements.
* **Complete Required Timestamps:** All four required timestamps present.
* **Same Execution Interval:** Measured across the identical 15:30 open to 15:59 close window.
* **Same Friction:** Deducts identical friction (e.g., 2 bps/side).

### 14.2 Uplift Mechanics
* **Baseline Reference Return:** Arithmetic mean of all qualifying matched non-event signed net returns for that ticker/direction/split:
  $$\bar{R}_{\text{baseline}}(i, \text{dir}, \text{split})$$
* **Event Uplift:**
  $$\text{uplift} = \text{net\_return}_{\text{event}} - \bar{R}_{\text{baseline}}$$
* **Non-Computable Rule:** If no qualifying baseline observations exist for a ticker/direction cell, baseline and uplift are labeled `non_computable`. Zero must never be substituted.

---

## 15. Data-Quality Requirements

Normal NYSE sessions expect 390 completed 1-minute bars (09:30–16:00 ET).

### Per Ticker-Session Audit
1. **Timestamp Normalization:** Timestamps parsed to aware `America/New_York` datetimes; malformed timestamps removed and recorded.
2. **Candle Validity:** Finite numeric values; $\text{open}, \text{high}, \text{low}, \text{close} > 0$; $\text{volume} \ge 0$.
3. **Duplicate Bars:** Counted and removed.
4. **No Synthetic Bars:** Interpolation and synthetic filling are prohibited.
5. **Ticker-Session Exclusion Rules:**
   $$\text{missing\_bar\_rate} > 5.0\% \quad \text{OR} \quad \text{duplicate\_bar\_rate} > 1.0\%$$
6. **Required Execution/Signal Timestamps:** A ticker-session is ineligible if any of the following four timestamps is absent after cleaning:
   * Previous-session 15:59 close;
   * Current-session 09:59 close;
   * Current-session 15:30 open;
   * Current-session 15:59 close.
7. **Early-Close Sessions:** Excluded in their entirety.
8. **Split Data-Quality Gate:** If $> 5.0\%$ of ticker-sessions in a split are excluded, the split cannot earn `supported`.

---

## 16. Point-in-Time Split Integrity

* **Warmup:** Warmup observations may only build threshold history; zero events, baselines, or performance metrics may originate from warmup.
* **Development History:** Historical valid development sessions may supply threshold history to later development sessions and early validation sessions.
* **Validation Separation:** Development observations may **not** enter validation event counts, baselines, or performance metrics.
* **Holdout Separation:** If holdout is authorized, validation sessions may provide threshold history, but validation observations cannot enter holdout event counts, baselines, or metrics.
* **Target Split Containment:** All outcomes must remain strictly inside their target split.

---

## 17. Overlap and Cross-Sectional Multiplicity

Because all executions occur during the identical final half-hour, cross-ETF events on a given session date are naturally simultaneous.
* Cross-ETF simultaneous events are not suppressed.
* Descriptive reporting includes:
  * Events per session;
  * Fraction of event sessions with multiple ETF signals (`multi_signal_session_rate`);
  * Total long events and short events.

---

## 18. Statistical Inference & Session-Clustered Bootstrap

To account for cross-sectional dependence among ETFs driven by common market shocks on the same trading day:

### 18.1 Algorithm
For each bootstrap replication $b = 1, \dots, 2000$:
1. **Cluster Resampling:** Resample eligible target-split **session dates** with replacement.
2. **Observation Retention:** Preserve all ticker observations from each sampled session date.
3. **Multiplicity Preservation:** Preserve multiplicity when a date is sampled more than once.
4. **Event Recomputation:** Recompute the primary mean event net return ($R_{\text{event}, b}$).
5. **Baseline Recomputation:** Recompute the matched non-event baseline using the resampled observations ($R_{\text{baseline}, b}$).
6. **Uplift Recomputation:** Recompute the event-minus-baseline uplift ($\Delta_b = R_{\text{event}, b} - R_{\text{baseline}, b}$).

### 18.2 Inference Parameters
* **Cluster Variable:** `session_date` (NOT ticker-session; accounting for ETF market-wide co-movement).
* **Resample Count:** `2,000` bootstrap replications.
* **Deterministic Seed:** `20260926`.
* **Confidence Level:** Two-sided `95%` percentile bootstrap confidence intervals.
* **Joint Uncertainty:** Matched baseline is recomputed jointly in each replicate; baseline is never held fixed.
* **Non-Computable Rule:** If a required replicate statistic is non-computable, the entire relevant CI status is `non_computable`. Do not drop replicates; do not substitute zero; do not reduce the denominator.

---

## 19. Required Metrics

Future execution reports across development, validation, and holdout must present at minimum:

### Sample and Coverage
1. `eligible_ticker_session_count`
2. `event_count`
3. `represented_etf_count`
4. `event_session_count` (distinct event session dates)
5. `events_per_etf`
6. `events_per_month`
7. `long_event_count`
8. `short_event_count`
9. `maximum_single_etf_event_concentration` (%)
10. `multi_signal_session_count`
11. `multi_signal_session_rate` (%)

### Return Distributions
12. `mean_gross_signed_return_30m`
13. `median_gross_signed_return_30m`
14. `win_rate_gross_30m` (%)
15. `mean_net_signed_return_0bps`
16. `mean_net_signed_return_2bps` (primary)
17. `mean_net_signed_return_5bps` (stressed)
18. `median_net_signed_return_0bps`
19. `median_net_signed_return_2bps`
20. `median_net_signed_return_5bps`

### Matched Baseline & Uplift
21. `matched_non_event_baseline_mean`
22. `matched_non_event_baseline_median`
23. `event_minus_baseline_mean`
24. `event_minus_baseline_median`

### Cross-Sectional Diagnostics
25. `per_etf_primary_results`
26. `per_month_primary_results`
27. `long_side_primary_results`
28. `short_side_primary_results`

### Integrity Audits
29. `data_quality_summary` (missing, duplicate, malformed, excluded counts)
30. `provider_provenance_summary` (requests, pages, retries, timestamps)

---

## 20. Validation Success Gates

Validation can earn the disposition **`supported`** only if **all six** locked gates pass simultaneously:

| Gate | Criterion | Threshold |
|---|---|---|
| **1. Sample Gate** | Event count, ETF breadth, and session breadth | $\ge 75\text{ events}$ across $\ge 10\text{ ETFs}$ and $\ge 20\text{ distinct event session dates}$ |
| **2. Concentration Gate** | Maximum single-ETF contribution | No single ETF $> 15.0\%$ of all validation events |
| **3. Data-Quality Gate** | Ticker-session exclusion rate | $\le 5.0\%$ excluded sessions in validation split |
| **4. Primary Net-Effect Gate** | Mean 30m net return (2 bps/side) | Mean $> 0$ **and** 95% Session-Clustered CI lower bound $> 0$ |
| **5. Baseline-Uplift Gate** | Mean 30m event-minus-baseline return | Mean $> 0$ **and** 95% Session-Clustered CI lower bound $> 0$ |
| **6. Cross-ETF Breadth Gate** | Cross-sectional consistency | $\ge 60.0\%$ of represented ETFs have positive primary mean net return |

*Note: Long vs. short sub-cohort differences are diagnostic only for this first preregistration; no separate long/short gates exist.*

---

## 21. Deterministic 5-Step Disposition Precedence

To eliminate ambiguity, study dispositions follow a strict 5-step decision sequence:

### Step 1 — Invalidity (`invalid`)
Return **`invalid`** if any methodological or data-integrity defect occurs:
* Lookahead bias or future-bar leakage;
* Premature holdout unsealing or inspection;
* Material timestamp or execution invalidity;
* Split contamination (outcomes crossing split boundaries);
* Silent provider or feed substitution;
* Corrupt, missing provenance, or unverifiable inputs.

### Step 2 — Evidence Sufficiency Failure (`inconclusive`)
Return **`inconclusive`** if otherwise valid, but any evidence-sufficiency condition fails:
* Fewer than 75 eligible events;
* Fewer than 10 represented ETFs;
* Fewer than 20 distinct event session dates (`event_session_count < 20`);
* Single-ETF event concentration $> 15.0\%$;
* $> 5.0\%$ of ticker-sessions in the split excluded due to locked data-quality defects.
* *Rule:* If evidence sufficiency fails, **do not inspect holdout**.

### Step 3 — Directional Hypothesis Failure (`rejected`)
With valid and sufficient evidence, return **`rejected`** if any directional failure occurs:
* Primary mean net return at 2 bps/side $\le 0$;
* Mean event-minus-baseline uplift $\le 0$;
* Fewer than $60.0\%$ of represented ETFs have positive primary mean net return (breadth gate failure).

### Step 4 — Statistical Uncertainty (`inconclusive`)
If the required means are positive and breadth passes ($\ge 60\%$), but either required 95% CI lower bound is $\le 0$ or non-computable, return:
**`inconclusive`**  
(Specifically: primary net return 95% CI lower bound $\le 0$, OR event-minus-baseline uplift 95% CI lower bound $\le 0$, OR either CI `non_computable`).

### Step 5 — Support (`supported`)
Return **`supported`** if and only if all six locked gates pass simultaneously.

*Application:* The exact same 5-step disposition sequence applies to conditional holdout evaluation.

---

## 22. Development / Validation / Holdout Governance

* **Development Split:** Diagnostic only. No parameter, threshold, universe, cost, or methodology modifications are permitted after viewing development.
* **Validation Split:** Formal one-time preregistered evaluation gate. No reruns seeking a different outcome.
* **Holdout Split:** May not be acquired, parsed, inspected, or evaluated unless validation earns exactly:
  `supported`  
  If validation resolves to `rejected`, `inconclusive`, or `invalid`, holdout remains:
  `unread_not_acquired`

---

## 23. Evidence-Confidence Cap

Any future evidence from this initial bounded study is strictly capped at:
$$\text{maximum\_evidence\_confidence} = \text{limited\_but\_usable\_evidence}$$

Reasons:
1. Finite 15-ETF universe;
2. Single 2026 market regime;
3. Hypothesis chosen after prior DAYTRADE research;
4. Absence of multi-year independent out-of-sample replication.

Even a supported validation and holdout would not prove durable alpha.

---

## 24. Production Boundary Invariant

This specification represents research only:
* `tradex/strategies/registry.py` must retain:
  `APPROVED_PRODUCTION_STRATEGIES == ()`
* No modifications to production scorers, signals, weights, thresholds, rankings, eligibility, alerts, dashboard trading behavior, or Journal persistence.
* Zero automatic promotion.

---

## 25. Explicit Out of Scope

The following items are explicitly prohibited in this task and primary contract:
* Implementing an evaluator (`DAYTRADE-002B` or equivalent);
* Reusing or modifying the `DAYTRADE-001` reversal evaluator for momentum;
* Acquiring or downloading market data;
* Inspecting 2026 study returns;
* Executing development, validation, or holdout;
* Testing alternative percentiles (e.g., 75th, 85th), lookback windows (e.g., 10, 30 days), or return definitions;
* Adding midday or volume confirmation filters;
* Adding volatility conditioning (literature conditioning may be explored only under a future, separately preregistered hypothesis);
* Adding 133-tick or 50-tick logic;
* Changing production behavior.
