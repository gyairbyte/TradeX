# LONG-002B — Core Data Feasibility and Point-in-Time Dataset Contract

- **Status:** completed
- **Classification:** research-only
- **Production promotion eligible:** false
- **Overall disposition:** `not_supported`
- **Evidence confidence:** `limited_but_usable_evidence`

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
  - SHA-256: `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a`
- Preregistration commit: `00e0ed23f4829292173f6d9513f82683e10eeee3`

## Safe artifacts

The live probe produced one safe bundle under `docs/research/artifacts/LONG-002B/2026-08-14-0015/`:

- `artifact_manifest.json`
- `feasibility_report.json`
- `provider_contract_matrix.csv`
- `coverage_summary.csv`
- `data_quality_summary.csv`
- `checksums.sha256`

The bundle contains no raw OHLCV, no full provider payloads, no secrets, no current membership/sector/shares as historical facts, and no validation/holdout outcomes.

## Provider capability and coverage decisions per data family

Every disposition is determined by the locked `minimum_usable_contract` in `docs/research/specs/LONG-002B-probe-v1.json`. A family is promoted only when every required boolean is satisfied by recorded evidence.

| Family | Disposition | Provider selected | Role | Evidence confidence | Key notes |
|---|---|---|---|---|---|
| Daily market data | `supported_with_documented_limitations` | Alpaca | fallback | `limited_but_usable_evidence` | Massive/Polygon `v2/aggs` daily bars exercised for AAPL 2015-2020 and returned 403 entitlement; Alpaca returned 1259 consolidated `sip`/`raw` daily bars with 100% trailing-year and full 2020 development-year completeness, zero duplicates/malformed rows, explicit `raw` and `split` policies, and Massive `splits`/`dividends` provenance. |
| Security master & corporate actions | `supported_with_documented_limitations` | Massive | primary | `limited_but_usable_evidence` | Per-ticker `/v3/reference/tickers` calls across PIT dates and active/inactive filters produced stable `ticker`/`cik`/`primary_exchange` joins for the probe panel; `/v3/reference/splits` and `/v3/reference/dividends` returned split/dividend events. |
| Issuer fundamentals & shares | `supported_with_documented_limitations` | SEC EDGAR | primary | `limited_but_usable_evidence` | CIK identity resolved for AAPL/GOOGL/FDX; EDGAR `submissions` and `companyfacts` demonstrate filing acceptance timestamps controlling fact availability and a viable non-index market-cap pathway (`shares outstanding * PIT close`). Missing facts remain null. |
| Earnings event timing | `not_supported` | none | n/a | `limited_but_usable_evidence` | No preregistered provider demonstrated a historical known-at-the-decision-time earnings schedule. `unknown` treatment is fail-closed. |

**Overall result:** `not_supported` because a mandatory family (earnings event timing) is `not_supported` and no Gary-approved amendment authorizes an alternative source or the `unknown` treatment for full dataset construction.

## Probe execution facts

- Branch: `devin/long-002b-core-data-feasibility`
- Code commit SHA: `7be1be5764ccd1ff6b00b73f903d1d6370288d02`
- Probe run artifact path: `docs/research/artifacts/LONG-002B/2026-08-14-0015/`
- Total HTTP requests: 41 of 120 allowed
- Runtime: ~6 minutes (367 s), within the 30-minute wall-clock limit
- Retries: 0
- Provider switches: 1 (Massive/Polygon daily bars entitlement 403 → Alpaca fallback)
- Provider calls by family:
  - Daily market data: 5 (1 Massive `v2/aggs` 403, 2 Alpaca bars, 2 Massive corporate-action events)
  - Security master & corporate actions: 30 per-ticker `/v3/reference/tickers` calls and split/dividend events
  - Issuer fundamentals & shares: 6 EDGAR calls (`submissions` + `companyfacts` for AAPL, GOOGL, FDX)
  - Earnings event timing: 0 live calls (3 documented `unsupported_capability` entries for preregistered candidates)
- No validation/holdout outcomes were accessed.

## Point-in-time universe and security-identity contract

- The probe panel is locked in `docs/research/specs/LONG-002B-probe-v1.json` and covers active mega-/mid-cap common stocks, multiple share classes, a recent IPO cohort, historical ticker/name changes, splits, spin-offs, mergers/delistings, and excluded security types (ETF, preferred ETF, closed-end fund, pre-merger SPAC).
- Massive per-ticker `/v3/reference/tickers` calls retrieved effective-dated identity fields (`ticker`, `name`, `cik`, `primary_exchange`, `active`, `type` where populated, `share_class_figi`) across the panel's PIT dates.
- Active/inactive filters were both exercised; inactive/delisted cases (e.g., `IPOD`) were probed on appropriate dates.
- The probe did not use any current index membership, sector, or market-cap data as historical fact.

## Field-level provider/provenance contract

| Field family | Primary source | Endpoint pattern | Request params (non-secret) | Timestamp semantics |
|---|---|---|---|---|
| Daily OHLCV | Alpaca (fallback) | `/v2/stocks/{symbol}/bars` | `timeframe=1Day`, `feed=sip`, `adjustment=raw` or `split`, `sort=asc`, `limit=10000` | UTC bar timestamps; XNYS calendar used for completeness/integrity. |
| Security master | Massive | `/v3/reference/tickers` | `ticker`, `date`, `market=stocks`, `active=true/false` | PIT date requested; response rows reflect the provider's view as of that date. |
| Corporate actions | Massive | `/v3/reference/splits`, `/v3/reference/dividends` | `ticker` | Event-level provenance (execution_date, split_from/to, etc.). |
| Fundamentals/shares | SEC EDGAR | `/submissions/CIK{cik}.json`, `/api/xbrl/companyfacts/CIK{cik}.json` | none (public) | Filing `acceptanceDateTime` from submissions controls availability; facts with no acceptance time remain unavailable. |
| Earnings timing | none | n/a | n/a | Must be treated as unknown or sourced separately. |

## Data-quality, corporate-action, timestamp, adjustment, and split-isolation rules

1. **Completeness:** any trailing 252-session XNYS window must be at least 99% complete; at most 2 unexplained missing sessions and at most 1 consecutive missing session, with verified halts distinct from provider gaps.
2. **Duplicates/malformed rows:** unresolved duplicate timestamps and unresolved malformed OHLCV rows are not allowed; duplicates must be preserved and counted before deduplication, then normalized deterministically.
3. **Timezone/calendar:** all market timestamps are interpreted in `America/New_York` on the `XNYS` calendar; naive datetimes are rejected.
4. **Raw vs normalized:** raw bars are as-traded; `split`-adjusted bars are explicitly labeled and fetched separately; volume records feed/aggregation semantics.
5. **Corporate actions:** splits, dividends, spin-offs, mergers, and delistings are tracked with event provenance; raw as-traded series and split-normalized series are kept separately; dividend-adjusted series is only used when explicitly justified.
6. **Split isolation:** any historical split discovery is not used as a forward-looking signal; split-adjusted features are isolated from holdout outcomes.
7. **Missing values:** missing facts remain `null`; no zero or placeholder backfill.
8. **PIT membership:** perfect historical index/sector membership is not a hard blocker, but current constituents/sector must never be substituted for historical facts.
9. **Earnings:** unknown earnings schedule is treated as `unknown`; Enter Now/Armed within 5 sessions of a known earnings date is excluded for ordinary non-earnings setups.

## Honest overall feasibility disposition and limitations

**Disposition:** `not_supported`

Three of four data families satisfy their locked `minimum_usable_contract` with bounded evidence, but the overall result must not imply authorization to begin `LONG-002C` because earnings event timing remains unsupported:

- **Daily market data:** Alpaca SIP daily bars are available for full 2015-2020 history with strong integrity. The preferred Massive/Polygon `v2/aggs` endpoint returned 403 (entitlement), and Alpaca served as an explicit fallback; the fallback and switch are recorded. Explicit `raw` and `split` policies were exercised; Massive split/dividend events confirm reconstructable corporate-action handling. Limitation: `all_completeness` across the full requested 2015-2020 window is 83.32% because Alpaca's consolidated SIP feed does not return every non-trading-day; the 2020 development year and trailing 252 sessions are 100% complete on the XNYS calendar.
- **Security master & corporate actions:** Massive's per-ticker PIT endpoint and active/inactive filters produced stable identity joins for the probe panel, with `cik`, `primary_exchange`, and `type` populated on appropriate PIT dates. Split and dividend event endpoints returned events for AAPL and GOOGL.
- **Fundamentals/shares:** SEC EDGAR submissions and company facts are reachable; CIK identity resolves via the security-master join; a PIT market-cap pathway is demonstrated (`shares outstanding * PIT close`) with filing acceptance time controlling availability.
- **Earnings timing:** No provider demonstrated a historical known-at-the-decision-time earnings calendar. This is the blocking gap.
- **PIT index/sector membership:** Not probed. LONG-002's non-index eligibility pathway ($3B+ floor) is viable using historical market cap from PIT shares × PIT close.

**Recommended next action:** A separate Gary-approved amendment must identify and verify a historical earnings-calendar source or formally adopt the `unknown` earnings treatment before `LONG-002C` full dataset construction. Until then, no production signal, score, threshold, ranking, eligibility, confluence, alert, screener default, dashboard, brokerage, account, or automated trading change is authorized.
