# INTRA-001 Mixed-Provider Data Contract Amendment v2

> **Superseded for prospective dataset construction:** `INTRA-001-data-sufficiency-amendment-v3` (`docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json` and `docs/research/INTRA-001-DATA-SUFFICIENCY-AMENDMENT-V3.md`) is now the active data-sufficiency and provider methodology for `INTRA-001`. Amendment v2 and this document are preserved as historical records; the canonical v2 JSON is unchanged.

This document formalizes Gary's approval of a locked, role-based mixed-provider data contract for the `INTRA-001` research study. It is an amendment to the original locked strategy specification only; every non-data-source rule in `docs/research/specs/INTRA-001-v1.json` remains unchanged.

## Original strategy spec

- File: `docs/research/specs/INTRA-001-v1.json`
- SHA-256: `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- Status: unchanged and immutable

## Why a mixed-provider contract is needed

`INTRA-001B-ALPACA-V2` determined that Alpaca's free historical SIP feed can supply the five-minute OHLCV bars required by `INTRA-001` with complete regular-session coverage from 2022 through 2025. However, Alpaca does not satisfy the point-in-time universe, security-master, delisted-symbol, or consolidated-versus-venue volume provenance requirements. Gary approved Option B: a locked mixed-provider research dataset in which one provider owns OHLCV and a separate reference provider owns point-in-time listing/security-master data.

## Provider roles (authoritative, non-overlapping)

### 1. Alpaca SIP — authoritative OHLCV source

Alpaca SIP is the sole source for:

- five-minute OHLCV bars
- complete regular-session history
- prior closes used in liquidity/ranking calculations
- prior 20 regular-session dollar-volume calculations
- session VWAP inputs
- opening-drive volume
- execution prices (entry, stop, target, time-exit)

No other provider may supply OHLCV for `INTRA-001` after the contract is locked.

### 2. Reference provider — authoritative point-in-time universe/security-master source

The reference provider selected by `INTRA-001B-REFERENCE` is the sole source for:

- monthly point-in-time active listings
- stock vs. ETF classification
- security-type eligibility and exclusions
- primary listing/exchange provenance, where available
- inactive/delisted status
- IPO/listing date, where available
- delisting date, where available
- the symbol/reference identity required for monthly membership

No other provider may supply these fields for `INTRA-001` after the contract is locked.

## Cross-provider join policy

1. The preferred join key is a stable, provider-supported identifier if one is demonstrably available and historically valid across the study window.
2. If no stable cross-provider ID exists, the join falls back to exact ticker plus effective date, and any unresolved identifier collision makes the affected symbol ineligible and must be surfaced.
3. Ticker-only, timeless joins are not sufficient.

## No fallback / no substitution policy

- There is no silent provider fallback within either role.
- OHLCV may not be mixed across providers.
- Reference-provider fields may not be mixed across providers.
- If the selected reference provider later becomes unavailable or violates the contract, the study becomes `invalid` unless a new contract amendment is pre-registered and approved.

## Candidate reference providers

The locked evaluation order is:

1. Alpha Vantage `LISTING_STATUS` (free endpoint)
2. Massive / Polygon reference tickers under Gary's current entitlement

A third provider is not permitted for this amendment. Alpha Vantage and Massive may not be combined into a composite reference stack.

## Locked historical reference dataset

- Original approved reference dataset: **2022-01-03 through 2025-12-31** (four years).
- Approved fallback reference dataset: **2024-01-02 through 2025-12-31** (two years). This fallback is a fixed methodology amendment. It may be used only if the original 2022–2025 reference contract cannot be satisfied under the current free entitlement. The fallback is not permission to move the start date after observing provider limitations.
- All strategy rules, universe rules, costs, thresholds, sample minimums, validation gates, and holdout discipline remain unchanged for either dataset. Sample minimums are not reduced for the shorter fallback window.

## Amendment status

- This amendment v2 is preserved as a historical audit record. For the latest prospective data-sufficiency methodology, see `docs/research/specs/INTRA-001-data-sufficiency-amendment-v3.json` and `docs/research/INTRA-001-DATA-SUFFICIENCY-AMENDMENT-V3.md`.
- Current amendment at the time of v2: `docs/research/specs/INTRA-001-data-contract-amendment-v2.json`
- Status at the time of v2: `approved_mixed_model_reference_provider_pending` until `INTRA-001B-REFERENCE` selects and locks a reference provider with decision-grade evidence.
- `INTRA-001B-REFERENCE` v2 first-page evidence (`2026-08-07-222404`) is preserved as an audit record but is explicitly not decision-grade; no reference provider is locked by v2.
- `INTRA-001B-REFERENCE-V4` later completed full-pagination live evidence and is recorded in `docs/research/INTRA-001B-REFERENCE-V4.md`.

## What this amendment does NOT do

- It does not authorize any production provider change.
- It does not authorize any change to trading behavior, scores, weights, thresholds, rankings, screeners, alerts, or dashboards.
- It does not begin `INTRA-001C` strategy implementation or the real `INTRA-001` study.
