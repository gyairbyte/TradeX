# LONG-002B-AMEND-001: Blocked Data-Family Resolution

## Purpose

This amendment probes the two families that blocked `LONG-002B` from an overall `supported` disposition:

1. **Security identity, lifecycle, and exclusion classification** — stable PIT identity, effective-dated ticker/listing history, active/inactive/renamed/merged/delisted securities, exchange/listing provenance, and defensible classification for the locked `LONG-002` exclusions.
2. **Earnings-event timing** — historical earnings dates as they were known at the `LONG-002` decision timestamp, with separation among future schedule, subsequent revisions, actual release, and SEC filing/disclosure timestamps.

`LONG-002B-AMEND-001` is research-only and does not authorize `LONG-002C`.

## Upstream specifications

| Spec | Path | SHA-256 |
|------|------|---------|
| `LONG-002-v1.json` | `docs/research/specs/LONG-002-v1.json` | `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5` |
| `LONG-002B-probe-v1.json` | `docs/research/specs/LONG-002B-probe-v1.json` | `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98` |
| `LONG-002B-data-contract-v1.json` | `docs/research/specs/LONG-002B-data-contract-v1.json` | `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a` |

## Preregistered providers

### Security identity, lifecycle, and exclusion classification

- **Preferred:** `massive` (`v3/reference/tickers/{ticker}`, `v3/reference/tickers/types`, `vX/reference/tickers/{id}/events`, `v3/reference/splits`, `v3/reference/dividends`).
- **Fallback 1:** `alpaca` (`assets` and corporate-actions endpoints).
- **Fallback 2:** `sec_edgar` (`submissions/CIK{cik}.json`).

### Earnings-event timing

- **Preferred:** `massive` (`v3/reference/tickers/{ticker}`, `vX/reference/financials`, `vX/reference/tickers/{id}/events`).
- **Fallback 1:** `sec_edgar` (submissions and filing-index metadata).
- **Fallback 2:** `yahoo_earnings_calendar` (current/prospective diagnostics only).

## Minimum usable contracts

### Security identity, lifecycle, and exclusion classification

A `supported` or `supported_with_documented_limitations` disposition requires all of the following for the probe panel:

- `stable_identity_effective_ticker_join_for_probe_panel`
- `active_inactive_lifecycle_evidence_for_probe_panel`
- `ticker_change_or_rename_evidence_for_probe_panel`
- `exchange_and_listing_provenance_for_probe_panel`
- `defensible_exclusion_classification_for_probe_panel`
- `corporate_action_provenance_for_splits_and_dividends`

The exclusion-classification contract is **not** satisfied by nonempty generic fields such as `CS` or `INDEX`. The evidence must demonstrate a provider-specific, defensible mapping to each locked `LONG-002` exclusion category.

### Earnings-event timing

A supported disposition requires:

- `historical_known_at_time_schedule`
- `distinguishes_future_schedule_known_at_time`
- `distinguishes_subsequent_revisions`
- `distinguishes_actual_release_timestamp`
- `separates_sec_filing_timestamp_from_schedule`
- `unknown_treatment_fail_closed`

If no source demonstrates a historical known-at-time schedule, the family remains `not_supported` and the amendment produces a decision memo comparing:

1. Continuing to block `LONG-002C`.
2. A formally fail-closed `unknown` treatment.
3. A future Gary-approved provider amendment.

The `unknown` treatment is **not** adopted automatically.

## Budget and stop conditions

- Maximum 120 HTTP requests across the amendment.
- Maximum 30 minutes runtime.
- One retry for transient failures only.
- No retries for authentication, entitlement, configuration, malformed-response, or unsupported-capability failures.
- Stop investigating a family once its minimum usable contract is satisfied.
- Uncalled capabilities are recorded as `unverified`, not as attempted provider failures.

## Probe panel

The amendment reuses the locked `LONG-002B` probe panel (≤12 securities, ≤4 as-of dates each). See `docs/research/specs/LONG-002B-probe-v1.json` for the full panel and category rationale.

## Prohibitions

This amendment does **not**:

- Modify `LONG-002-v1.json`.
- Build the full `LONG-002` dataset.
- Begin `LONG-002C`.
- Calculate targets, forward returns, MFE/MAE, clean-target labels, adverse rates, KPIs, baselines, or model performance.
- Perform feature discovery, chart review, model fitting, trigger research, threshold search, or validation/holdout evaluation.
- Access brokerage or account data.
- Change production signals, scores, weights, thresholds, rankings, eligibility, alerts, dashboards, or trading behavior.
- Add dashboards, brokerage, or automated-trading functionality.
- Merge its own PR.

## Safe deliverables

- Human-readable amendment/feasibility report (`docs/research/LONG-002B-AMEND-001.md`).
- Machine-readable locked amendment probe specification (`docs/research/specs/LONG-002B-AMEND-001-probe-v1.json`).
- Machine-readable result/report in the safe artifact bundle.
- Provider-contract matrix.
- Coverage and data-quality summaries.
- Artifact manifest and checksums.
- Deterministic tests.
- Minimal `README.md`, `CLAUDE.md`, and `docs/PROJECT-TRACKER.md` synchronization.

Safe artifacts must contain no secrets, authorization headers, raw licensed payloads, raw OHLCV, absolute local paths, validation/holdout outcomes, or personally identifying account information.

## Results

- **Branch:** `devin/long-002b-amend-001-blocker-resolution`
- **Starting `main` SHA:** `75a37e872afc7a5d14c349bbed2a4db935b88608`
- **Preregistration commit SHA:** `75fad17b190d4879d26dd7de6b61241672193f08`
- **Code commit SHA used for live probe:** `53643572303df7006610d04381200680809bab77`
- **Amendment probe spec SHA-256:** `38f550b3bf14bc58654ba5286213bbfe894577ccb1502b604f60076e6e239ce7`
- **Upstream `LONG-002-v1.json` SHA-256:** `f3df2845543500985c88568f9b855812576e9e4a10901f8a5f7a1834a319b3b5`
- **Upstream `LONG-002B-probe-v1.json` SHA-256:** `002a0795096ba0f6f77ba1f2e673b5d3e6a2008730a57f7f87e71cf86b949a98`
- **Upstream `LONG-002B-data-contract-v1.json` SHA-256:** `f8ad6655e482fe5c9e8847467643bf0b03949686ad914180599323758cbf555a`
- **Overall amendment disposition:** `not_supported` (security identity and earnings-event timing both remain blocked; LONG-002C is not authorized)
- **Security identity, lifecycle, and exclusion classification:** `not_supported`
  - Provider: `massive` (role `partial`)
  - Endpoints: `v3/reference/tickers/{ticker}`, `v3/reference/tickers/types`, `vX/reference/tickers/{id}/events`, `v3/reference/splits`, `v3/reference/dividends`
  - No fallback providers were exercised.
  - The probe panel contained multiple `(symbol, as_of_date)` rows whose `type` was `None`, `CS`, or `INDEX` with no corroborating PIT name/SIC evidence; those historical rows fail closed to `unknown` and prevent the minimum exclusion-classification contract from being satisfied.
  - PFF is correctly classified as `ETF` (preferred-stock strategy); SPY is correctly classified as `ETF`; IGR is correctly classified as `closed_end_fund`; IPOD is correctly classified as `pre_merger_spac`; the failing rows are unresolved historical ones, not the decision-date row substituted as historical fact.
- **Earnings-event timing:** `not_supported`
  - Provider: `massive` (primary)
  - `vX/reference/financials` returns XBRL financial statements with `filing_date` and `period_of_report_date` only; it does not expose a historical known-at-the-decision-time earnings schedule.
  - Fallbacks `sec_edgar` and `yahoo_earnings_calendar` were not exercised and are recorded as `unverified` with `request_count=0`. The report explicitly states that provider search was not exhausted.
- **HTTP requests:** 64 of 120
- **Retries:** 0
- **Provider switches:** 0
- **Runtime:** ~751 seconds (~12.5 minutes)
- **Safe artifact bundle:** `docs/research/artifacts/LONG-002B-AMEND-001/2026-08-16-222647/`

## Decision memo: earnings-event timing

No preregistered endpoint satisfied the `historical_known_at_time_schedule` contract. The amendment therefore produces a separated decision memo and does **not** adopt any option automatically:

1. **Continue blocking `LONG-002C`** until a provider demonstrates historical known-at-time earnings schedules.
2. **Formally adopt a fail-closed `unknown` treatment** for earnings dates at the `LONG-002` decision timestamp; this requires a Gary/ChatGPT methodology decision.
3. **Request a future Gary-approved provider amendment** targeted at a historical earnings-calendar source.

The current branch records the blocker and preserves the fail-closed default; it does not silently treat earnings dates as `unknown`.

## Limitations

- The evaluator evaluates every `(symbol, as_of_date)` PIT row independently; unresolved historical rows with generic or missing `type` codes (`None`, `CS`, `INDEX`) and no corroborating name/SIC signal remain `unknown` and fail closed. Later or current rows are never substituted as historical fact.
- A missing ticker or event response (HTTP 404) is not treated as lifecycle evidence. The evaluator requires positive, effective-dated lifecycle or identity-link evidence such as an explicit `active: false`, `delisted_utc`, or `ticker_change` record.
- The `vX/reference/tickers/{id}/events` endpoint supports `ticker_change` events; spin-off, merger, and delisting metadata are only inferred from those `ticker_change` records, not from 404s.
- Earnings-event timing has no identified historical PIT schedule source within the preregistered provider set; the SEC EDGAR and Yahoo earnings-calendar fallbacks were not evaluated within the locked budget.
