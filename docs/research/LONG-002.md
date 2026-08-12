# LONG-002: Long-only rapid-upside opportunity research program

This document is the human-readable canonical research contract for `LONG-002`.
The machine-readable locked specification is in [`docs/research/specs/LONG-002-v1.json`](./specs/LONG-002-v1.json).
Any future LONG-002 research artifact must record:

* SHA-256 of `docs/research/specs/LONG-002-v1.json`
* Code/repository commit used for the applicable study
* Dataset/manifest identity when one exists

This PR is `LONG-002A` — specification/preregistration only. No market-data
calls, historical outcome analysis, model fitting, or validation/holdout access
occurs in this PR.

---

## 1. Research classification

* **Task ID:** `LONG-002`
* **Category:** Long-term trading (rapid-upside, days-to-weeks horizon)
* **Classification:** `research-only`
* **Current phase:** `LONG-002A` — locked research/discovery contract
* **Production promotion:** Not eligible (`production_promotion_eligible = false`)
* **Production behavior:** Unchanged

`LONG-002` is **not** a continuation or retuning of `LONG-001`, and it is **not**
the same hypothesis as `INTRA-001`. `LONG-001` evaluated the existing production
long-term score against a 40-week moving-average baseline and did not authorize
production promotion. `INTRA-001` studied an opening-drive VWAP pullback
continuation on 5-minute bars and also concluded `inconclusive`.

---

## 2. Product objective

`LONG-002` researches an explainable, long-only rapid-upside opportunity system
for U.S.-listed mid-, large-, and mega-cap common stocks. At each point-in-time
decision snapshot, the eventual system will estimate the probability and
capturable potential of clean `+10%`, `+20%`, and `+30%` moves over `5`, `10`,
and `21` trading sessions from an executable entry.

Move potential, entry readiness, downside risk, data confidence, evidence
strength, candidate applicability, and explanations are distinct concepts.

The system ultimately surfaces only:

* **Enter Now**
* **Armed — next 1–5 sessions**
* **Qualified Waitlist**

Nonqualifying stocks are retained internally for research/auditability but are
not shown as a giant user-facing `Skip` list. `LONG-002` is decision support,
not automated execution.

---

## 3. Universe and eligibility

### Security universe

Primary candidates are U.S.-listed operating-company common stocks, primarily
mid-, large-, and mega-cap, deduplicated across overlapping index sources.
Index membership is a universe-construction aid, not a predictive reason.

Starting universe may draw from:

* Russell 1000
* S&P 500
* S&P MidCap 400
* DJIA
* Other qualifying liquid U.S. common stocks

ETFs/ETNs are not primary stock candidates; they may be used for benchmarks,
sector/market context, and robustness analysis.

### Exclusions

Excluded security types and structures include: OTC securities; warrants;
rights; units; preferred stock; ETNs; closed-end funds; pre-merger SPACs and
shell companies; non-operating-company shells; and other structurally
incomparable securities.

### Point-in-time constituent policy

Index membership is a universe-construction aid, not a predictive reason. Use
the best available reliable point-in-time index/constituent membership. Perfect
historical constituent history is not a hard blocker if it is genuinely
unavailable, but any survivorship or constituent-history limitation must be
documented and never used as a modeling feature. Never substitute current
membership as historical fact.

### Market capitalization

* Non-index point-in-time market-cap floor: **$3 billion**
* Verified point-in-time Russell 1000, S&P MidCap 400, S&P 500, or DJIA
  membership may allow eligibility below $3B, provided all other rules pass.
* Development-only sensitivity floors: **$3B, $5B, $7B**
* The default remains $3B unless a later properly controlled research amendment
  changes it.

Suggested reporting cohorts: $3B–<$5B, $5B–<$20B, $20B–<$200B, $200B+.

### Price and liquidity

* Current as-traded close: **≥ $5**
* 20-session median as-traded close: **≥ $5**
* 20-session median dollar volume: **≥ $20M**
* 60-session median dollar volume: **≥ $10M**
* Development sensitivity for the 20-session floor: **$10M, $20M, $50M**

Use dollar volume as the primary historical liquidity gate.

### Trading history

* Established-stock cohort: at least **252 completed sessions**
* Recent-IPO cohort: at least **63 completed sessions** and up to **251**
* Features requiring longer history remain unavailable rather than fabricated

### Fundamental cohort

* Full cohort: at least **6 reported quarters**, **8 preferred**
* Recent-IPO cohort: at least **2 reported quarters**
* Latest expected periodic filing must not be overdue
* Most recent filing normally no more than **120 calendar days old**
* Missing/inapplicable financial facts remain `null` with applicability
  metadata; never replace them with zero.

### Daily-bar integrity

For established stocks:

* Most recent 20 expected sessions: 100% observed except verified halts/suspensions
* Trailing-year completeness: at least 99%
* Maximum two unexplained missing sessions across the trailing 252 expected sessions
* Maximum one unexplained consecutive missing session
* Zero unresolved duplicate timestamps
* Zero unresolved malformed/invalid OHLCV rows
* Positive prices, nonnegative volume, internally valid OHLC relationships
* Sorted, unique normalized timestamps

A verified trading halt is distinct from provider-missing data and must be
represented separately.

### Live execution gates (not historical eligibility gates unless genuine PIT
quote data exists)

* Preferred spread: **≤ 0.25%**
* Maximum spread for Enter Now / Armed: **≤ 0.50%**
* Preferred reference-position participation: **≤ 0.10%** of median daily dollar volume
* Maximum reference-position participation: **≤ 0.25%**
* Reference-position notionals for execution diagnostics: approximately **$10,000–$20,000**

Actual position sizing remains user-controlled and external to the predictive
ranking model. The `$10K–$20K` figures are reference notionals for liquidity
and execution diagnostics, not a recommendation or predictive feature.

### Ordinary earnings risk

A non-earnings setup may not be Enter Now or Armed when scheduled earnings are
within the next **5 trading sessions**, but only when that schedule was known
point-in-time. It may remain Waitlist if otherwise qualified. Pre-earnings
speculation requires separate research.

---

## 4. Identity and point-in-time rules

Require both issuer-level identity (e.g., CIK) and stable security/share-class
identity when available. Historical tickers map to immutable identities.

For sector-relative features, use a classification valid at the historical
decision timestamp. Current sector classifications may be descriptive only if
point-in-time history is unavailable; do not silently backfill current
classifications into historical predictive features.

Historical market capitalization must be point-in-time. Preferred hierarchy:

1. Reliable historical market cap
2. Latest known point-in-time shares outstanding × actual historical close
3. Otherwise, the stock cannot use the non-index $3B eligibility pathway

Do not use today's market cap or today's share count for historical eligibility.

---

## 5. Price and corporate-action representations

### As-traded series

Used for share-price eligibility, dollar-volume eligibility,
reference/actual entry, gap behavior, and execution diagnostics.

### Split-normalized, dividend-unadjusted analytical series

Used for technical calculations, historical returns spanning splits, moving
averages, relative strength, and MFE/MAE across split boundaries. `LONG-002`
researches price moves, not long-horizon total return.

### Corporate-action metadata

Retain splits, ordinary dividends, special dividends, spin-offs, rights
distributions, mergers, and other material transformations. If a special
distribution/spin-off cannot be reconstructed correctly, affected forward-return
labels must be excluded rather than interpreted as genuine market moves.

---

## 6. Official decision cadence

Use the accepted ADR-0001 market timezone (`America/New_York`) and XNYS
calendar.

### Evening snapshot (primary research/ranking snapshot)

**8:30 p.m. America/New_York**

It may use only information available by that timestamp. The evening research
population is the primary initial discovery population. An evening immediately
actionable result is internally `enter_next_session_provisional`, not an already
executable live position.

### Pre-market snapshot

**9:00 a.m. America/New_York**

Reevaluates the eligible universe using overnight information and may add,
upgrade, downgrade, or remove candidates. The morning snapshot may convert a
provisional evening entry into `enter_now`.

### Intraday

`LONG-002` does not continuously rerank the universe intraday. Intraday
processing is limited to previously defined execution/risk events (Armed
trigger, stop, target, gap/entry validity, and approved material-event checks).
Continuous intraday opportunity discovery belongs to `DAYTRADE-001`.

---

## 7. Historical periods

| Split | Start | End |
|---|---|---|
| Warm-up | 2015-01-01 | 2015-12-31 |
| Development | 2016-01-01 | 2020-12-31 |
| Validation | 2021-01-01 | 2022-12-31 |
| Holdout | 2023-01-01 | 2025-12-31 |
| Shadow/replay | 2026-01-01 onward | separate from holdout |

All model selection is chronological. No random train/test split. An
observation may belong to a split only if its full potential five-session entry
window and full 21-session forward outcome window remain within that split. Use
the exchange calendar; the maximum boundary purge is conceptually five trigger
sessions plus 21 outcome sessions. Do not inspect holdout outcomes before
authorized holdout access.

---

## 8. Outcome and entry contract

### Evening discovery reference

Signal known after the official evening information cutoff. Reference entry is
the actual next regular-session open plus applicable modeled entry friction. No
use of the future day's low, best first-hour price, retrospectively selected
VWAP, or other hindsight-optimized entry.

### Armed entries

* Use the first historically executable occurrence of the frozen trigger.
* Trigger valid for a maximum of **5 trading sessions**.
* If never triggered, record expiration; do not count it as a trade win/loss.
* If price gaps beyond the frozen acceptable entry band, record
  `gapped_beyond_entry`; do not assume a fictitious trigger-price fill.

### Waitlist

No active outcome/trade clock. It must first become Armed or Enter Now and
produce an executable entry.

### Target grid

Always calculate all nine:

* +10% within 5, 10, and 21 sessions
* +20% within 5, 10, and 21 sessions
* +30% within 5, 10, and 21 sessions

### Confirmatory hierarchy

| Role | Target |
|---|---|
| Primary | clean +10% within 10 sessions |
| Key magnitude secondary | clean +20% within 21 sessions |
| Speed secondary | clean +10% within 5 sessions |
| Stretch | clean +30% within 21 sessions |

All nine remain available diagnostically. One predefined feasibility fallback
is allowed: clean +10% within 21 sessions. The fallback may be invoked only by a
label-only development census showing that the primary +10%/10 endpoint lacks
the preregistered independent-event sample required for meaningful evaluation.
It must occur before KPI/model discovery and may not depend on predictive model
performance.

---

## 9. Gross moves versus net economics

The `+10/+20/+30` target labels remain **gross market-price move labels** from
an executable market reference. Separately retain net capturable economics after
modeled execution friction.

Primary generic historical friction: **10 bps per side**. Sensitivities: **5 bps**
and **25 bps per side**. Stress diagnostic for applicable event-driven/
lower-liquidity cohorts: **50 bps per side**. Treat these as all-in modeled
execution friction rather than pretending to know exact historical spread/
slippage decomposition where quote-level PIT data is unavailable. Historical
quote spreads must not be fabricated.

---

## 10. Outcome-quality taxonomy

Do not force every observation into one exclusive winner/loser bucket. For each
target/horizon retain at least:

* `target_reached`
* `target_progress_ratio`
* `near_miss`
* `partial_move`
* `mae_pct`
* `mae_atr`
* `adverse_excursion`
* `clean_target_reached`
* `path_sequence_ambiguous`
* `end_of_horizon_return`
* `retention_ratio`
* `sustained_target`
* `time_to_target`
* `time_to_mae`

### Target progress

`target_progress_ratio = MFE / target`

* ≥1.00: target reached
* 0.80–<1.00: near miss
* 0.50–<0.80: partial move
* <0.50: did not approach target

### Adverse excursion

Research comparison barrier: `max(5%, 1.5 × pre-entry ATR as % of entry)`. This
is an outcome-quality label, not the final stop-loss rule.

### Clean target

Allowable pre-target adverse movement: `min(target / 2, adverse_barrier)`. A
clean target requires executable/valid entry, target reached, pre-target MAE no
worse than the clean-risk cap, and no unresolved same-bar sequencing ambiguity.

### Same-bar ambiguity

If daily data touches both the relevant target and the downside barrier and
order cannot be known, set `path_sequence_ambiguous=true`; it may still be a
gross target touch but cannot count as a clean target reach.

### Persistence

`sustained_target` when target reached and end-of-horizon return is at least
50% of the target magnitude. Persistence is separate from target attainment.

---

## 11. Master opportunity episodes

Daily observations remain the canonical unit for ranking/probability research.
To avoid treating adjacent dates in the same rally as independent events, also
construct deterministic master episodes:

* Anchor on the earliest currently unassigned observation for a stock that
  reaches at least +10% within 21 trading sessions from the next-open reference
  entry.
* Keep the episode open for a fixed 21-session evaluation window.
* Do not close when +10% is first reached.
* Do not recursively extend the episode because later qualifying observations
  overlap.
* No new episode for that stock until the fixed window ends.
* Nested +10/+20/+30 outcomes belong to the same master episode.
* Official episode MFE, MAE, targets, and timing are measured from the first
  anchor entry.
* Preserve all constituent daily observations and tag them as `pre_target`,
  `target_session`, or `post_target`.

The master anchor is an ex-post labeling construct and must not be described as
model detection.

---

## 12. Controls

The full quantitative study must preserve natural prevalence and must not
balance winners/losers. Matched controls are for discovery/chart review/
specified comparative analyses only.

### Structural controls

Prefer matching on exact decision date, sector, and market-cap cohort.

### Capacity-matched challenge controls

May additionally match on pre-signal volatility and liquidity.

### Prohibited control matching

Do not match general controls on candidate predictive variables such as
momentum/relative strength, price structure, volume pattern, earnings, earnings
surprise, news, guidance, or fundamental acceleration.

### Exclusion rules

* A control must not be inside an active positive master episode.
* Do not reuse the exact same control observation.
* Do not repeatedly reuse one ticker within a rolling 21-session window for
  chart-review controls.
* If an honest match does not exist, record an unmatched case rather than
  forcing a bad match.

---

## 13. Blinded chart-review protocol

This is development-only hypothesis discovery.

### Pilot

**24 cases** — refine presentation/labeling workflow. Pilot cases are
permanently excluded from the main blinded sample and any human-label
performance claim.

### Main sample

**240 frozen cases:**

* 120 positive master episodes
* 40 ordinary non-movers
* 40 near-misses
* 40 adverse/trap cases

Use deterministic reproducible sampling with a recorded random seed and
immutable answer key. Positive cases should be diverse across target magnitude,
speed, development years, sectors, market-cap cohorts, earnings/non-earnings,
event/non-event, and volatility/regime. A ticker should normally appear no more
than twice. Do not force unavailable quotas.

**Stage A:** anonymized technical/market view (hide ticker, company, exact
calendar date, future bars, result, and class).

**Stage B:** add anonymized PIT fundamentals, earnings, guidance where
trustworthy, analyst revisions where qualified, news/catalyst information where
qualified, and data confidence. Preserve both Stage A and Stage B labels.

#### Frozen reviewer label schema

For each case the reviewer records:

* **Surface decision:** `surface` or `do_not_surface`.
* **Visible state if surfaced:** `Enter Now`, `Armed`, or `Qualified Waitlist`.
* **Expected target and horizon** (e.g., `+10% / 10 sessions`).
* **Qualitative confidence** on a `1–5` scale.
* **Setup archetype:** `setup_archetype`, `other`, or `unclear`.
* **Entry plan**, **trigger/zone**, **max five-session validity**, **gap handling**, and **invalidation**.
* Up to **three principal positive reasons** and the mandatory material risks/counterarguments.

Stage A and Stage B labels are preserved independently.

No per-case outcome reveal, running accuracy, or class hint until all 240 main
cases are locked. Suggested batching: 12 batches of 20 while keeping outcomes
hidden until completion. This review is for hypothesis/archetype/explanation
discovery only; it must not be used as the final calibrated model training
population.

---

## 14. Candidate KPI / data-layer contract

### Mandatory core

* Security identity
* PIT universe eligibility
* As-traded OHLCV
* Split-normalized analytical price history
* Corporate-action integrity
* Market benchmark data
* PIT sector context where valid
* Complete outcome windows
* Price/trend features
* Volume/liquidity features
* Volatility/range features
* Relative-strength/context features

### Full fundamental cohort

PIT SEC filing metadata and standardized financial facts with at least 6
reported quarters. Candidate families include revenue/EPS growth and
acceleration, margin level/change, operating income, operating cash flow,
capex/free cash flow, cash/debt, share-count change/dilution, asset growth,
return/capital measures, valuation where meaningful, filing freshness, and
post-filing/post-earnings reaction features. Use sector-aware applicability.

### Technical candidates

Transparent primitives across approved horizons: returns/momentum,
acceleration, trend/location, moving-average distance/slope, proximity to
highs/lows, consolidation/tightness, breakout proximity, ATR%, realized
volatility, volatility percentile, compression/expansion, gap behavior, relative
volume, dollar-volume trends, up/down volume behavior, and price/volume
confirmation/divergence.

### Relative strength / context

* Stock vs SPY
* Stock vs PIT sector where valid
* Cross-sectional ranks among historically eligible securities
* Relative-strength acceleration/persistence
* Sector relative strength
* Sector/market breadth where valid
* Market trend/regime
* Volatility regime
* Beta/correlation where appropriate

### Challenger layers

* Analyst estimates/revisions/consensus surprise when genuine vintage/PIT data
  is available.
* News/catalyst data only with auditable timestamp and coverage semantics.
  Missing news means unknown coverage unless the provider contract legitimately
  establishes otherwise.
* Exploratory challengers: options, short interest, insider activity,
  institutional ownership/positioning. Do not mislabel delayed/aggregate chain
  data as transaction-level institutional options flow.

### Coverage principles

Core technical/context features should target essentially complete coverage
(approximately ≥99% where applicable). Broad-universe fundamental candidates
generally require ≥80% applicable overall coverage and ≥60% within each major
applicable sector. Sector-specific fundamental candidates may remain viable with
roughly ≥80% coverage in the applicable cohort. These are research data-contract
rules, not permission to impute unavailable facts. News/analyst challengers
require auditable qualified coverage intervals. Model comparisons involving
richer data must use identical common-coverage observations. Missing data is
never silently interpreted as zero or absence.

---

## 15. Baselines and comparators

Freeze the allowed baseline family before `LONG-002` candidate-system
evaluation.

### Universe base rate

Natural target/horizon prevalence.

### Simple momentum family

* 5-session return
* 10-session return
* 20-session return
* 60-session return

### SPY-relative family

Stock return minus SPY return over 5, 10, 20, and 60 sessions. PIT
sector-relative versions may be secondary comparators where valid.

### Volatility-aware momentum family

Fixed equal-weight rank combination: 50% cross-sectional momentum percentile +
50% cross-sectional ATR%-movement-capacity percentile. Do not optimize the
50/50 weights. Use the same allowed momentum lookbacks.

### Existing TradeX long-term scorer

Run the existing production scorer exactly as it exists with fresh default
settings/weights and no `LONG-002` tuning. It is a comparator, not `LONG-002`
methodology.

### Strongest-simple-comparator rule

A dedicated baseline-only development census selects the strongest permitted
simple comparator for the applicable primary endpoint. Freeze that comparator
before candidate-system evaluation. Do not change it based on
validation/holdout. All paired comparisons use identical observations, timestamps,
fills, costs, and exclusions.

---

## 16. Ranking objective

`LONG-002` should optimize primarily for **top-of-list precision for clean,
executable moves of at least +10%, subject to explicit downside, execution,
calibration, and confidence constraints**.

Among qualified candidates, reward larger credible `+20/+30` outcomes, faster
attainment, and expected clean move value. Penalize adverse risk, execution
failure, gap-through risk, uncertainty, and insufficient applicability/support.

Candidate feature families are **hypotheses to be tested**, not assumed
predictive signals. No feature is treated as valid until it contributes to
out-of-sample model performance under the locked evaluation protocol.

### Expected clean move value

The expected clean move value is computed from mutually exclusive
highest-target tiers and capped at `+30%`:

```text
ECMV = 10% * P(highest clean tier is +10%)
     + 20% * P(highest clean tier is +20%)
     + 30% * P(highest clean tier is +30% or more)
```

A development-derived speed preference/discount is frozen before validation and
is not tuned post-hoc.

### Validation tie-break order

When comparing candidate systems on the development split, break ties in this
order:

1. Pass all risk, actionability, calibration, and sample-count gates.
2. Highest clean-target **Precision@10** (then **Precision@25** as secondary).
3. Highest expected clean move value at the same K.
4. Lower adverse rate.
5. Better calibration (lower Brier / better reliability).
6. Simpler / more explainable system when results are materially similar.

### Primary metrics

Clean-target **Precision@10/@25**, expected clean move value **@10/@25**,
adverse rate, calibration, actionability, time-to-target, lift over the
strongest frozen simple baseline, opportunities per week, and product
diagnostics at the `7`/`12`/`31` display caps.

Enter Now, Armed, and Waitlist are ranked separately. Recall and generic
classification accuracy are secondary.

---

## 17. Display contract

Qualification comes before ranking and display. Caps, not quotas:

* Enter Now: **max 7**
* Armed: **max 12**
* Qualified Waitlist: **max 12**

Maximum default focus list: **31**, but zero candidates is valid. Never backfill a
section with weaker names merely to reach its cap. An expanded view may later
show all genuinely qualified candidates. Do not impose artificial sector
diversification on the raw ranking; disclose concentration instead.

---

## 18. State architecture

Four conceptual layers:

1. Security/data eligibility
2. Opportunity qualification
3. Entry-state assignment
4. Within-state ranking/display

State precedence: `Enter Now > Armed > Qualified Waitlist > Hidden`. A stock
may appear in only one visible state at a time. Every official snapshot
recomputes state; do not persist yesterday's state automatically.

### Enter Now

Requires already qualified opportunity, executable current/next defined entry,
acceptable live execution conditions, no unresolved material invalidation, and
no additional trigger required. Morning-confirmed Enter Now is valid only for the
defined execution opportunity and expires if not executed.

### Armed

Requires qualified opportunity, explicit frozen trigger, maximum five-session
validity, frozen invalidation, gap-through handling, live liquidity/spread
requirements, sufficient trigger probability, and trigger-adjusted opportunity
value. Do not silently move the trigger. Changing the entry plan closes the old
recommendation and creates a new ID.

### Qualified Waitlist

Requires strong underlying opportunity potential, entry currently inadequate,
specific plausible path to Armed or Enter Now, explicit promotion condition, and
explicit removal condition. Waitlist is not a generic watchlist and is
requalified each official snapshot. Small model-score changes should not
cause state flicker; eventual hysteresis rules are permitted but their numeric
buffers are deferred to development. Preserve deterministic transition reason
codes.

---

## 19. Candidate model families and search budget

No model fitting occurs in `LONG-002A`. The future development allowlist is:

1. **Transparent cross-sectional rank/score system** — must retain an
   equal-weight reference form. Any alternative weighting scheme comes from a
   small registered set, not continuous unconstrained optimization.
2. **Regularized probabilistic/time-to-event system** — e.g., regularized
   logistic or discrete-time logistic hazard-style approaches.
3. **Shallow strongly regularized gradient-boosted trees** — the only nonlinear
   challenger.

Explicitly out of scope: neural networks, transformers for prediction,
reinforcement learning, genetic/evolutionary search, AutoML, unrestricted
stacking/ensembles, unlimited automated hyperparameter search, LLM-generated
trading probabilities, and unrestricted indicator-period search.

A feature registry must be frozen before model experiments begin. Adding
outcome-informed features afterward requires a documented development amendment.

### Search budget

* Round 1: maximum **12** material configurations per model family, **36** total.
* Round 2: maximum **12** additional material configurations across all families.
* Initial total: maximum **48** materially distinct model configurations.

Every attempted configuration, including failures, must remain in an experiment
ledger.

---

## 20. Entry-trigger research contract

Future entry research must separate stock-selection potential from timing.
Immediate next-session entry is the fixed control. Core daily-data trigger
families are:

1. Breakout continuation
2. Pullback / retest / reclaim
3. Catalyst-gap continuation

All levels, confirmation rules, invalidation, extension handling, and
five-session validity must be defined from information available at the original
decision timestamp. Core daily triggers should use completed-bar logic and
subsequent executable entry rather than infer unknowable intraday sequencing.
Intraday breakout/reclaim/VWAP/anchored-VWAP refinements are challengers only
when trustworthy intraday data supports them and may not block the daily-data
core study. Initial trigger-search budget: maximum **12** materially distinct
non-control configurations. Apply trigger research to the complete qualifying
candidate population, not known winners only.

---

## 21. Stop/invalidation and exit-management contract

Post-entry management remains separate from stock selection and entry research.

### M1 — downside/invalidation research

Test bounded concepts: no-protective-stop control, fixed-percentage stop,
volatility-normalized stop, setup-structural invalidation, justified hybrid.
Maximum **8** material M1 configurations. An initial stop/invalidation may
remain unchanged or tighten under a frozen rule but may never be widened to
rescue a losing trade. Thesis invalidation and protective stop are distinct
concepts.

### Daily-bar stop execution

If opening price gaps through stop, use actual open plus exit friction.
Otherwise if low crosses stop, use stop price plus friction. If stop and target
both occur in one daily bar and sequencing is unknown, primary policy is
stop-first, set ambiguity flag, and target-first may be sensitivity only.

### M2 — profit/exit research

At most two M1 policies may advance. Then test a bounded set such as time exit,
fixed target, staged target ladder, and target then trail. Maximum **8** material
M2 configurations total. Normal `LONG-002` trade lifetime: maximum **21 trading
sessions after actual entry**. A later opportunity requires fresh qualification
rather than silently extending the old trade.

---

## 22. Statistical evidence and uncertainty

Do not use raw daily-row count as the primary evidence-sufficiency measure.
Track separately: daily observations, surfaced opportunities, unique
recommendation episodes, independent master opportunity episodes, distinct
tickers, chronological coverage, and cohort concentration.

Earlier planning figures such as `300/100/150` positive episodes are planning
targets only, not locked hard gates. Actual minimum episode/recommendation
counts must be determined from development-only endpoint feasibility and frozen
before validation.

Primary uncertainty should use paired `LONG-002`-versus-frozen-baseline
time-block resampling: primary block **21 trading sessions**, robustness
sensitivity **42 trading sessions**. Keep the market cross-section together
within time blocks. Episode/archetype analysis should additionally use
ticker-aware robustness. Report 95% uncertainty intervals, but do not use
p-values/statistical significance alone to determine support.

Concentration in a sector/ticker/year triggers robustness analysis, not an
arbitrary automatic failure. Do not inspect holdout event counts in advance. If
realized holdout sample is insufficient after authorized access, the result may
be inconclusive; do not lower the gate afterward.

---

## 23. Advancement/disposition framework

No exact numerical advancement thresholds are invented in this PR where they were
intentionally deferred. Those must be derived from development-only evidence and
locked before validation.

### Structural requirements

* No more than three frozen candidate **systems** may advance from development.
* Validation selects at most one.
* Normally one fully frozen system enters holdout.
* Failed validation means no holdout parsing.
* Validation must use deterministic selection/tie-break rules.
* More complex systems must demonstrate practically meaningful incremental value
  over simpler alternatives.

Require both absolute product-usefulness gates and relative improvement over the
strongest frozen simple comparator.

### Final study disposition vocabulary

* `supported_for_production_consideration`
* `not_supported`
* `inconclusive`
* `invalid_evidence`

### Evidence-confidence vocabulary

* `strong_evidence`
* `moderate_evidence`
* `limited_but_usable_evidence`
* `invalid_evidence`

A supported historical research result (`LONG-002I`) authorizes only proceeding
to `LONG-002J` prospective shadow. A `prospectively_supported` `LONG-002J`
result authorizes only consideration of a separate Gary-approved production
decision-support PR. No single phase authorizes production deployment on its
own.

---

## 24. Explanation/confidence contract

Every displayed candidate must keep separate:

1. Predicted opportunity
2. Active-model data quality
3. Overall model evidence strength
4. Candidate-specific applicability/support

Candidate applicability states may include: well represented, partially
represented, sparse historical support, and outside supported range.
Outside-supported-range candidates should normally be prevented from actionable
states unless separately validated.

Do not display falsely precise probabilities. Internally preserve full model
probabilities, but user-facing output may use sensible rounding/ranges and
should suppress probability claims when calibration or support is inadequate.

Canonical explanations must be deterministic structured outputs. Default
summary: no more than 3 principal positive reasons and normally 2–3 material
counterarguments. Mandatory risk/invalidation/data warnings may never be hidden
by those presentation limits. A displayed reason must be traceable to an
actual active-model feature/rule and point-in-time source. Generated prose, if
ever added later, may improve readability but may not invent evidence, alter
ranking/state/probability, or omit mandatory risks. Historical displayed
snapshots must be reproducible exactly.

---

## 25. Monitoring and prospective shadow

### Candidate monitoring

Future candidate monitoring must reevaluate at every official snapshot,
preserve state transition history, use deterministic reason codes, permit
`Armed -> Waitlist` when the active trigger closes but the stock independently
requalifies, and prevent trivial score changes from causing churn through later
frozen hysteresis rules. Do not implement this in `LONG-002A`.

Actual user positions: TradeX must never infer that Gary entered merely because a
trigger fired. A future MVP concept may include `Mark as Entered`, prepopulated
recommendation metadata, required/confirmed actual fill price and timestamp,
with position size optional unless dollar P&L/risk tracking is desired. Actual
sizing remains Gary-controlled. No brokerage connectivity or automated order
execution is part of `LONG-002A`.

### Prospective shadow contract

If and only if historical validation and holdout pass, future `LONG-002`
prospective evaluation begins research-only shadow mode. Burn-in: **10 trading
sessions**, operational verification only, evidence excluded. Official minimum:
**126 trading sessions**, at least **50 unique actionable recommendation
episodes**, at least **30 mechanically executable shadow entries**. If calendar
minimum is reached before event minimum, continue observation. Logic remains
frozen during the official shadow period. Scheduled official snapshots must
achieve at least **99%** successful completion. No retrospective reconstruction,
silent stale data, silent provider substitution, or future leakage.

Prospective dispositions:

* `prospectively_supported`
* `prospectively_not_supported`
* `prospectively_inconclusive`
* `operationally_not_ready`
* `invalid_evidence`

A `prospectively_supported` `LONG-002J` result authorizes only **consideration**
of a separate Gary-approved production decision-support PR. It does not by
itself authorize production deployment. Historical holdout support
(`LONG-002I`) alone authorizes only the `LONG-002J` prospective shadow, not
production promotion.

---

## 26. Data/provider governance

This PR makes **zero provider calls** and **zero provider selection**. For
optional/required future data-family investigation, each probe must define:
preferred provider/history, minimum usable contract, accepted limitations,
genuine blockers, named fallback candidates, bounded retries/API calls/runtime,
and a stop condition. For each data family the search is bounded to **one
preferred provider plus at most two named fallback candidates**. There is no
silent provider switch: any change from the locked preferred/fallback contract
requires explicit documented approval. Once minimum usable data is found,
provider exploration stops. Additional provider hunting requires explicit Gary
approval and must address a calculation-invalidating blocker rather than simply
seek better-looking data. `LONG-002B` will be the phase that performs bounded
data-feasibility/provider work.

---

## 27. Phased `LONG-002` program

| Phase | Title | Scope |
|---|---|---|
| `LONG-002A` | Locked research/discovery contract | This PR; documentation/specification only. |
| `LONG-002B` | Core data feasibility and PIT dataset contract | Bounded provider/data audit, PIT universe feasibility, data-manifest design, no predictive model. |
| `LONG-002C` | Outcome census, master episodes, and frozen baselines | Development-only labels/base rates/episodes/baseline census. |
| `LONG-002D` | KPI discovery and blinded-review tooling | Feature registry, development-only descriptive analytics, blinded chart-study tooling. |
| `LONG-002E` | Bounded candidate-system development | Maximum 48 material model configurations. |
| `LONG-002F` | Entry-trigger research | Bounded trigger development. |
| `LONG-002G` | Management research | M1/M2 downside and exit research. |
| `LONG-002H` | Locked validation | No iterative tuning. |
| `LONG-002I` | Locked historical holdout | Only after validation explicitly authorizes access. |
| `LONG-002J` | Prospective shadow | Only after historical evidence supports proceeding. |

Do not implement later phases in `LONG-002A`.

---

## 28. Deferred decisions

The following decisions are intentionally deferred and may not be replaced
with plausible-looking defaults. Each item states when it may be decided and
what data may be used:

| Deferred item | When it may be decided | Data that may be used |
|---|---|---|
| Final model feature set | `LONG-002D`, after blinded chart review and KPI discovery | Development-only candidate families, controls, and locked data contract; no validation/holdout outcomes. |
| Final model weights/coefficients | `LONG-002E`, after feature registry freeze and model family selection | Development split and experiment ledger only. |
| Final qualification probability thresholds | `LONG-002E`, after model family search budget | Development-only candidate scores and base rates; no validation/holdout. |
| Final adverse-risk qualification ceiling | `LONG-002E`, during candidate-system search | Development split outcomes and base rates. |
| Final opportunity-value threshold | `LONG-002E`, during candidate-system search | Development split outcomes and expected clean move estimates. |
| Exact probability display formatting | `LONG-002E` calibration stage, after evidence-strength assessment | Development split calibration data only. |
| Exact ranking speed discount/weights | `LONG-002E`, after candidate family evaluation | Development split outcomes and base rates. |
| Exact practical-improvement gate over baseline | Before `LONG-002H` validation, derived from development-only evidence | Development split candidate-versus-baseline comparison. |
| Final independent-episode/sample-count gates | `LONG-002C` development-only endpoint feasibility census | Development split master episodes and base rates. |
| Exact state hysteresis buffers | Future monitoring phase, after `LONG-002E` candidate system and before shadow | Development/validation state transition simulation; no holdout. |
| Exact breakout/retest/catalyst trigger formulas/lookbacks | `LONG-002F` trigger research, after `LONG-002E` systems locked | Development split and locked feature registry. |
| Exact acceptable gap/extension bands by setup | `LONG-002F` trigger research | Development split entry-gap diagnostics. |
| Exact stop percentages/ATR multiples | `LONG-002G` M1 research | Development split downside/invalidation simulation. |
| Exact target allocation/trailing parameters | `LONG-002G` M2 research | Development split exit simulations. |
| Final optional provider choices | `LONG-002B`, after bounded provider feasibility audit | Provider contract and coverage data; no model outcomes. |
| Final optional news/analyst/options inclusion | `LONG-002D` feature registry and `LONG-002E` model search | Development-only coverage and incremental value tests; no validation/holdout. |
| Unique recommendation-episode lifecycle and grouping rule | Before `LONG-002E` model-evaluation sample gates are used. | Development-only master episodes and recommendation timestamps; no validation/holdout outcomes. |
| Final production behavior | Separate Gary-approved production decision-support PR, only after `LONG-002J` prospective shadow returns `prospectively_supported` and evidence supports promotion consideration. | Locked validation, holdout, and prospective shadow evidence only. |

---

## 29. Explicitly out of scope

`LONG-002A` does **not** do any of the following:

* No market-data/provider API calls.
* No historical OHLCV download.
* No fundamental download.
* No news download.
* No analyst-estimate download.
* No options download.
* No creation of a `LONG-002` real-data snapshot.
* No outcome census.
* No winner/loser event sampling.
* No chart-review execution.
* No KPI calculation.
* No feature selection.
* No model fitting.
* No hyperparameter tuning.
* No baseline performance calculation.
* No trigger implementation or testing.
* No stop/exit simulation.
* No development-period performance analysis.
* No validation access.
* No holdout access.
* No 2026 outcome analysis.
* No production signal, score, weight, threshold, ranking, eligibility,
  confluence, alert, or dashboard trading-logic changes.
* No `Mark as Entered` implementation.
* No brokerage or account integration.
* No automated trading.
* No raw market data committed.
* No claim that any `LONG-002` feature, model, or setup has predictive value.
* No unrelated cleanup/refactoring.

Do not create `tradex/research/long_002/` dataset/model/evaluator scaffolding
just to anticipate later phases unless a tiny pure spec helper is absolutely
necessary. This PR is docs + spec + tests.

---

## 30. Reuse and non-reuse of prior research

### Concepts/infrastructure patterns potentially reusable later

* Immutable study specifications
* SHA/hash identity
* Dataset manifests
* Fail-closed verification
* PIT timing
* XNYS calendar handling
* Cross-split exclusion
* Separate network snapshot from offline evaluation
* Fresh model/settings configuration
* No saved user weights
* Event-study versus executable-policy distinction
* Deterministic artifacts
* Cost sensitivity
* Benchmark reporting
* Cohort reporting
* Stable JSON-safe schemas

### `LONG-001` methodology that must not be inherited automatically

* Fixed 30-stock + 12-ETF universe
* Threshold 40
* 40-week SMA sole baseline
* 13/26-week holding horizons
* Existing production long-term feature set
* Existing long-term weights
* `LONG-001` promotion gates
* Weekly-only methodology

`LONG-002` is a distinct hypothesis/program. `INTRA-001` is also complete and
separate; its opening-drive/VWAP-pullback hypothesis must not be treated as
Gary's generic day-trading or long-term strategy.

---

## 31. Acceptance criteria for `LONG-002A`

1. This document provides a coherent standalone explanation of the approved
   `LONG-002` methodology and phased research program.
2. `docs/research/specs/LONG-002-v1.json` captures all material locked
   machine-readable decisions.
3. Deferred decisions remain clearly deferred and state the permitted future
   decision point/data source.
4. Human and machine-readable specifications do not materially contradict each
   other.
5. The study remains explicitly research-only.
6. `production_promotion_eligible=false`.
7. No provider or market-data calls are introduced or executed as part of
   `LONG-002A` research.
8. No historical outcomes/KPI/model results are generated.
9. No validation or holdout data is parsed.
10. No production scorer, score, weight, threshold, ranking, eligibility,
    confluence, alert, or dashboard trading behavior changes.
11. `LONG-001` remains intact and separate.
12. `INTRA-001` remains closed/inconclusive and separate.
13. `docs/PROJECT-TRACKER.md` accurately adds `LONG-002` and future
    `DAYTRADE-001` and removes stale completed-`INTRA-001` next-work language.
14. `README.md` and `CLAUDE.md` are minimally synchronized with the new research
    program.
15. Deterministic spec tests cover the critical locked invariants, including
    the `LONG-002I -> LONG-002J -> separate Gary-approved production PR`
    progression.
16. Existing tests and lint checks pass.
17. No secrets, credentials, raw OHLCV, private paths, or generated research
    results are committed.
18. The PR diff is focused on `LONG-002A` and tracker/documentation consistency
    only.
