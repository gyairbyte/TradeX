# INTRA-001B-REFERENCE-V4 Reference Provider Probe Report

- **Task ID:** INTRA-001B-REFERENCE-V4
- **Probe version:** 4
- **Provider:** none selected
- **Outcome:** unsupported
- **Approved as reference provider:** False
- **Reason:** Massive/Polygon completed all 12 monthly PIT snapshots for active/inactive states with verified pagination, taxonomy, repeatability, and hashability, but did not satisfy all mandatory gates: ['otc_exclusion', 'duplicate_symbol_behavior_and_resolution']. Duplicate symbols: 302; unresolved: 5. No paid upgrade or composite reference stack was introduced. The reference provider remains unselected under the current free entitlement.
- **Candidate order:** alpha_vantage, massive
- **Starting main SHA:** 8405ca77569b55f460a381555843842fe55e248a
- **Branch:** devin/intra-001b-reference-v3
- **Live run head:** 27b111c0c9cc0adb21ef82dd9d2f0699e55e297f
- **v1 pre-registration commit:** e4d123e5ecca80ab8ba1fa09ff397d4f0a3d67dc
- **v2 pre-registration commit:** d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299
- **v3 pre-registration commit:** 03e61700dbf2fd072fc36bb63764dc7fa3876281
- **v4 pre-registration commit:** 27b111c0c9cc0adb21ef82dd9d2f0699e55e297f
- **Ran at:** 2026-08-08T06:20:51.835613+00:00
- **Not required gates:** historical_2022_entitlement_under_current_plan, feasible_for_all_48_monthly_pit_snapshots

## Locked methodology

- Original strategy spec: `docs/research/specs/INTRA-001-v1.json`
- Original spec SHA-256: `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- Amendment: `docs/research/specs/INTRA-001-data-contract-amendment-v2.json`
- No paid upgrade: `True`
- No composite reference stack: `True`

## Probe dates

- 2025-08-31
- 2025-09-30
- 2025-10-31
- 2025-11-30
- 2025-12-31
- 2026-01-31
- 2026-02-28
- 2026-03-31
- 2026-04-30
- 2026-05-31
- 2026-06-30
- 2026-07-31

## Fallback probe dates

- 2024-09-30
- 2024-10-31
- 2024-11-30
- 2024-12-31
- 2025-01-31
- 2025-02-28
- 2025-03-31
- 2025-04-30
- 2025-05-31
- 2025-06-30
- 2025-07-31
- 2025-08-31
- 2025-09-30
- 2025-10-31
- 2025-11-30
- 2025-12-31
- 2026-01-31
- 2026-02-28
- 2026-03-31
- 2026-04-30
- 2026-05-31
- 2026-06-30
- 2026-07-31

## Decision gates

| Gate | Passed |
|------|--------|
| pit_date_support_for_all_probe_dates | True |
| active_state_complete | True |
| inactive_or_delisted_state_complete | True |
| pagination_exhausted_to_terminal | True |
| no_pagination_cycles_or_repeated_cursors | True |
| exact_historical_date_semantics | True |
| common_stock_classification | True |
| etf_classification | True |
| warrant_exclusion | True |
| right_exclusion | True |
| unit_exclusion | True |
| preferred_stock_exclusion | True |
| otc_exclusion | False |
| primary_listing_provenance | True |
| symbol_presence_and_determinism | True |
| lifecycle_evidence | delisting_date, listing_date |
| duplicate_symbol_behavior_and_resolution | False |
| repeatability | True |
| hashability | True |
| no_present_day_reconstruction | True |
| historical_2022_entitlement_under_current_plan | False |
| feasible_for_all_48_monthly_pit_snapshots | False |
| feasible_for_all_probe_monthly_pit_snapshots | True |
| **All mandatory gates passed** | False |

## Candidate dispositions

- **alpha_vantage** (original): evaluated_not_selected — 2022-01-31/active: provider message: {}; 2022-01-31/delisted: provider message: {}; 2023-07-31/active: provider message: {}; 2023-07-31/delisted: provider message: {}; 2024-05-31/active: provider message: {}; 2024-05-31/delisted: provider message: {}; 2025-11-30/active: provider message: {}; 2025-11-30/delisted: provider message: {}
- **massive** (original): evaluated — Completed all 12 monthly PIT snapshots; 868 HTTP page requests; failed mandatory gates: ['otc_exclusion', 'duplicate_symbol_behavior_and_resolution'].

## Provider candidate summary

- **Provider:** massive
- **Target entitlement:** current Gary entitlement
- **Primary exchange field:** primary_exchange
- **Security type field:** type
- **Delisting date field:** delisted_utc

### Security type counts

- ADRC: 8201
- ADRP: 180
- ADRR: 60
- CS: 139599
- ETF: 74269
- ETN: 3008
- ETS: 1579
- ETV: 1014
- FUND: 6881
- INDEX: 4855
- PFD: 26611
- RIGHT: 5283
- SP: 26022
- UNIT: 16149
- WARRANT: 26311

### Exchange counts

- ARCX: 52984
- BATS: 19238
- XASE: 23658
- XBOS: 12
- XNAS: 145308
- XNYS: 130649

### Pagination summary

- Max active pages: 14
- Max inactive pages: 24
- Estimated HTTP calls for 48 monthly snapshots: 1824
- Estimated collection time (seconds): 22,070

## Capability matrix

| Capability | Supported | Evidence class | Note |
|------------|-----------|----------------|------|
| pit_date_support_for_all_probe_dates | True | live_evidence | Successful PIT dates: ['2025-08-31', '2025-09-30', '2025-10-31', '2025-11-30', '2025-12-31', '2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30', '2026-05-31', '2026-06-30', '2026-07-31']; required: ['2025-08-31', '2025-09-30', '2025-10-31', '2025-11-30', '2025-12-31', '2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30', '2026-05-31', '2026-06-30', '2026-07-31'] |
| active_state_complete | True | live_evidence | Active observations: 24; complete: True |
| inactive_or_delisted_state_complete | True | live_evidence | Inactive/delisted observations: 24; complete: True |
| pagination_exhausted_to_terminal | True | live_evidence | All snapshots reached terminal pagination. |
| no_pagination_cycles_or_repeated_cursors | True | live_evidence | No repeated cursor, cycle, or unexpected next_url detected. |
| exact_historical_date_semantics | True | live_evidence | Date parameter preserved; distinct canonical sets across PIT dates. |
| common_stock_classification | True | live_evidence | Common-stock mapping present: True |
| etf_classification | True | live_evidence | ETF mapping present: True |
| warrant_exclusion | True | live_evidence | Warrant category present and ineligible: True |
| right_exclusion | True | live_evidence | Right category present and ineligible: True |
| unit_exclusion | True | live_evidence | Unit category present and ineligible: True |
| preferred_stock_exclusion | True | live_evidence | Preferred-stock category present and ineligible: True |
| otc_exclusion | False | live_evidence | OTC taxonomy: False; OTC exchange markers: False; primary exchange field: primary_exchange |
| primary_listing_provenance | True | live_evidence | Exchange field 'primary_exchange'; observed exchanges: ['ARCX', 'BATS', 'XASE', 'XBOS', 'XNAS', 'XNYS']... |
| symbol_presence_and_determinism | True | live_evidence | Blank ticker count total: 0; canonical rows present: True |
| lifecycle_evidence | True | live_evidence | Lifecycle fields present: ('delisting_date', 'listing_date'); listing field: None; delisting field: delisted_utc |
| duplicate_symbol_behavior_and_resolution | False | live_evidence | Duplicate symbols: 302; unresolved: 5 |
| repeatability | True | live_evidence | Full-snapshot repeat hashes matched for all observations. |
| hashability | True | live_evidence | All successful snapshots have SHA-256 hashes. |
| no_present_day_reconstruction | True | live_evidence | Distinct historical results across requested dates; no evidence of present-day reconstruction. |
| historical_2022_entitlement_under_current_plan | False | live_evidence | 2022 PIT date request failed or returned no rows. |
| feasible_for_all_48_monthly_pit_snapshots | False | documented_capability | 48-month PIT entitlement not probed in V4; 2022-2023 coverage explicitly not required. |
| estimated_48_month_pagination_cost | True | documented_capability | Estimated 1824 HTTP calls and 22,070.4s collection time for 48 monthly snapshots. |
| feasible_for_all_probe_monthly_pit_snapshots | True | documented_capability | Estimated 456 HTTP calls and 5,517.6s collection time for 12 probe monthly snapshots. |

---
This report is a research artifact only. It does not authorize production changes.
