# MVP-ARCH-001: TradeX provider, strategy, and dashboard consolidation plan

**Artifact:** `MVP-ARCH-001`
**Classification:** `product-architecture-and-governance-design-only`
**Decision status:** `gary_approved` (design-only)
**Approved by:** `Gary Yang`
**Approved on:** `2026-08-19`
**Approval scope:** `design_only` — this approval does not authorize implementation, production trading changes, provider calls, LONG-002C dataset construction, or any rollout step without separate Gary approval.
**Starting `main` SHA:** `52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2`
**Prerequisite commit:** `52cff71fd73105c7a2a01bc6f9ccc19c3ae204a2` (merged PR #52)

## Authorization boundary

This packet is design-only and has been approved by Gary Yang on 2026-08-19 as the product-architecture direction. No implementation, provider call, dashboard change, alert change, database migration, production signal change, LONG-002C work, or rollout step is authorized by this approval. Each rollout step listed below requires separate Gary approval.

- **Alert Changes Authorized:** `False`
- **Dashboard Changes Authorized:** `False`
- **Database Migration Authorized:** `False`
- **Pr Merge Authorized Without Gary Decision:** `False`
- **Production Behavior Changes Authorized:** `False`
- **Provider Calls Authorized:** `False`
- **Provider Removal Authorized:** `False`
- **Strategy Promotion Authorized:** `False`

## Product diagnosis

TradeX has a strong modular technical and research foundation, but the current product is a collection of scanners, context tools, and research pipelines rather than one cohesive daily decision-support workflow. The MVP objective is to consolidate around a single understandable daily job: surface, evaluate, and review a small set of actionable long-candidates while quarantining research, context, and unproven heuristics.

**Primary daily job:** Help Gary discover, evaluate, monitor, and review a small set of actionable long-only swing candidates each trading day, with explicit evidence, data confidence, and unknown-value handling.
**First screen:** The Today view: a prioritized list of Enter Now / Armed / Waitlist candidates, with pre-market, earnings, and market context attached. Nothing else competes for attention until Gary clicks into a candidate.
**Scope note:** MVP-ARCH-001 is a separate product-architecture and governance workstream. It does not authorize LONG-002C work, dataset construction, provider calls, or production behavior changes.

## LONG-002 and MVP-ARCH-001 workstream separation

- `long_002b_amend_002_completed`: `True`
- `long_002c_design_authorized_by_pr52`: `True`
- `long_002c_currently_paused_by_gary`: `True`
- `long_002c_dataset_construction_authorized`: `False`
- `long_002c_work_authorized_by_mvp_arch_001`: `False`
- **Notes:** LONG-002B-AMEND-002 is completed and merged. LONG-002C design is authorized by PR #52, but Gary has explicitly paused its execution while MVP-ARCH-001 is completed. MVP-ARCH-001 is a separate product-architecture workstream and does not alter LONG-002 authorization.

## Provider recommendation

**Target principle:** one authoritative provider per capability, with at most one explicit fallback

| Capability | Primary | Fallback / Notes |
|---|---|---|
| constituents | wikipedia | Point-in-time membership must be confirmed separately before any research production. |
| earnings | (none verified) | current: yahoo; Yahoo earnings are current/prospective, not historical PIT. Unknown values must fail visibly; do not substitute SEC filing or actual release timestamps. |
| filings_fundamentals_shares | sec_edgar | Use acceptance-time controls and keep filing dates separate from known-at-time earnings schedules. |
| global_brokerage | archived | IBKR archived unless Gary later selects it as the intended brokerage or global-market platform. |
| ohlcv | schwab | fallback: alpaca (only as explicitly degraded intraday fallback with visible IEX/feed limitations); research fallback: yahoo (daily/weekly research and fallback; not silent actionable intraday fallback) |
| options | removed from core MVP | Options Activity should be archived from primary navigation unless a defined strategy and adequate source are approved in a separate PR. |
| premarket_bars | yahoo | Only Yahoo currently supports pre-market bars; this is a known capability gap, not a recommendation to treat Yahoo as equivalent to real-time OHLCV. |
| research_reference | massive_polygon | Retain for research/reference and data-family probes only. |

## Dashboard disposition and target-area mapping

| Tab | Disposition | Target area | Action |
|---|---|---|---|
| Scanner | `merge_into_workflow` | Today | Feed the Today view; relabel as 'Scanner (exploratory)' and add evidence badges. |
| Coil Detector | `move_to_research_lab` | Research Lab | Move to Research Lab as 'Coil context'; keep code and tests intact. |
| Confluence | `merge_into_workflow` | Candidate Detail | Show as alignment-of-scores context inside Candidate Detail; replace 'conviction' language. |
| Pattern Similarity | `move_to_research_lab` | Research Lab | Remove from primary navigation; preserve code, tests, and artifacts in Research Lab. |
| Pre-Market | `merge_into_workflow` | Candidate Detail | Show as pre-market event context inside Candidate Detail; add non-actionable badge. |
| Options Activity | `archive` | Research Lab | Archive from primary navigation; preserve adapters and research option in Research Lab for a future approved use case. |
| Alerts | `merge_into_workflow` | Settings | Move alert configuration into Settings; notifications attach to Today / Candidate Detail when triggered. |
| Signal Journal | `replace` | Journal | Replace with an executable-strategy journal; existing SQLite rows remain as legacy_signal_telemetry. |
| Weights | `archive` | Settings | Remove user-facing point tuning; future strategy parameters are versioned and surfaced read-only in Settings. |
| Help | `merge_into_workflow` | Today | Make contextual help inside Today / Candidate Detail instead of a competing primary tab. |

## Strategy and evidence state

| Component | State | May rank | Actionable labels | Auto alerts | Notes |
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
| LONG-002 | `research_only` | False | False | False | Rapid-upside research program; LONG-002B-AMEND-002 is completed; LONG-002C design is authorized by PR #52 but explicitly paused by Gary while MVP-ARCH-001 is completed; dataset construction and production promotion unauthorized. |

## Candidate contract

**Purpose:** Keep distinct concepts separate before any candidate can be shown as Enter Now / Armed / Waitlist.

**Fields:** `strategy_id`, `strategy_version`, `symbol`, `security_identity_version`, `decision_timestamp`, `candidate_state`, `setup_quality_score`, `move_potential`, `entry_readiness`, `downside_risk`, `data_confidence`, `evidence_state`, `human_readable_reasons`, `missing_or_unknown_inputs`, `provider_provenance`, `entry_plan`, `invalidation_stop`, `target_or_expiration`, `outcome_status`

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

**Future contract fields:** `strategy_id_and_version`, `candidate_id`, `planned_entry`, `realized_fill`, `stop_price`, `target_price`, `expiration`, `invalidation_rule`, `exit_reason`, `exit_fill`, `slippage_and_costs`, `net_return`, `strategy_drawdown`, `provider_provenance`, `outcome_confidence`

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
- **Impact:** None; labels only.
- **Gary approval required:** True
- **Dependencies:** MVP-ARCH-001 approval
- **Rollback:** Revert label/markdown changes; no data migration.
### 2. Provider lifecycle/configuration simplification
- **Objective:** Make Schwab primary, Alpaca/Yahoo fallback roles explicit, archive IBKR default, and make unknown earnings fail visibly.
- **Impact:** Could change default provider selection; no signal logic changes.
- **Gary approval required:** True
- **Dependencies:** Step 1
- **Rollback:** Restore previous defaults via .env or settings.
### 3. Navigation consolidation
- **Objective:** Move Coil Detector, Pattern Similarity, and Options Activity to Research Lab; reorganize Settings.
- **Impact:** None; UI navigation only.
- **Gary approval required:** True
- **Dependencies:** Step 1
- **Rollback:** Restore previous tab list in dashboard.py.
### 4. Alert gating
- **Objective:** Gate automatic actionable alerts on approved strategy evidence-state; keep delivery infrastructure.
- **Impact:** Reduces false alerts; requires approved strategy list.
- **Gary approval required:** True
- **Dependencies:** Step 3
- **Rollback:** Disable alert gating and keep the alert policy fail-closed; do not re-enable unsupported legacy alert thresholds.
### 5. Candidate persistence contract
- **Objective:** Introduce candidate table/schema that stores the candidate contract fields.
- **Impact:** Adds schema; no changes to existing signal_history.
- **Gary approval required:** True
- **Dependencies:** Step 2
- **Rollback:** Stop writing new candidates, hide the new surface, and revert to the previous code path; the new candidate table remains empty and existing tables are untouched.
### 6. Journal/outcome replacement
- **Objective:** Add executable strategy journal; keep legacy signal_history rows labeled legacy_signal_telemetry.
- **Impact:** Replaces Signal Journal primary UI; does not delete data.
- **Gary approval required:** True
- **Dependencies:** Step 5
- **Rollback:** Restore the Signal Journal tab as the primary journal view; the new executable-strategy journal table remains empty and untouched.
### 7. Prospective PIT data capture
- **Objective:** Schedule lightweight capture of earnings, classification, and provider provenance at decision timestamps.
- **Impact:** None until used by an approved strategy.
- **Gary approval required:** True
- **Dependencies:** Step 2
- **Rollback:** Disable the capture job; already captured rows remain.
### 8. Later resumption of LONG-002C design
- **Objective:** Resume LONG-002C design PR only after MVP architecture and candidate/journal contracts are approved.
- **Impact:** None until a separate production PR is approved.
- **Gary approval required:** True
- **Dependencies:** Step 5, Step 6
- **Rollback:** Continue pausing LONG-002C; no dataset built.

## Material discrepancies found

- README.md and PROJECT-TRACKER need to clearly separate LONG-002B-AMEND-002 completion, LONG-002C design authorized-but-paused, and MVP-ARCH-001 as a separate workstream.
- Help tab quick-start recommends Pattern Match as step 3, but PATTERN-001 was rejected and pattern similarity is research-only.
- Signal Journal help text presents expectancy as proof of strategy edge, but the underlying outcome windows are generic 1/3/5-session signal telemetry.
- Coil Detector help text uses 'before the crowd sees them' and 'bigger potential release' language that implies a validated edge.
- Confluence tab caption calls the weighted score 'much higher conviction' though it is an aggregation of unvalidated heuristics.
- Options Activity tab label implies actionability, but no options source is configured by default and no strategy uses the output.
## Scoped Rollout Authorizations

### MVP-ARCH-001-R1 (Approved 2026-08-21)

Gary Yang separately approved rollout step 1 on 2026-08-21 with narrow scope:
- **Task ID:** `MVP-ARCH-001-R1`
- **Scope:** Truthful UI/help labeling and evidence-state notices only across all 10 existing tabs.
- **Boundaries:**
  - `implementation_authorized`: `True` (strictly bounded to UI/help labeling and evidence notice rendering)
  - `production_trading_changes_authorized`: `False`
  - `navigation_changes_authorized`: `False`
  - `alert_behavior_changes_authorized`: `False`
  - `provider_changes_authorized`: `False`
  - `provider_calls_authorized`: `False`
  - `database_migration_authorized`: `False`
  - `strategy_promotion_authorized`: `False`
  - `long_002c_work_authorized`: `False`
- **Status:** Implemented in PR #57.

### MVP-ARCH-001-R2 (Approved 2026-08-21)

Gary Yang separately approved rollout step 2 on 2026-08-21 with narrow scope:
- **Task ID:** `MVP-ARCH-001-R2`
- **Scope:** Provider lifecycle and configuration simplification only.
- **Boundaries:**
  - `implementation_authorized`: `True` (strictly bounded to provider lifecycle and configuration simplification)
  - `provider_changes_authorized`: `True`
  - `default_ohlcv_provider_change_authorized`: `True` (Schwab primary/default; Alpaca/Yahoo explicit fallback; IBKR archived/manual)
  - `premarket_source_decoupling_authorized`: `True` (Specialized Yahoo pre-market provider decoupled from central OHLCV default)
  - `earnings_unknown_handling_authorized`: `True` (Fail-closed on unknown earnings when filter enabled)
  - `production_trading_changes_authorized`: `False`
  - `signal_logic_changes_authorized`: `False`
  - `score_changes_authorized`: `False`
  - `weight_changes_authorized`: `False`
  - `threshold_changes_authorized`: `False`
  - `navigation_changes_authorized`: `False`
  - `alert_behavior_changes_authorized`: `False`
  - `live_provider_calls_authorized`: `False`
  - `database_migration_authorized`: `False`
  - `strategy_promotion_authorized`: `False`
  - `long_002c_work_authorized`: `False`
- **Subsequent steps (Steps 3–8):** Remain pending separate Gary approval.
- **Status:** Implemented and merged in PR #58.

### MVP-ARCH-001-R3 (Approved 2026-08-22)

Gary Yang separately approved rollout step 3 on 2026-08-22 with narrow scope:
- **Task ID:** `MVP-ARCH-001-R3`
- **Scope:** Navigation consolidation only (Research Lab and Settings transitional grouping).
- **Boundaries:**
  - `implementation_authorized`: `True` (strictly bounded to navigation consolidation)
  - `navigation_changes_authorized`: `True`
  - `research_lab_navigation_authorized`: `True`
  - `settings_navigation_authorized`: `True`
  - `production_trading_changes_authorized`: `False`
  - `signal_logic_changes_authorized`: `False`
  - `score_changes_authorized`: `False`
  - `weight_changes_authorized`: `False`
  - `threshold_changes_authorized`: `False`
  - `alert_behavior_changes_authorized`: `False`
  - `provider_changes_authorized`: `False`
  - `provider_calls_authorized`: `False`
  - `live_provider_calls_authorized`: `False`
  - `database_migration_authorized`: `False`
  - `candidate_persistence_authorized`: `False`
  - `journal_replacement_authorized`: `False`
  - `pit_capture_authorized`: `False`
  - `strategy_promotion_authorized`: `False`
  - `long_002c_work_authorized`: `False`
- **Subsequent steps (Steps 4–8):** Remain pending separate Gary approval.

## Governance invariants

- Production promotion remains unauthorized.
- MVP-ARCH-001 original architecture approval remains design-only; MVP-ARCH-001-R1 was separately Gary-approved and implemented for truthful UI/help labeling and evidence-state notices only; MVP-ARCH-001-R2 was separately Gary-approved and implemented for provider lifecycle and configuration simplification only; MVP-ARCH-001-R3 is separately Gary-approved on 2026-08-22 for navigation consolidation only; rollout Steps 4–8 remain pending separate Gary approval; R3 does not authorize production trading changes, signal logic changes, score/weight/threshold changes, alert behavior changes, provider changes/calls, database migrations, candidate persistence, journal replacement, PIT capture, strategy promotion, or LONG-002C work.
- Existing research artifacts and locked specifications are referenced, not modified.
- LONG-002B-AMEND-002 is completed and merged; LONG-002C design is authorized by PR #52 but explicitly paused by Gary; MVP-ARCH-001 is a separate product-architecture workstream.
- This packet does not authorize LONG-002C dataset construction, provider calls, dashboard changes, alert changes, database migrations, strategy promotion, or production behavior changes.
- No existing strategy is relabeled production_approved.

---

*This packet is a versioned product-architecture decision document. It does not implement any consolidation, provider change, dashboard change, alert change, database migration, or production behavior change.*
