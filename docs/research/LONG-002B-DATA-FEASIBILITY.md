# LONG-002B — Core Data Feasibility and Point-in-Time Dataset Contract

**Status:** completed  
**Classification:** research-only  
**Production promotion eligible:** false  
**Overall disposition:** `supported_with_documented_limitations`  
**Evidence confidence:** `limited_but_usable_evidence`  

## What LONG-002B did

LONG-002B executed a bounded, preregistered provider probe to determine whether the data required by the locked `LONG-002` research contract can be constructed point-in-time correctly. It did **not** build the full historical LONG-002 dataset.

Locked upstream contracts preserved unchanged:

- `docs/research/LONG-002.md` (human-readable contract)
- `docs/research/specs/LONG-002-v1.json` (machine-readable spec)
  - SHA-256: `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5`

## Preregistration

- Probe spec: `docs/research/specs/LONG-002B-probe-v1.json`
  - SHA-256: `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98`
- Data-contract schema: `docs/research/specs/LONG-002B-data-contract-v1.json`
- Preregistration commit: recorded in this branch history (`chore(LONG-002B): preregister probe spec...`)

## Safe artifacts

The live probe produced one safe bundle under `docs/research/artifacts/LONG-002B/2026-08-12-205122/`:

- `artifact_manifest.json`
- `feasibility_report.json`
- `provider_contract_matrix.csv`
- `coverage_summary.csv`
- `data_quality_summary.csv`
- `checksums.sha256`

The bundle contains no raw OHLCV, no full provider payloads, no secrets, no current membership/sector/shares as historical facts, and no validation/holdout outcomes.

## Provider capability and coverage decisions per data family

| Family | Disposition | Provider selected | Role | Evidence confidence | Key limitation / blocker |
|---|---|---|---|---|---|
| Daily market data | `supported_with_documented_limitations` | Alpaca | fallback | `limited_but_usable_evidence` | Massive/Polygon daily bars endpoint not directly exercised; only one as-of date per probe symbol; full 2015-2025 coverage not proven; `sip`/`iex` feed semantics and `raw`/`split_adjusted` policy require further verification. |
| Security master & corporate actions | `supported_with_documented_limitations` | Massive | primary | `limited_but_usable_evidence` | Active/inactive PIT snapshot retrieved; split/dividend/merge endpoints not probed; ticker-to-identity join demonstrated for active panel. |
| Issuer fundamentals & shares | `supported_with_documented_limitations` | SEC EDGAR | primary | `limited_but_usable_evidence` | CIK resolution depends on the security-master pass; filing acceptance timestamps and XBRL facts are available; full point-in-time fact pipeline needs a build-phase. |
| Earnings event timing | `not_supported` | none | n/a | `invalid_evidence` | No provider demonstrated a historical known-at-the-decision-time earnings schedule. A future LONG-002 build may need to treat earnings dates as `unknown` or use a separate approved source. |

## Probe execution facts

- Starting `main` SHA: `cc30788ac191289548538c3ebdac4b8eae25651d`
- Branch: `devin/long-002b-core-data-feasibility`
- Probe run artifact path: `docs/research/artifacts/LONG-002B/2026-08-12-205122/`
- Total HTTP requests: 24 (well under the 120 budget)
- Runtime: within the 30-minute wall-clock limit
- Provider calls:
  - Alpaca: 12 (one per probe symbol, `1Day` bars, `sip` feed, `raw` adjustment)
  - Massive: 6 active PIT reference snapshots across two dates (up to 3 pages each)
  - SEC EDGAR: 6 (`submissions` + `companyfacts` for the first four panel symbols)
- Retries: only transient `Timeout`/`ConnectionError` are retried once; no retry for auth, entitlement, config, malformed, or unsupported failures.
- No silent provider switching occurred.
- No validation/holdout outcomes were accessed.

## Point-in-time universe and security-identity contract

- The probe panel is locked in `docs/research/specs/LONG-002B-probe-v1.json` and covers active mega-/mid-cap common stocks, multiple share classes, a recent IPO cohort, historical ticker/name changes, splits, spin-offs, mergers/delistings, and excluded security types (ETF, preferred ETF, closed-end fund, pre-merger SPAC).
- Massive active PIT snapshots returned stable `ticker`, `name`, `type` (`CS` for common stock), `primary_exchange`, and `cik` fields for probe symbols on the dates queried.
- Effective ticker-to-identity join is feasible via Massive `cik` + exchange/ticker, with the caveat that historical inactive/delisted symbols may need an inactive snapshot or a `date`-constrained query.
- The probe did not use any current index membership, sector, or market-cap data as historical fact.

## Field-level provider/provenance contract

| Field family | Primary source | Endpoint pattern | Request params (non-secret) | Timestamp semantics |
|---|---|---|---|---|
| Daily OHLCV | Alpaca (fallback) | `/v2/stocks/{symbol}/bars` | `timeframe=1Day`, `feed=sip`, `adjustment=raw`, `sort=asc`, `limit=1000` | UTC bar timestamps; `America/New_York`/`XNYS` calendar interpretation is the caller's responsibility. |
| Security master | Massive | `/v3/reference/tickers` | `market=stocks`, `locale=us`, `date={pit_date}`, `active=true/false` | PIT date requested; response rows reflect the provider's view as of that date. |
| Fundamentals/shares | SEC EDGAR | `/submissions/CIK{cik}.json`, `/api/xbrl/companyfacts/CIK{cik}.json` | none (public) | Filing `acceptance-datetime` from submissions controls availability; facts with no acceptance time remain unavailable. |
| Earnings timing | none | n/a | n/a | Must be treated as unknown or sourced separately. |

## Future full-dataset manifest schema

`docs/research/specs/LONG-002B-data-contract-v1.json` defines the manifest schema a future LONG-002 dataset build must produce. It records:

- `dataset_id`, `schema_version`, locked spec hashes, code commit SHA, `generated_at`.
- Per-field-family provider, role, endpoint, non-secret request parameters, retrieval and as-of timestamps.
- Requested/actual coverage windows, timezone (`America/New_York`), exchange calendar (`XNYS`).
- Immutable issuer/security identity, effective ticker mapping, security type/exchange.
- Corporate-action provenance, raw vs normalized policy, adjustment/volume policy.
- Per-file hashes, row counts, schemas.
- Missing/duplicate/malformed/exclusion counts, provider failures/fallbacks, limitations, evidence confidence.
- Split-boundary holdout safeguard and proof that current membership/classification was not backfilled.

## Data-quality, corporate-action, timestamp, adjustment, and split-isolation rules

1. **Completeness:** any trailing 252-session window must be at least 99% complete; at most 2 unexplained missing sessions and at most 1 consecutive missing session, with verified halts distinct from provider gaps.
2. **Duplicates/malformed rows:** unresolved duplicate timestamps and unresolved malformed OHLCV rows are not allowed; duplicates must be preserved and counted before deduplication, then normalized deterministically.
3. **Timezone/calendar:** all market timestamps are interpreted in `America/New_York` on the `XNYS` calendar; naive datetimes are rejected.
4. **Raw vs normalized:** raw bars are as-traded; normalized/feed bars must be explicitly labeled; volume must record feed/aggregation semantics.
5. **Corporate actions:** splits, dividends, spin-offs, mergers, and delistings are tracked with event provenance; raw as-traded series and split-normalized series are kept separately; dividend-adjusted series is only used when explicitly justified.
6. **Split isolation:** any historical split discovery is not used as a forward-looking signal; split-adjusted features are isolated from holdout outcomes.
7. **Missing values:** missing facts remain `null`; no zero or placeholder backfill.
8. **PIT membership:** perfect historical index/sector membership is not a hard blocker, but current constituents/sector must never be substituted for historical facts.
9. **Earnings:** unknown earnings schedule is treated as `unknown`; Enter Now/Armed within 5 sessions of a known earnings date is excluded for ordinary non-earnings setups.

## Honest overall feasibility disposition and limitations

**Disposition:** `supported_with_documented_limitations`

The core data families required by LONG-002 are *provisionally feasible* with the providers exercised in this probe, but several documented limitations must be addressed before a full historical dataset can be built:

- **Daily market data:** Alpaca SIP daily bars are available and return split-raw consolidated data, but the probe did not exercise the preferred Massive/Polygon daily-bar endpoint and did not verify full 2015-2025 coverage or the exact split-adjustment behavior. The `1Day` bar semantics for pre/post-split dates and volume need a dedicated build-phase verification.
- **Security master:** Massive's active PIT snapshot is viable for active symbols as of a given date, but split/dividend/merge/corporate-action endpoints were not probed. A full build must verify those endpoints or source them from EDGAR/alternative records.
- **Fundamentals/shares:** EDGAR submissions and company facts are reachable with a compliant user agent. CIK resolution can be derived from Massive's security master, but the full pipeline to translate XBRL facts into point-in-time shares outstanding and fundamentals requires a separate build phase.
- **Earnings timing:** No provider in the bounded probe demonstrated a historical known-at-the-decision-time earnings calendar. This is the clearest gap. LONG-002 must either (a) treat earnings as `unknown` with an exclusion window, or (b) seek a Gary-approved separate probe for a historical earnings calendar source.
- **PIT index/sector membership:** Not probed. LONG-002's non-index eligibility pathway ($3B+ floor) is viable using historical market cap from PIT shares × PIT close.

**Recommended next action:** Before building the full LONG-002 historical dataset, a separate Gary-approved amendment should identify and verify a historical earnings-calendar source or formally adopt the `unknown` earnings treatment, and the Massive/Polygon daily-bar endpoint should be exercised under the same bounded-probe discipline. Until then, no production signal, score, threshold, ranking, eligibility, confluence, alert, screener default, dashboard, brokerage, account, or automated trading change is authorized.
