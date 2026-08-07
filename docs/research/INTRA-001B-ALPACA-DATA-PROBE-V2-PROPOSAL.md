# INTRA-001B-ALPACA v2 Probe Proposal

**Status:** Proposed — pending approval.  
**Scope:** Locked to the same provider, symbols, windows, feeds, thresholds, and research-only boundary as v1. Only the probe implementation and audit artifacts change.

## 1. Purpose

The v1 live Alpaca probe produced strong empirical evidence that Alpaca Basic/free historical SIP can supply 2022-01-03 through 2025-12-31 five-minute OHLCV for the locked symbol set. However, a post-run audit found material defects in the v1 probe implementation (see `docs/research/INTRA-001B-ALPACA-DATA-PROBE.md` section 0). This document proposes a bounded v2 probe that corrects those defects without changing the locked research question, provider, symbols, date ranges, feeds, thresholds, or production behavior.

## 2. What v2 does not change

- `docs/research/specs/INTRA-001-v1.json` (strategy spec) — unchanged.
- `docs/research/specs/INTRA-001B-alpaca-probe-v1.json` — unchanged (it remains the v1 lock).
- Provider: Alpaca Basic/free.
- Symbols: `SPY`, `AAPL`, `JPM`.
- Date ranges: full 2022-01-03 through 2025-12-31, bounded windows 2022-02, 2023-08, 2024-06, 2025-12, overlap 2024-06.
- Feeds: `sip` (candidate), `iex` (comparison).
- `timeframe=5Min`, `adjustment=raw`, `asof=2025-12-31`, `sort=asc`, `limit=10000`, request delay 0.5s.
- Coverage, duplicate, and zero-volume thresholds.
- No production trading-behavior changes.

## 3. What v2 corrects

### 3.1 Timestamp semantics

- `_classify_timestamp_semantics` will use the same eligible regular-session grid used by `_analyze_request` (exclude the 16:00 close timestamp from regular-session semantics classification).
- The function will return `bar_start`, `bar_end`, `undetermined`, or `ambiguous`.
- `bar_end` or `ambiguous` for the candidate feed will be an approval blocker for `approved_for_intra_001_five_minute_ohlcv`.
- The v2 report will explicitly document whether Alpaca SIP 5Min bars are bar-start or bar-end.

### 3.2 Pagination gating and `pagination_summary.csv`

- `_record_passes` will require `pagination_complete == True`, `repeated_page_token == False`, and `pagination_cycle_detected == False`.
- Repeatability rows will include `pagination_complete`, `page_count`, and `next_page_token_present` for both repetitions, and a mismatch will fail the repeat.
- The v2 safe bundle will include `pagination_summary.csv` with per-request page count, token sequence, and a deterministic page-token hash.
- Page-level counts and token-sequence hashes will be retained in the private provider output.

### 3.3 Independent direct and chunked capability booleans

- `_build_decision` will compute `direct_full_range_supported` and `chunked_historical_windows_supported` independently.
- Selection policy still prefers `direct_full_range` when available, but both may be `true`.
- A focused test will assert both booleans can be `true` simultaneously.

### 3.4 Evidence-aligned provider-contract conclusions

- `point_in_time_universe_supported` will be `false` unless the probe explicitly demonstrates historical beginning-of-month 2022-2025 universe reconstruction. The active `GET /v2/assets` snapshot will be recorded as evidence for current listing only.
- `inactive_asset_listing_supported` will require an actual `GET /v2/assets?status=inactive` call and HTTP 200.
- `delisted_symbol_handling_supported` will remain `false` because `asof` only maps current-to-historic symbols at a single date; it does not reconstruct a historical security master.
- `corporate_action_endpoint_supported` will be recorded as `true` for endpoint reachability only, but it will not by itself satisfy the complete-provider positive path.
- `consolidated_volume_supported` will be derived from the `sip` feed returning volume, but `remaining_volume_provenance_disclosure_required` will stay `true` until the probe distinguishes consolidated SIP volume from venue-specific IEX volume with paired diagnostics.
- `no_provider_mixing_contract_satisfied` will be renamed/separated into two fields: `probe_did_not_mix_providers` (true — this probe uses Alpaca only) and `single_provider_contract_satisfied` (false until all dimensions are proven).

### 3.5 Complete-provider matrix and SIP/IEX comparator

The v2 provider-contract matrix will have rows for:
- five-minute OHLCV/history
- consolidated vs. venue-specific volume (with timestamp-overlap percentage, total volume by feed, median paired-bar `IEX/SIP` volume ratio, and OHLC difference flag)
- timestamp convention (bar-start vs. bar-end)
- adjustment/corporate actions
- symbol changes / `asof` mapping
- inactive/delisted symbol access
- point-in-time active universe (monthly PIT reproducibility)
- stock vs. ETF / warrant/right/unit/preferred classification
- historical security-type provenance
- current/inactive master coverage
- no-provider-mixing statement
- manifest feasibility

Each row will distinguish `live_evidence`, `documented_capability`, and `unproven`.

### 3.6 No regression of Schwab probe

- `_build_decision` will preserve PR #40 Schwab semantics: a passing Schwab OHLCV probe will not automatically become a complete INTRA source.
- Schwab spec validation will remain strict; Alpaca-specific optional fields will default safely and not loosen Schwab required fields.
- The existing Schwab tests will continue to pass unchanged.

### 3.7 Locked audit contract

- `probe_spec.lock.json` will either contain the exact raw pre-registered bytes or an explicit `raw_spec_sha256` plus a normalized representation labeled as derived.
- The v2 safe bundle will include `pagination_summary.csv` and `report.md` (if the report writer is committed to the bundle).
- Zero-volume and invalid-OHLC thresholds will be computed over the candidate regular-session expected-grid bars, not the entire response. Extended-hours quality will be reported separately.

## 4. v2 pre-registration plan

1. Create `docs/research/specs/INTRA-001B-alpaca-probe-v2.json` (or a v2 section of this proposal) with the same research parameters and new implementation/version fields.
2. Update `tradex/research/intraday_data_probe/` implementation to address sections 3.1–3.7 above.
3. Add/extend credential-free tests for timestamp semantics, pagination gating, independent direct/chunked booleans, provider-contract evidence alignment, and Schwab non-regression.
4. Commit the v2 pre-registration before any live Alpaca calls.
5. Re-run the live Alpaca probe only after pre-registration is approved.

## 5. Expected safe artifact bundle

- `README.txt`
- `artifact_manifest.json`
- `checksums.sha256`
- `probe_spec.lock.json`
- `strategy_spec_reference.json`
- `request_audit.csv`
- `pagination_summary.csv`
- `coverage_summary.csv`
- `repeatability_summary.csv`
- `chunk_overlap.csv`
- `feed_comparison.csv`
- `provider_contract_matrix.csv`
- `decision.json`
- `report.md`

## 6. Disposition criteria

After v2 live execution, the probe can produce one of the locked outcomes:
- `supported_complete` only if all contract rows and OHLCV thresholds are satisfied on the single provider.
- `supported_ohlcv_only` only if timestamp semantics are resolved, pagination is complete, direct/chunked support is independently true, and the remaining contract rows are documented as unsupported.
- `not_supported` if OHLCV coverage fails.
- `inconclusive` if repeatability, overlap, or contract evidence is contradictory.
- `invalid` if the probe implementation itself violates its own gating rules.

## 7. No live Alpaca calls until approved

This proposal does not trigger any live provider requests. It is a scope document for review before v2 pre-registration and live execution.