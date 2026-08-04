# PATTERN-001 Sanitized Safe-Handoff Artifacts

This directory contains the sanitized aggregate safe-handoff bundle from the locked local Schwab study for PATTERN-001 (`devin/validate-pattern-matcher`, PR #23). It is documentation and evidence only; it does not include raw OHLCV data, credentials, or row-level signal/trade artifacts.

## Location

```text
docs/research/artifacts/PATTERN-001/2026-08-03-9ea40e85/
```

The date prefix reflects the local run date. The suffix `9ea40e85` is the first eight characters of the snapshot `manifest.lock.json` canonical SHA-256.

## What is included

The extracted safe-handoff bundle contains only the aggregate research artifacts:

- `README.txt` — bundle provenance and workflow identifiers
- `artifact_manifest.json` — deterministic SHA-256 checksums for the research artifact set
- `baseline_comparison.csv` — pooled and per-ticker baseline-lift comparison
- `data_quality.csv` — per-ticker data-quality summary from the snapshot validation
- `development_fingerprints.json` — aggregated fingerprint statistics for run-up and decline events
- `manifest.lock.json` — snapshot manifest with provenance and per-ticker file metadata (no raw bar data)
- `period_summary.csv` — aggregate period-level metrics for development, validation, and holdout
- `promotion_decision.json` — final evidence classification and gate results
- `report.md` — human-readable study report
- `study_spec.lock.json` — exact locked study specification
- `ticker_summary.csv` — per-ticker metric summary

## What is excluded

Consistent with the PATTERN-001 safe-handoff rules, this repository copy does **not** contain:

- Raw OHLCV files
- `study.json`
- `observations.csv`
- `qualifying_signals.csv`
- `frequency_matched_controls.csv`
- `event_study.csv`
- `executable_trades.csv`
- OAuth tokens
- `.env` files
- Credentials
- Authorization headers
- Raw provider responses
- Account, position, transaction, or order data

The `artifact_manifest.json` still lists hashes for some of the intentionally excluded files because it was generated from the full local result directory.

## Verified identifiers

| Identifier | Value |
|---|---|
| ZIP SHA-256 | `b0171d7e221c4e21e808eca0ffa27dba30d7ef7a835598133c3ef63cd1e5e424` |
| Study-spec SHA-256 | `68a3d59cf4b06f21889207dde67e217d2a61916ec7c331adb9fe629c521bf8c7` |
| Manifest SHA-256 | `9ea40e85d3c2388ec33f582988a79e66b8f0e5d18a04800c714db358db3080ef` |
| Ordered-universe SHA-256 | `554c6933750be1f10716ce45912e70ff6c963cc190157f730ef1d7ddbd850404` |
| Provider | `schwab` |
| Date range | `2018-01-02` through `2026-07-31` |
| Requested / successful / failed tickers | `44 / 44 / 0` |
| Validated daily bars | `90,825` |
| Invalid OHLC rows removed | `13` across `12` tickers |
| Duplicate timestamps | `0` |
| Missing required values | `0` |
| Bars outside requested range | `0` |

## Development fingerprints

| Event type | Events | Tickers | Fingerprint SHA-256 |
|---|---|---|---|
| Run-up | `274` | `41` | `dfda89180393330da667f005db90cb1d0b49e80b37ea6a4982b13ab9030661e9` |
| Decline | `322` | `42` | `35c632dcb4b5f245851c111dfb05c3a8d1cf6633c07741f89a54e273ed3e3ba1` |

## Locked-study results at 10 bps per side

### Run-up

| Split | Signals | Tickers | Mean net return | Lift | Lift CI |
|---|---|---|---|---|---|
| Validation | `170` | `42` | `-0.071576%` | `+7.072294 bps` | `[-95.613019, 123.821956]` |
| Holdout | `234` | `44` | `+0.258650%` | `+10.238333 bps` | `[-103.220270, 124.515187]` |
| Classification | `rejected` | | | | |

### Decline

| Split | Signals | Tickers | Mean signed net return | Lift | Lift CI |
|---|---|---|---|---|---|
| Validation | `1,816` | `43` | `-1.343259%` | `-98.634383 bps` | `[-151.294198, -45.900568]` |
| Holdout | `2,341` | `44` | `-0.979449%` | `-21.393567 bps` | `[-54.078555, 12.556656]` |
| Classification | `rejected` | | | | |

## Overall decision

- **Overall classification:** `rejected`
- **Run-up classification:** `rejected`
- **Decline classification:** `rejected`
- **`production_promotion_eligible`:** `false`
- **`research_test_mode`:** `false`

## Product decisions

- Keep automatic pattern-match alerts disabled.
- Keep the dashboard Pattern Similarity tab and the matcher output labeled as experimental/non-predictive research.
- Do not add pattern similarity to production scoring, ranking, eligibility, or confluence.
- Do not tune the matcher weights, thresholds, profiles, event definitions, lookbacks, holding periods, or universe from these results.
- Do not introduce an automatic inversion or alternative strategy; that would be a new hypothesis requiring a separate approved study.

## Limitations

- The universe is the fixed `MINING_UNIVERSE` convenience cohort from `tradex/patterns/miner.py`; it is not a point-in-time S&P 500 or Nasdaq-100 universe, and survivorship/selection bias are present.
- The study uses provider-returned daily candles as-is with `adjustment_policy="provider_default"`; no additional split/dividend adjustment is applied, and Schwab's exact corporate-action methodology is not independently verified.
- Execution assumptions are next-open entry and fifth-session close; borrow availability, borrow fees, stop/target orders, and slippage beyond the modeled bps are not represented.
- The safe bundle is aggregate; it cannot independently reproduce every row-level calculation without the external raw snapshot, which is excluded for credential and privacy safety.

## Provenance

- Reviewed exact PR head: `6035a7d7e4c7b4c31eb2c5bad34d809a0ce559e0`
- Base `main`: `f283ce6b9ae9c48e19579fb7263c613d03e9d126`
- GitHub Actions workflow run: `30859972042`
- CI `test` job: `91839590312`
- Tested merge ref: `de7687eb8500eeff84606a1c3ed03fa1f82f499f`
- Local run date: `2026-08-03`
