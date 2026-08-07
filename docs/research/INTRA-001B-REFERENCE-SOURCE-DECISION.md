# INTRA-001B Reference Provider Decision

**Status:** `supported` — Massive/Polygon is selected as the locked reference provider for the `INTRA-001` mixed-provider data contract.

**Task ID:** INTRA-001B-REFERENCE  
**Probe version:** 2 (two-year fallback approved)  
**Selected provider:** `massive`  
**Target entitlement:** current Gary entitlement (free Polygon reference tickers via `api.massive.com`)  
**Dataset used:** original 2022-01-03 through 2025-12-31 PIT dates  
**Reference feed:** `v3/reference/tickers`, `market=stocks`, `locale=us`, `date=YYYY-MM-DD`, `active=true/false`

## Pre-registration and code state

- **Probe spec:** `docs/research/specs/INTRA-001B-reference-probe-v2.json`
- **Pre-registration commit:** `d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299`
- **Final head at run:** `d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299`
- **Branch:** `devin/intra-001b-reference-source`
- **Original strategy spec:** `docs/research/specs/INTRA-001-v1.json` (SHA-256 unchanged)
- **Mixed-provider contract amendment:** `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` / `docs/research/INTRA-001-MIXED-PROVIDER-DATA-CONTRACT.md`
- **Safe artifact bundle:** `docs/research/artifacts/INTRA-001B-REFERENCE/2026-08-07-222404/`

## Candidate evaluation order

1. Alpha Vantage `LISTING_STATUS`
2. Massive / Polygon `v3/reference/tickers`

Alpha Vantage was evaluated first. The configured free API key reached its daily request limit during the probe and `LISTING_STATUS` returned empty `{}` for every PIT date, failing the point-in-time, repeatability, and security-type gates. No paid upgrade was performed. Massive was then evaluated under the locked branching rule and satisfied all mandatory gates for the original four-year PIT dates.

## Locked PIT dates evaluated

- 2022-01-31
- 2023-07-31
- 2024-05-31
- 2025-11-30

All four dates returned active and inactive (delisted) rows without error and with repeatable SHA-256 hashes.

## Mandatory gates

| Gate | Status |
|------|--------|
| PIT date support for all probe dates | Passed |
| Active and inactive/delisted coverage | Passed |
| Security-type exclusions possible | Passed |
| Security-type taxonomy granular | Passed |
| Primary exchange provenance | Passed |
| Reproducible / free under current entitlement | Passed |
| Full repeatability | Passed |
| Historical 2022 entitlement under current plan | Passed |
| No paid upgrade | Passed |
| No composite reference stack | Passed |
| No silent fallback | Passed |

## Security type taxonomy

Massive exposes a `type` field with values including `CS`, `ETF`, `PFD`, `RIGHT`, `UNIT`, and `WARRANT`, which is granular enough to enforce the five exclusions required by `INTRA-001` (OTC, warrant, right, unit, preferred stock). `OTC` was not observed in the first-page samples; any `type` value not in the approved set will be excluded by the membership filter.

## Exchange provenance

The `primary_exchange` field was populated for observed active listings and included `XNYS`, `XNAS`, `ARCX`, `BATS`, and `XASE`.

## What was not approved

- Alpha Vantage `LISTING_STATUS` was not selected because the free entitlement could not complete the required repeated PIT queries for the full four-year probe in this session (daily rate limit / empty responses).
- The two-year fallback dataset (2024-01-02 through 2025-12-31) was not required because the original four-year PIT dates passed under Massive.
- No composite reference stack was built.
- No OHLCV provider mixing was introduced.

## Next step

The mixed-provider data contract is now locked for `INTRA-001`:

- **OHLCV:** Alpaca SIP
- **Reference / security-master:** Massive/Polygon

Implementation of the `INTRA-001C` snapshot construction or the real `INTRA-001` study is not authorized by this research-only probe and must be pre-registered separately.
