# INTRA-001B-REFERENCE-V3 Reference Provider Probe Report

- **Task ID:** INTRA-001B-REFERENCE-V3
- **Probe version:** 3
- **Provider:** none selected
- **Outcome:** invalid
- **Approved as reference provider:** False
- **Reason:** V3 probe code contained a cursor-validation defect and is not decision-grade. Alpha Vantage LISTING_STATUS returned empty provider messages for all PIT dates; Massive/Polygon /v3/reference/tickers returned first-page data, but the pre-registered next_url validator rejected every provider-supplied cursor because it did not decode the base64url cursor before validating date/active/market. See the V4 proposal for the bounded rerun.
- **Candidate order:** alpha_vantage, massive
- **Starting main SHA:** 8405ca77569b55f460a381555843842fe55e248a
- **Branch:** devin/intra-001b-reference-v3
- **Live run head:** 03e61700dbf2fd072fc36bb63764dc7fa3876281
- **v1 pre-registration commit:** e4d123e5ecca80ab8ba1fa09ff397d4f0a3d67dc
- **v2 pre-registration commit:** d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299
- **v3 pre-registration commit:** 03e61700dbf2fd072fc36bb63764dc7fa3876281
- **v4 pre-registration commit:** n/a
- **Ran at:** 2026-08-08T00:33:21.113592+00:00
- **Not required gates:** none

## Locked methodology

- Original strategy spec: `docs/research/specs/INTRA-001-v1.json`
- Original spec SHA-256: `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- Amendment: `docs/research/specs/INTRA-001-data-contract-amendment-v2.json`
- No paid upgrade: `True`
- No composite reference stack: `True`

## Probe dates

- 2022-01-31
- 2023-07-31
- 2024-05-31
- 2025-11-30

## Fallback probe dates

- 2024-01-31
- 2024-07-31
- 2025-01-31
- 2025-11-30

## Decision gates

| Gate | Passed |
|------|--------|
| pit_date_support_for_all_probe_dates | False |
| active_state_complete | False |
| inactive_or_delisted_state_complete | False |
| pagination_exhausted_to_terminal | False |
| no_pagination_cycles_or_repeated_cursors | True |
| exact_historical_date_semantics | False |
| common_stock_classification | True |
| etf_classification | True |
| warrant_exclusion | True |
| right_exclusion | True |
| unit_exclusion | True |
| preferred_stock_exclusion | True |
| otc_exclusion | False |
| primary_listing_provenance | False |
| symbol_presence_and_determinism | False |
| lifecycle_evidence | delisting_date, listing_date |
| duplicate_symbol_behavior_and_resolution | True |
| repeatability | False |
| hashability | True |
| no_present_day_reconstruction | False |
| historical_2022_entitlement_under_current_plan | False |
| feasible_for_all_48_monthly_pit_snapshots | False |
| feasible_for_all_probe_monthly_pit_snapshots | False |
| **All mandatory gates passed** | False |

## Candidate dispositions

- **alpha_vantage** (original): evaluated — 2022-01-31/active: provider message: {}; 2022-01-31/delisted: provider message: {}; 2023-07-31/active: provider message: {}; 2023-07-31/delisted: provider message: {}; 2024-05-31/active: provider message: {}; 2024-05-31/delisted: provider message: {}; 2025-11-30/active: provider message: {}; 2025-11-30/delisted: provider message: {}
- **massive** (original): evaluated — 2022-01-31/active: invalid next_url: date parameter drift; 2022-01-31/inactive: invalid next_url: date parameter drift; 2023-07-31/active: invalid next_url: date parameter drift; 2023-07-31/inactive: invalid next_url: date parameter drift; 2024-05-31/active: invalid next_url: date parameter drift; 2024-05-31/inactive: invalid next_url: date parameter drift; 2025-11-30/active: invalid next_url: date parameter drift; 2025-11-30/inactive: invalid next_url: date parameter drift

## Provider candidate summary

- **Provider:** massive
- **Target entitlement:** current Gary entitlement
- **Primary exchange field:** primary_exchange
- **Security type field:** type
- **Delisting date field:** delisted_utc

**Errors:** 2022-01-31/active: invalid next_url: date parameter drift; 2022-01-31/inactive: invalid next_url: date parameter drift; 2023-07-31/active: invalid next_url: date parameter drift; 2023-07-31/inactive: invalid next_url: date parameter drift; 2024-05-31/active: invalid next_url: date parameter drift; 2024-05-31/inactive: invalid next_url: date parameter drift; 2025-11-30/active: invalid next_url: date parameter drift; 2025-11-30/inactive: invalid next_url: date parameter drift

### Security type counts


### Exchange counts


### Pagination summary

- Max active pages: 0
- Max inactive pages: 0

## Capability matrix

| Capability | Supported | Evidence class | Note |
|------------|-----------|----------------|------|
| pit_date_support_for_all_probe_dates | False | live_evidence | Successful PIT dates: []; required: ['2022-01-31', '2023-07-31', '2024-05-31', '2025-11-30'] |
| active_state_complete | False | live_evidence | Active observations: 0; complete: False |
| inactive_or_delisted_state_complete | False | live_evidence | Inactive/delisted observations: 0; complete: False |
| pagination_exhausted_to_terminal | False | live_evidence | At least one snapshot did not reach terminal pagination. |
| no_pagination_cycles_or_repeated_cursors | True | live_evidence | No repeated cursor, cycle, or unexpected next_url detected. |
| exact_historical_date_semantics | False | live_evidence | Distinct historical date semantics not proven. |
| common_stock_classification | True | live_evidence | Common-stock mapping present: True |
| etf_classification | True | live_evidence | ETF mapping present: True |
| warrant_exclusion | True | live_evidence | Warrant category present and ineligible: True |
| right_exclusion | True | live_evidence | Right category present and ineligible: True |
| unit_exclusion | True | live_evidence | Unit category present and ineligible: True |
| preferred_stock_exclusion | True | live_evidence | Preferred-stock category present and ineligible: True |
| otc_exclusion | False | live_evidence | OTC taxonomy: False; OTC exchange markers: False; primary exchange field: primary_exchange |
| primary_listing_provenance | False | live_evidence | No primary exchange field or values. |
| symbol_presence_and_determinism | False | live_evidence | Blank ticker count total: 0; canonical rows present: False |
| lifecycle_evidence | True | live_evidence | Lifecycle fields present: ('delisting_date', 'listing_date'); listing field: None; delisting field: delisted_utc |
| duplicate_symbol_behavior_and_resolution | True | live_evidence | Duplicate symbols: 0; unresolved: 0 |
| repeatability | False | live_evidence | Repeat mismatch or missing. |
| hashability | True | live_evidence | All successful snapshots have SHA-256 hashes. |
| no_present_day_reconstruction | False | live_evidence | Present-day reconstruction not disproven. |
| historical_2022_entitlement_under_current_plan | False | live_evidence | 2022 PIT date request failed or returned no rows. |
| feasible_for_all_48_monthly_pit_snapshots | False | documented_capability | 48-month feasibility not established. |
| feasible_for_all_probe_monthly_pit_snapshots | False | documented_capability | Feasibility for 4 probe monthly snapshots not established. |

---
This report is a research artifact only. It does not authorize production changes.
