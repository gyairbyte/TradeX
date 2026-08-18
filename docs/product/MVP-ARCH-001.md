# MVP-ARCH-001: TradeX provider, strategy, and dashboard consolidation plan

**Artifact:** `MVP-ARCH-001`
**Classification:** `product-architecture-and-governance-design-only`
**Decision status:** `pending_gary_decision`
**Starting `main` SHA:** `52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2`
**Prerequisite commit:** `52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2` (merged PR #52)

## Authorization boundary

- **Production Behavior Changes Authorized:** `False`
- **Provider Calls Authorized:** `False`
- **Dashboard Changes Authorized:** `False`
- **Provider Removal Authorized:** `False`
- **Alert Changes Authorized:** `False`
- **Database Migration Authorized:** `False`
- **Strategy Promotion Authorized:** `False`
- **Long 002C Work Authorized:** `False`
- **Pr Merge Authorized Without Gary Decision:** `False`

## Product diagnosis

TradeX has a strong modular technical and research foundation, but the current product is a collection of scanners, context tools, and research pipelines rather than one cohesive daily decision-support workflow. The MVP objective is to consolidate around a single understandable daily job: surface, evaluate, and review a small set of actionable long-candidates while quarantining research, context, and unproven heuristics.

### Primary daily job

Help Gary discover, evaluate, monitor, and review a small set of actionable long-only swing candidates each trading day, with explicit evidence, data confidence, and unknown-value handling.

### What Gary sees first

The Today view: a prioritized list of Enter Now / Armed / Waitlist candidates, with pre-market, earnings, and market context attached. Nothing else competes for attention until Gary clicks into a candidate.

## Required product questions

1. **What is TradeX's primary daily job for Gary?** Discover, evaluate, monitor, and review a small set of actionable long-only swing candidates each trading day.
1. **What should Gary see first when opening the application?** Today — Enter Now, Armed, and Waitlist candidates with context and data-confidence badges.
1. **Which current features directly support that job?** Scanner (after relabeling), Pre-Market (as context), Candidate Detail (future), and Journal (future).
1. **Which features are useful only as context?** Pre-Market gaps, earnings proximity, confluence aggregation, and coil detector persistence metrics.
1. **Which features belong exclusively in Research Lab?** Pattern Similarity, Score validation (VAL-002), LONG-001/SHORT-001/INTRA-001/LONG-002 artifacts, and research-only parameter studies.
1. **Which features should be archived?** Pattern Similarity primary navigation, Options Activity primary navigation, Signal Journal as a performance claim, and Weights as an untuned user-facing control.
1. **Which outputs can currently support actionability, and which cannot?** None of the existing numeric scores or heuristics are validated as executable strategies; they may be used only as discovery/context. A candidate must carry an approved strategy ID, entry plan, stop, target, and invalidation before it can be actioned.
1. **What evidence must exist before an experimental system becomes part of the primary workflow?** A locked research protocol, development evidence, validation and untouched-holdout gates, paired executable backtests, and a separate Gary-approved production PR that defines strategy ID, version, entry/stop/target/expiration, and universe.
1. **How should TradeX measure whether a complete strategy worked?** Using an executable journal that records the planned entry, realized fill, stop/target/expiration outcome, slippage, costs, and provider provenance per strategy version — not generic 1/3/5-session signal returns.
1. **What is the smallest sequence of changes that turns the existing foundation into a cohesive MVP?** 1. Truthful labels and evidence badges; 2. Provider lifecycle/config simplification; 3. Navigation consolidation; 4. Alert gating; 5. Candidate persistence contract; 6. Journal/outcome replacement; 7. Prospective PIT data capture; 8. Later LONG-002C resumption.

## Provider inventory

### yahoo
- **Roles:** ohlcv, premarket_bars, earnings, market_cap_ranking, options_chain_snapshot
- **Production/runtime:** yes
- **Research use:** yes
- **Credential/operational burden:** none
- **Limitations:** 15-min delayed intraday; free daily/weekly; no entitlement check; not point-in-time; historical adjustments and splits may differ from premium sources
- **Fallback behavior:** Default OHLCV provider; pre-market only supports Yahoo; no silent fallback from other providers to Yahoo for intraday execution
- **Mix within scan/outcome:** FetchReport records actual_provider; signal_history and outcome_tracker store provider provenance; mixing is visible, not hidden
- **Recommended lifecycle:** `operational_fallback`
- **Recommended role:** Daily/weekly/research OHLCV fallback; earnings treated as current/prospective only; unknown values must fail visibly
### schwab
- **Roles:** ohlcv, market_cap_ranking, liquidity_filter_fundamentals
- **Production/runtime:** yes
- **Research use:** yes
- **Credential/operational burden:** Schwab brokerage account + OAuth app + local token file
- **Limitations:** Real-time US equity data if entitled; account required; Used for PATTERN-001, SHORT-001, and other research with UTC-indexed, sorted, de-duplicated daily bars
- **Fallback behavior:** Configured as DATA_PROVIDER; whole-scan fallback disabled unless explicitly set via OHLCV_FALLBACK_ORDER
- **Mix within scan/outcome:** Provenance stored separately; outcome tracker may use different provider from signal provider
- **Recommended lifecycle:** `operational_primary`
- **Recommended role:** Primary operational OHLCV provider when configured; used for daily-history and outcome resolution
### alpaca
- **Roles:** ohlcv
- **Production/runtime:** yes
- **Research use:** yes
- **Credential/operational burden:** API key + secret key
- **Limitations:** Free tier IEX feed; real-time but may differ from SIP/consolidated tape; Historical daily bars validated in LONG-002B; SIP/feed limitations must be exposed
- **Fallback behavior:** Currently a whole-scan fallback if configured in OHLCV_FALLBACK_ORDER
- **Mix within scan/outcome:** actual_provider recorded in FetchReport and signal_history
- **Recommended lifecycle:** `operational_fallback`
- **Recommended role:** Explicitly degraded intraday fallback only if IEX/feed limitations are visible and tested; not a silent replacement for Schwab
### ibkr
- **Roles:** ohlcv
- **Production/runtime:** yes
- **Research use:** no
- **Credential/operational burden:** IB account + TWS/IB Gateway running locally
- **Limitations:** Real-time global markets; requires local gateway; Not used in any research artifact
- **Fallback behavior:** Supported in fetcher but not configured by default
- **Mix within scan/outcome:** Could be primary or fallback if configured
- **Recommended lifecycle:** `archived`
- **Recommended role:** Archive from MVP unless Gary explicitly selects IBKR as intended brokerage or global-market platform
### massive_polygon
- **Roles:** ohlcv, reference_ticker_data, corporate_actions
- **Production/runtime:** no
- **Research use:** yes
- **Credential/operational burden:** API key
- **Limitations:** Paid/institutional entitlement; v2/aggs returned 403 in LONG-002B probes; Reference endpoints provide per-ticker PIT rows but generic type codes do not satisfy LONG-002 exclusion contract
- **Fallback behavior:** Used as research/reference only; not integrated into operational fallback chain
- **Mix within scan/outcome:** Not used in production scans
- **Recommended lifecycle:** `research_only`
- **Recommended role:** Retain for research/reference and PIT data-family probes; do not promote to operational primary without a new Gary-approved amendment
### sec_edgar
- **Roles:** filings, fundamentals, shares, issuer_identity
- **Production/runtime:** no
- **Research use:** yes
- **Credential/operational burden:** none (public, rate-limited)
- **Limitations:** Public filing acceptance timestamps; not real-time quotes; Demonstrated PIT shares/filing acceptance-time control in LONG-002B; acceptance timestamps are actual disclosure, not previously known schedules
- **Fallback behavior:** Specialized source used directly in long_002_data_feasibility; not a general fallback
- **Mix within scan/outcome:** Not mixed with OHLCV outcomes; used for fundamental/identity validation
- **Recommended lifecycle:** `specialized_reference`
- **Recommended role:** Primary specialized filing/fundamental source; useful for identity and shares, not for earnings-calendar scheduling
### unusual_whales
- **Roles:** options_true_flow
- **Production/runtime:** no
- **Research use:** no
- **Credential/operational burden:** Paid API key
- **Limitations:** Transaction-level options flow if paid and configured; Not validated as a decision input; no research artifact uses it
- **Fallback behavior:** Chain/flow source resolution is explicit; no silent fallback
- **Mix within scan/outcome:** Not used in signal or outcome records
- **Recommended lifecycle:** `experimental`
- **Recommended role:** Archive from core MVP unless a defined strategy and adequate source are approved separately; true flow may return to Research Lab
### tradier
- **Roles:** options_chain_snapshot
- **Production/runtime:** no
- **Research use:** no
- **Credential/operational burden:** API key
- **Limitations:** Option-chain snapshots; not transaction flow; Not validated as a decision input
- **Fallback behavior:** Explicit options source selection only
- **Mix within scan/outcome:** Not used in signal or outcome records
- **Recommended lifecycle:** `experimental`
- **Recommended role:** Archive from core MVP unless a defined options use case is approved; chain snapshots are not directional signal evidence
### wikipedia
- **Roles:** constituent_lists
- **Production/runtime:** yes
- **Research use:** no
- **Credential/operational burden:** none; web scraping with user-agent header
- **Limitations:** Current index constituents only; no historical PIT membership; Not point-in-time; rebalancing drift and survivorship bias
- **Fallback behavior:** Not a fallback for market data
- **Mix within scan/outcome:** Used only for watchlist preset refresh
- **Recommended lifecycle:** `specialized_reference`
- **Recommended role:** Continue as watchlist constituent source, refreshed explicitly, with no claim of historical accuracy

## Provider recommendation

**Target principle:** one authoritative provider per capability, with at most one explicit fallback
**Notes:** Fallbacks must never silently convert delayed, partial, or differently sourced data into equivalent actionable evidence.

- **ohlcv:** primary `schwab`
  - fallback: alpaca (only as explicitly degraded intraday fallback with visible IEX/feed limitations)
- **premarket_bars:** primary `yahoo`
  - Only Yahoo currently supports pre-market bars; this is a known capability gap, not a recommendation to treat Yahoo as equivalent to real-time OHLCV.
- **filings_fundamentals_shares:** primary `sec_edgar`
  - Use acceptance-time controls and keep filing dates separate from known-at-time earnings schedules.
- **constituents:** primary `wikipedia`
  - Point-in-time membership must be confirmed separately before any research production.
- **earnings:** primary `(none verified)`
  - Yahoo earnings are current/prospective, not historical PIT. Unknown values must fail visibly; do not substitute SEC filing or actual release timestamps.
- **research_reference:** primary `massive_polygon`
  - Retain for research/reference and data-family probes only.

## Dashboard inventory and recommendation

### Scanner
- **User problem:** Which stocks are currently scoring highest on technical conditions?
- **Classification:** exploratory_scorer
- **Supporting research disposition:** Production scorers are legacy heuristics; no research program validated them as executable strategies.
- **Current overstatement:** UI language treats high scores as 'setups' and the sidebar labels higher scores as 'higher conviction'.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `keep_but_relabel`
- **Recommended action:** Relabel as 'Scanner (exploratory)' and add evidence badges distinguishing signal, context, and unvalidated heuristic.
### Coil Detector
- **User problem:** Which stocks have appeared repeatedly without breaking out?
- **Classification:** context
- **Supporting research disposition:** Exploratory; coil_strength formula is a heuristic, not a validated edge.
- **Current overstatement:** Help text describes coils as letting you 'get positioned before the obvious move'.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `move_to_research_lab`
- **Recommended action:** Move to Research Lab as 'Coil context'; keep the code and tests intact.
### Confluence
- **User problem:** Which stocks look strong across multiple timeframes?
- **Classification:** context
- **Supporting research disposition:** VAL-002 and related score validation do not establish that confluence predicts executable outcomes.
- **Current overstatement:** Caption calls results 'much higher conviction setups' and 'all timeframes aligned'.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `keep_but_relabel`
- **Recommended action:** Keep as context-only; replace 'conviction' language with 'alignment of exploratory scores' and show coverage/missing-timeframe metadata.
### Pattern Similarity
- **User problem:** Which stocks resemble historical run-up/decline shapes?
- **Classification:** research_only
- **Supporting research disposition:** PATTERN-001 was rejected on holdout; production promotion is false.
- **Current overstatement:** Help tab lists Pattern Match as a recommended third step in a first session.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `archive`
- **Recommended action:** Remove from primary navigation; preserve code, tests, and artifact bundle in Research Lab.
### Pre-Market
- **User problem:** Which stocks are gapping before the open and why?
- **Classification:** event_detector
- **Supporting research disposition:** Gap scanner is source-aware and marks failures visibly; only Yahoo supports pre-market bars.
- **Current overstatement:** Tier labels like 'large' and 'massive' gap can be read as trade recommendations.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `keep_but_relabel`
- **Recommended action:** Retain as event/context discovery; add badges showing gap is not an approved strategy entry.
### Options Activity
- **User problem:** Is there unusual options flow or chain activity?
- **Classification:** context
- **Supporting research disposition:** No defined strategy uses options data; no validated PIT options edge.
- **Current overstatement:** Tab name implies actionability; most users will have no true-flow source configured.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `archive`
- **Recommended action:** Remove from primary navigation unless a separately approved strategy and source are defined.
### Alerts
- **User problem:** Notify me when thresholds are crossed.
- **Classification:** settings_infrastructure
- **Supporting research disposition:** Alert infrastructure is sound, but it currently fires on unvalidated heuristics.
- **Current overstatement:** Alerts are presented as if coil/confluence/gap outputs are actionable thresholds.
- **Actionable today:** True
- **Outcome measurement valid:** False
- **Recommended disposition:** `merge_into_workflow`
- **Recommended action:** Keep the delivery infrastructure; move configuration into a future Settings area and gate automatic actionable alerts to approved strategies only.
### Signal Journal
- **User problem:** Did my signals work?
- **Classification:** legacy_signal_telemetry
- **Supporting research disposition:** Uses generic horizons, not strategy-specific entry/stop/target/expiration; does not prove edge.
- **Current overstatement:** Help text claims expectancy is 'the most important number' and positive expectancy means the strategy has edge.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `replace`
- **Recommended action:** Replace the primary Journal tab with a future executable-strategy journal; preserve existing SQLite rows as legacy_signal_telemetry.
### Weights
- **User problem:** Tune how many points each component contributes.
- **Classification:** settings_infrastructure
- **Supporting research disposition:** Weights are unvalidated and can be post-hoc tuned on uncontrolled observations.
- **Current overstatement:** Presentation as a tuning UI implies the user can improve the score without research control.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `archive`
- **Recommended action:** Remove from normal user workflow; future strategy parameters must be versioned and research-controlled.
### Help
- **User problem:** How do I use TradeX?
- **Classification:** settings_infrastructure
- **Supporting research disposition:** Currently recommends Pattern Match and Signal Journal as if they are validated workflows.
- **Current overstatement:** Quick-start still lists Pattern Match as a recommended step.
- **Actionable today:** False
- **Outcome measurement valid:** False
- **Recommended disposition:** `keep_but_relabel`
- **Recommended action:** Retain but rewrite inaccurate or overstated explanations; make evidence-state and research-status explicit.

## Strategy and evidence inventory

| Component | Evidence state | May rank | Actionable labels | Auto alerts | Notes |
|---|---|---|---|---|---|
| Production intraday scorer | `legacy_heuristic` | True | False | False | Additive 0-100 indicator; no validated executable edge. |
| Production short-term scorer | `legacy_heuristic` | True | False | False | VAL-002 did not authorize production changes; SHORT-001 is not supported. |
| Production long-term scorer | `legacy_heuristic` | True | False | False | LONG-001 was inconclusive. |
| Coil detector | `exploratory` | False | False | False | Heuristic persistence metric; move to Research Lab. |
| Confluence | `exploratory` | False | False | False | Coverage-aware aggregation of unvalidated scores; context only. |
| Premarket gaps | `exploratory` | False | False | False | Event detector; not an approved strategy. |
| Options activity | `exploratory` | False | False | False | Archive from primary workflow unless separately approved. |
| Pattern similarity / PATTERN-001 | `rejected` | False | False | False | Rejected on holdout; quarantined from production. |
| SHORT-001 | `not_supported` | False | False | False | No candidate policy passed development/validation; context not promoted. |
| LONG-001 | `inconclusive` | False | False | False | Production long-term score vs 40-week MA baseline; no promotion. |
| INTRA-001 | `inconclusive` | False | False | False | Real-data study inconclusive; holdout not parsed. |
| VAL-002 | `inconclusive` | False | False | False | Score validation study complete; did not force a production change recommendation. |
| LONG-002 | `research_only` | False | False | False | Rapid-upside research program; design PR authorized, dataset construction and production promotion unauthorized; currently paused for MVP architecture work. |

## Candidate contract design

**Purpose:** Keep distinct concepts separate before any candidate can be shown as Enter Now / Armed / Waitlist.

**Required fields:**

- `strategy_id`
- `strategy_version`
- `symbol`
- `security_identity_version`
- `decision_timestamp`
- `candidate_state`
- `setup_quality_score`
- `move_potential`
- `entry_readiness`
- `downside_risk`
- `data_confidence`
- `evidence_state`
- `human_readable_reasons`
- `missing_or_unknown_inputs`
- `provider_provenance`
- `entry_plan`
- `invalidation_stop`
- `target_or_expiration`

**Rules:**

- A single 0-100 score is not probability, cross-strategy comparability, evidence strength, or actionability.
- setup_quality, move_potential, entry_readiness, downside/risk, and data_confidence are separate fields.
- missing_or_unknown_inputs are explicit and cannot be backfilled with current or later data.

## Journal and outcome contract

**Current state:** `legacy_signal_telemetry`

**Why the current Signal Journal cannot prove an edge:**

- Uses signal close as reference, not the next executable entry fill.
- Measures later closes at generic 1/3/5-session horizons, not strategy-specific stop/target/expiration.
- Does not evaluate invalidation, stop, target, or expiration consistently.
- Expectancy formula is signal telemetry, not executable strategy expectancy.
- Encourages post-hoc threshold adjustment from uncontrolled observations.

**Future contract fields:**

- `strategy_id_and_version`
- `candidate_id`
- `planned_entry`
- `realized_fill`
- `stop_price`
- `target_price`
- `expiration`
- `invalidation_rule`
- `exit_reason`
- `exit_fill`
- `slippage_and_costs`
- `net_return`
- `strategy_drawdown`
- `provider_provenance`
- `outcome_confidence`

**Notes:** Existing SQLite rows must be preserved and labeled legacy_signal_telemetry. No data migration in this PR.

## Target product workflow

### Today
- **Purpose:** Enter Now, Armed, and Waitlist candidates with context badges.
- **Contains:** ranked candidate list, premarket context, earnings context, data confidence badges
### Candidate Detail
- **Purpose:** Deep-dive on one candidate.
- **Contains:** setup, readiness, risk, invalidation, evidence, missing data, chart, provenance
### Journal
- **Purpose:** Planned decisions and executable strategy outcomes.
- **Contains:** planned trades, fills, stops, targets, strategy-specific results
### Research Lab
- **Purpose:** Experimental, rejected, inconclusive, shadow, and archived systems.
- **Contains:** Pattern Similarity, Coil context, score validation, LONG-001/SHORT-001/INTRA-001/LONG-002 artifacts, parameter studies
### Settings
- **Purpose:** Providers, watchlists, alert delivery, diagnostics, read-only strategy config.
- **Contains:** provider lifecycle, alert channels, watchlists, diagnostics, read-only strategy versions

## Alert boundary

- Only separately approved actionable strategies may generate automatic actionable alerts.
- Research, rejected, inconclusive, archived, and legacy heuristic outputs cannot generate actionable alerts.
- Shadow strategies may record telemetry but may not send normal actionable alerts.
- Context and event detectors may be attached to an approved candidate but cannot independently imply a trade.
- Provider degradation or unknown mandatory data must prevent unsupported actionability.

## Prospective data capture recommendation

- Capture earnings schedules as known at 8:30 p.m. and 9:00 a.m. America/New_York decision timestamps.
- Capture security classification and reference facts at decision timestamps.
- Record provider and request provenance for every candidate observation.
- Record missing/unknown status explicitly rather than leaving it implicit.

## Rollout plan

### 1. Truthful UI/help labeling and evidence badges
- **Objective:** Add evidence-state badges to all existing tabs and rewrite Help to stop recommending rejected/inconclusive features.
- **Production/trading impact:** None; labels only.
- **Requires Gary approval:** True
- **Dependencies:** MVP-ARCH-001 approval
- **Rollback:** Revert label/markdown changes; no data migration.
### 2. Provider lifecycle/configuration simplification
- **Objective:** Make Schwab primary, Alpaca/Yahoo fallback roles explicit, archive IBKR default, and make unknown earnings fail visibly.
- **Production/trading impact:** Could change default provider selection; no signal logic changes.
- **Requires Gary approval:** True
- **Dependencies:** Step 1
- **Rollback:** Restore previous defaults via .env or settings.
### 3. Navigation consolidation
- **Objective:** Move Coil Detector, Pattern Similarity, and Options Activity to Research Lab; reorganize Settings.
- **Production/trading impact:** None; UI navigation only.
- **Requires Gary approval:** True
- **Dependencies:** Step 1
- **Rollback:** Restore previous tab list in dashboard.py.
### 4. Alert gating
- **Objective:** Gate automatic actionable alerts on approved strategy evidence-state; keep delivery infrastructure.
- **Production/trading impact:** Reduces false alerts; requires approved strategy list.
- **Requires Gary approval:** True
- **Dependencies:** Step 3
- **Rollback:** Disable gating or restore previous alert threshold check.
### 5. Candidate persistence contract
- **Objective:** Introduce candidate table/schema that stores the candidate contract fields.
- **Production/trading impact:** Adds schema; no changes to existing signal_history.
- **Requires Gary approval:** True
- **Dependencies:** Step 2
- **Rollback:** Drop new table; existing tables untouched.
### 6. Journal/outcome replacement
- **Objective:** Add executable strategy journal; keep legacy signal_history rows labeled legacy_signal_telemetry.
- **Production/trading impact:** Replaces Signal Journal primary UI; does not delete data.
- **Requires Gary approval:** True
- **Dependencies:** Step 5
- **Rollback:** Restore Signal Journal tab; new journal table remains empty.
### 7. Prospective PIT data capture
- **Objective:** Schedule lightweight capture of earnings, classification, and provider provenance at decision timestamps.
- **Production/trading impact:** None until used by an approved strategy.
- **Requires Gary approval:** True
- **Dependencies:** Step 2
- **Rollback:** Disable capture job.
### 8. Later resumption of LONG-002C design
- **Objective:** Resume LONG-002C design PR only after MVP architecture and candidate/journal contracts are approved.
- **Production/trading impact:** None until a separate production PR is approved.
- **Requires Gary approval:** True
- **Dependencies:** Step 5, Step 6
- **Rollback:** Continue pausing LONG-002C; no dataset built.

## Material discrepancies found

- README.md LONG-002 'Current phase' still names LONG-002B-AMEND-001 even though LONG-002B-AMEND-002 is merged; this should be synchronized.
- Help tab quick-start recommends Pattern Match as step 3, but PATTERN-001 was rejected and pattern similarity is research-only.
- Signal Journal help text presents expectancy as proof of strategy edge, but the underlying outcome windows are generic 1/3/5-session signal telemetry.
- Coil Detector help text uses 'before the crowd sees them' and 'bigger potential release' language that implies a validated edge.
- Confluence tab caption calls the weighted score 'much higher conviction' though it is an aggregation of unvalidated heuristics.
- Options Activity tab label implies actionability, but no options source is configured by default and no strategy uses the output.
- Weights tab allows user tuning of component points persisted to ~/.tradex/weights.json without research versioning or validation.
- PROJECT-TRACKER current phase is LONG-002B-AMEND-002 and does not yet reflect Gary's pause for MVP architecture work.

## Governance invariants

- No implementation, provider call, dashboard change, alert change, database migration, or production signal change occurs in this PR.
- No existing strategy is relabeled production_approved.
- LONG-002C design was authorized by PR #52 but is explicitly paused while MVP architecture work is completed.
- LONG-002C dataset construction remains unauthorized.
- Production promotion remains unauthorized.
- Final consolidation decisions remain pending Gary approval.
- Existing research artifacts and locked specifications are referenced, not modified.

---

*This packet is a versioned product-architecture decision document. It does not implement any consolidation, provider change, dashboard change, alert change, database migration, or production behavior change.*
