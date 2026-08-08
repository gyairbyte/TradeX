# INTRA-001B-REFERENCE-V4 Reference Provider Decision

**Formal V4 disposition:** `unsupported`. Massive/Polygon completed full pagination for all 12 monthly PIT snapshots under Gary's current free entitlement, but it did not satisfy the pre-registered mandatory data-contract gates. No paid upgrade, composite reference stack, or additional provider probe is introduced.

## Why V4 is unsupported

The V4 live probe verified that the cursor-validation and disposition fixes work:

- Massive `/v3/reference/tickers` returned complete active and inactive snapshots for every monthly PIT date in the 2025-08-31 through 2026-07-31 window.
- Pagination reached terminal `next_url=null`, with a maximum of 14 active pages and 24 inactive pages per snapshot.
- All snapshots were repeated once; repeat hashes matched.
- Ticker Types endpoint returned a stable taxonomy mapping (SHA-256 `6ad7ecf9f4334c8f1838f6135fc271109cbd5afe0c0ddd76c422a6d48d68fccc`).
- Security-type exclusions for warrant, right, unit, and preferred stock passed.

Two mandatory gates failed:

1. **`otc_exclusion`:** Massive's US `stocks` taxonomy and exchange set do not surface an explicit OTC marker. The API's `market=stocks`/`locale=us` filter returned only listed-exchange securities (`XNYS`, `XNAS`, `ARCX`, `BATS`, `XASE`, `XBOS`), but the pre-registered gate requires explicit evidence that OTC securities can be excluded. The gate therefore did not pass.
2. **`duplicate_symbol_behavior_and_resolution`:** Inactive snapshots contained duplicate ticker occurrences (302 across the 12-month window, 5 unresolved). Some historical inactive tickers map to multiple records without a consistent `cik`, `figi`, or `composite_figi`, so deterministic symbol identity is not guaranteed for those cases.

Because the data contract requires deterministic symbol identity and an explicit OTC exclusion path, Massive/Polygon cannot be locked as the authoritative reference provider under the current free entitlement for V4's pre-registered gates. No strategy rules, `INTRA-001-v1.json`, or production trading logic change as a result of this disposition.

## V4 audit lock points

- **v1 pre-registration commit:** `e4d123e5ecca80ab8ba1fa09ff397d4f0a3d67dc`
- **v2 pre-registration commit:** `d5b2ba5d14151fd007c89cc5fc9c6ae7fec6f299`
- **v3 pre-registration commit:** `03e61700dbf2fd072fc36bb63764dc7fa3876281`
- **v4 pre-registration commit / live run head:** `27b111c0c9cc0adb21ef82dd9d2f0699e55e297f`
- **Starting main SHA:** `8405ca77569b55f460a381555843842fe55e248a`
- **Branch:** `devin/intra-001b-reference-v3`
- **v4 safe artifact bundle:** `docs/research/artifacts/INTRA-001B-REFERENCE-V4/2026-08-08-062051/`
- **Original strategy spec:** `docs/research/specs/INTRA-001-v1.json`
- **Original strategy spec SHA-256:** `09394d038928433529ec4c5f5ba5ff0392c764d5b59f1af71d95f4f3957c0464`
- **V4 probe spec:** `docs/research/specs/INTRA-001B-reference-probe-v4.json`
- **V4 decision:** `docs/research/artifacts/INTRA-001B-REFERENCE-V4/2026-08-08-062051/decision.json`

## V4 provider evidence summary

- **Alpha Vantage** evidence from V3 was reused; `LISTING_STATUS` returned empty `{}` messages for all attempted PIT dates. It was not selected.
- **Massive/Polygon** was probed first under the V4 pre-registered candidate order.
- **HTTP/429/cursor errors:** 0 errors, 0 `429` throttling responses, no repeated cursors or cycles detected across the live run.
- **Total Massive HTTP page requests:** 868 (first-pass + repeat for all 12 active and 12 inactive snapshots).
- **Repeatability:** All 24 first-pass observations had matching repeat-pass raw SHA-256 hashes.
- **Gate matrix:** See `decision.json` and `report.md` in the safe artifact bundle. Mandatory gates `otc_exclusion` and `duplicate_symbol_behavior_and_resolution` did not pass. `historical_2022_entitlement_under_current_plan` and `feasible_for_all_48_monthly_pit_snapshots` were recorded as not required.
- **48-month semantics:** `feasible_for_all_48_monthly_pit_snapshots` is `false` because the 48-month PIT window was not probed and 2022-2023 entitlement is explicitly not required for V4. The `estimated_48_month_pagination_cost` capability row reports an extrapolated 1,824-call / 22,070-second pagination cost as an information-only estimate, separate from gate pass/fail status.

## Amendment status

- `docs/research/specs/INTRA-001-data-contract-amendment-v2.json` is updated to `approved_mixed_model_blocked_reference_source`.
- `reference_provider` remains unset (`null`). Massive/Polygon is not locked for the reference/security-master role.

## What does not change

- `INTRA-001-v1.json` and its SHA-256 are untouched.
- No production provider behavior, `SUPPORTED_OHLCV_PROVIDERS`, `tradex/data/fetcher.py`, scores, weights, thresholds, rankings, screeners, alerts, or dashboards change.
- No paid upgrade, no third reference provider, and no Alpha Vantage + Massive composite stack is introduced.
- The fallback dataset is not invoked because the failures are structural data-contract failures, not historical-depth or entitlement limitations.

## Next steps (require explicit approval)

Any continuation of reference-provider work (`INTRA-001B-REFERENCE-V5` or a paid/entitlement change) requires a new Gary approval and a new pre-registered probe. `INTRA-001C` snapshot construction and production promotion remain blocked until a valid reference-provider decision is achieved.
