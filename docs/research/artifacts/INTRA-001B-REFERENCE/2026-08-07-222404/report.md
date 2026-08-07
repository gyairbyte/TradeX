# INTRA-001B-REFERENCE Reference Provider Probe Report

- **Task ID:** INTRA-001B-REFERENCE
- **Probe version:** 1
- **Provider:** massive
- **Outcome:** supported
- **Approved as reference provider:** True
- **Reason:** All mandatory reference-provider gates passed.
- **Candidate order:** alpha_vantage, massive
- **Pre-registration commit:** d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299
- **Final head:** d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299
- **Branch:** devin/intra-001b-reference-source
- **Ran at:** 2026-08-07T22:24:04.258836+00:00

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

## Decision gates

| Gate | Passed |
|------|--------|
| PIT date support | True |
| Active/delisted coverage | True |
| Security-type exclusions possible | True |
| Security-type taxonomy granular | True |
| Primary exchange provenance | True |
| Reproducible | True |
| Free under current entitlement | True |
| Full repeatability passed | True |

## Provider candidate summary

- **Provider:** massive
- **Target entitlement:** current Gary entitlement
- **Primary exchange field:** primary_exchange
- **Security type field:** type
- **Delisting date field:** delisting_utc

### Security type counts

- ADRC: 217
- CS: 3311
- ETF: 752
- ETN: 38
- ETS: 36
- ETV: 4
- FUND: 75
- INDEX: 23
- PFD: 732
- RIGHT: 66
- SP: 427
- UNIT: 335
- WARRANT: 563

### Exchange counts

- ARCX: 560
- BATS: 191
- XASE: 394
- XNAS: 3179
- XNYS: 2743

## Capability matrix

| Capability | Supported | Evidence class | Note |
|------------|-----------|----------------|------|
| pit_date_support_for_all_probe_dates | True | live_evidence | All four PIT dates returned rows without error. |
| active_and_delisted_or_inactive_coverage | True | live_evidence | States with data: ['active', 'inactive']. |
| security_type_exclusions_feasible | True | live_evidence | Observed type values: ['ADRC', 'CS', 'ETF', 'ETN', 'ETS', 'ETV', 'FUND', 'INDEX', 'PFD', 'RIGHT', 'SP', 'UNIT', 'WARRANT']. |
| security_type_taxonomy_granular | True | live_evidence | Provider exposes labels that distinguish the five unwanted security types. |
| primary_exchange_provenance | True | live_evidence | Observed exchanges: ['ARCX', 'BATS', 'XASE', 'XNAS', 'XNYS']... |
| full_repeatability | True | live_evidence | Repeat fetch SHA-256 matched for every observation. |
| free_under_current_entitlement | True | documented_capability | Probe used only free endpoints; no paid upgrade was required. |
| historical_2022_entitlement_under_current_plan | True | live_evidence | A 2022 PIT date was requested and returned data. |
| listing_and_delisting_date_fields | True | live_evidence | Delisting field: delisting_utc; listing field: None. |

---
This report is a research artifact only. It does not authorize production changes.
