# LONG-002B-DEC-001: Blocker Disposition Decision Packet

**Status:** `pending_gary_decision`
**LONG-002C authorized:** `false`
**Production promotion eligible:** `false`
**Starting `main` SHA:** `c7782f49dce0c637bfea1042a2ce65206d77d7af`

## Purpose

This packet presents three mutually exclusive options for resolving the two remaining `LONG-002B` blockers. It is research-governance only: no provider calls, credentials, dataset construction, or production changes occur in this PR.

## Upstream locked specifications

| Spec | SHA-256 |
|------|---------|
| `LONG-002-v1.json` | `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5` |
| `LONG-002B-probe-v1.json` | `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98` |
| `LONG-002B-data-contract-v1.json` | `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a` |
| `LONG-002B-AMEND-001-probe-v1.json` | `38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7` |

## Prerequisite artifact

- **Task:** `LONG-002B-AMEND-001`
- **Bundle:** `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647`
- **Run ID:** `2026-08-16-222647`
- **Overall disposition:** `not_supported`
- **Total HTTP requests:** 64
- **Preregistration commit SHA:** `75fad17b190d4879d26dd7de6b61241672193f08`
- **Code commit SHA in effect during live probe:** `42f1d93f43adf1cdef8f3b91c07370026544e764`

### Blocked family dispositions

- `security_identity_lifecycle_and_exclusion_classification`: `not_supported`
- `earnings_event_timing`: `not_supported`

## Blocked family summaries

### Security identity, lifecycle, and exclusion classification

- **Disposition:** `not_supported`
- **Blocker summary:** Multiple required (symbol, as_of_date) PIT rows returned generic or missing type fields (None, CS, INDEX) with no corroborating PIT name/SIC evidence. They fail closed to unknown, so the minimum exclusion-classification contract is not satisfied. PFF, SPY, IGR, and IPOD classify correctly, but panel-wide defensibility is not demonstrated.

### Historical known-at-the-decision-time earnings scheduling

- **Disposition:** `not_supported`
- **Blocker summary:** No preregistered endpoint returned a historical earnings schedule as it was known at the decision timestamp. Massive vX/reference/financials returns XBRL filing/period dates only; SEC EDGAR gives actual disclosure timestamps; Yahoo earnings calendar is prospective/current. The fallbacks were not exercised.


## Decision options

### Option 1 — Continue blocking LONG-002

Preserve both blocked families as not_supported and do not authorize LONG-002C. The program remains paused until new evidence satisfies the locked minimum usable contracts.

- **Selected by default:** `False`
- **Requires Gary approval:** `False`
- **Authorizes LONG-002C dataset construction:** `False`

**Evidence required to reopen:**
A provider amendment or policy change that demonstrates, for the probe panel, (a) defensible PIT security identity/lifecycle/exclusion classification, and (b) historical known-at-the-decision-time earnings scheduling, both satisfying their locked minimum usable contracts.

### Option 2 — Adopt an explicit fail-closed unknown policy

Formally amend the LONG-002 data contract so that missing or unresolvable PIT facts remain unknown and are never used as historical facts, features, ranking inputs, or actionability shortcuts. For earnings scheduling, an unknown schedule means the observation cannot be labeled a confirmed non-earnings setup and cannot reach Enter Now or Armed under the ordinary policy (at most Waitlist or do_not_surface, per later design). Current calendars, actual release dates, and SEC filing timestamps cannot be used retrospectively to restore actionability. This option requires a separate Gary/ChatGPT methodology approval before any LONG-002C design PR and does not establish that sufficient actionable samples exist.

- **Selected by default:** `False`
- **Requires Gary approval:** `True`
- **Authorizes LONG-002C dataset construction:** `False`

**Required contract amendment terms:**

- `security_unknown_rows_excluded_from_eligible_universe`: `True`
- `no_backfill_of_current_or_later_classifications_as_historical_facts`: `True`
- `unknown_security_classification_is_not_treated_as_common_stock`: `True`
- `earnings_schedule_fields_remain_unknown_when_historical_known_at_time_evidence_unavailable`: `True`
- `current_calendars_sec_filing_timestamps_or_actual_release_dates_may_not_be_substituted_for_previously_known_schedules`: `True`
- `unavailable_earnings_timing_cannot_become_predictive_feature_or_ranking_input`: `True`
- `unknown_earnings_schedule_cannot_be_labeled_confirmed_non_earnings_setup`: `True`
- `unknown_earnings_schedule_cannot_reach_enter_now_or_armed_under_ordinary_policy`: `True`
- `unknown_earnings_maximum_actionable_state_waitlist_or_do_not_surface`: `True`
- `no_retrospective_actionability_from_current_calendars_actual_release_or_sec_timestamps`: `True`
- `actionability_and_kpi_reporting_mark_unknown_earnings_observations_unavailable`: `True`
- `insufficient_known_schedule_coverage_makes_executable_policy_evaluation_inconclusive`: `True`
- `coverage_selection_bias_comparability_and_sample_sufficiency_risks_documented`: `True`
- `authorizes_only_a_separate_long_002c_design_pr_after_explicit_gary_approval`: `True`

### Option 3 — Authorize one final bounded provider amendment

Approve one additional research-only provider amendment bounded to resolve the two blocked families. No provider calls or code changes occur in this decision PR; the amendment must be separately approved and preregistered.

- **Selected by default:** `False`
- **Requires Gary approval:** `True`
- **Authorizes LONG-002C dataset construction:** `False`

**Provider amendment proposal (documentation only; no calls until separate Gary approval):**

- **Purpose:** Resolve the two not_supported blockers with positive, effective-dated evidence from at most one preferred provider plus two fallbacks per family.
- **security_identity_lifecycle_and_exclusion_classification**
  - Preferred provider: `crsp_wrds`
  - Capability sought: Historical daily security master with active/inactive/delisted flag, effective-dated ticker and share-class history, and a security-type taxonomy that maps defensibly to the locked LONG-002 exclusions.
  - Why existing sources failed: Massive v3/reference/tickers provides a single PIT row per ticker/date with generic type codes (CS/INDEX) that do not map to ETF/CEF/pre-merger SPAC; Alpaca and SEC EDGAR fallbacks similarly lack a complete historical exchange security master with lifecycle and defensible classification.
  - Fallbacks:
    - `nasdaq_data_link`: CRSP/Sharadar daily stock metadata including historical delistings and type flags.
    - `sec_edgar`: Issuer-level name/ticker/filing history; used only for identity joins and not for exchange security-type classification.
- **earnings_event_timing**
  - Preferred provider: `wall_street_horizon`
  - Capability sought: Historical earnings announcement calendar with vintage information: the future earnings date known at the decision timestamp, subsequent revisions, and separation from actual release/SEC filing timestamps.
  - Why existing sources failed: Massive vX/reference/financials exposes filing_date/period_of_report_date only; SEC EDGAR provides actual acceptance timestamps, not a previously known future schedule; Yahoo earnings calendar is current/prospective and has no vintage history.
  - Fallbacks:
    - `quandl_sharadar_events`: Historical earnings/announcement date dataset with vintage/revision history.
    - `sec_edgar`: Reconfirm that actual disclosure timestamps cannot substitute for a previously known future schedule; restrict use to filing/period dates.
- **Budget:**
  - Max HTTP requests: 120
  - Max runtime: 30 minutes
  - Max retries per request: 1
  - Max fallbacks per family: 2
  - No provider calls until separate Gary approval: `True`
- **Stop conditions:**
  - Stop the security family once the probe panel demonstrates stable PIT identity, active/inactive/renamed/delisted lifecycle evidence, defensible exclusion-type classification for each locked category, and split/dividend event provenance.
  - Stop the earnings family once a source demonstrates historical known-at-the-decision-time earnings scheduling with vintage/revision information and separation from SEC filing timestamps.
  - Stop immediately if all candidates fail the minimum usable contract or exceed the budget.
- **Evidence required to change family from not_supported:** Every boolean in the applicable minimum_usable_contract must be satisfied by recorded evidence; successful HTTP responses or payload presence alone are insufficient.


## Advisory recommendation

**Recommended option:** `2` — Adopt an explicit fail-closed unknown policy

**Rationale:** The PR #50 probe showed that the per-date classification logic works correctly: PFF, SPY, IGR, and IPOD map to their locked exclusion categories, while unresolved historical rows fail closed to unknown. A strict fail-closed unknown policy is therefore feasible without additional provider exploration, aligns with the research protocol's best-available-data principle, and lets LONG-002 proceed only to a bounded LONG-002C design PR after explicit Gary/ChatGPT approval. It does not establish that sufficient actionable samples exist. Option 1 is safe but stalls the program; Option 3 is likely costly and uncertain because historical earnings-calendar and security-master sources with the required vintage/PIT coverage are typically paid and may not resolve the unresolved historical rows. The fail-closed policy's main risk is reduced coverage and selection bias; the earnings-unknown rule means any executable-policy evaluation must separately mark or exclude those observations and may be inconclusive if known-schedule coverage is too low.

**Risks to document before any LONG-002C design PR:**

- Security rows with unknown classification are excluded from the eligible universe, which may reduce coverage and introduce selection bias toward larger, better-covered issuers.
- PIT-known earnings within five sessions block Enter Now / Armed; unknown earnings schedules are not treated as confirmed non-earnings setups and cannot reach Enter Now or Armed under the ordinary policy (at most Waitlist or do_not_surface), so the actionable sample may be materially smaller.
- Current earnings calendars, actual release timestamps, and SEC filing acceptance timestamps cannot be used retrospectively to restore actionability for observations where the schedule was unknown at the decision timestamp.
- Actionability and KPI reporting must separately mark or exclude observations whose earnings schedule was unknown; if known-schedule coverage is too low, executable-policy evaluation may be inconclusive.
- The unknown policy must be applied consistently; it cannot become a latent feature, ranking input, or post-hoc exclusion rule.
- Sample sufficiency, coverage, selection bias, comparability, and cohort-level power must be reassessed before any design PR is approved.

## Governance invariants

- No option in this packet authorizes LONG-002C dataset construction.
- A future Gary decision requires a separate approval and PR boundary.
- Current or later security classifications may never be substituted as historical facts.
- Earnings disclosure timestamps cannot masquerade as previously known schedules.
- Provider exploration remains bounded by the locked governance limits; no live calls occur in this PR.
- The locked upstream specification hashes are recorded and verified.
- The PR #50 artifact disposition remains not_supported and unchanged by this decision packet.

---

*This packet is advisory only and does not authorize LONG-002C.*
