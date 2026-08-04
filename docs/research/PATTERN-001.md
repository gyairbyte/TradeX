# PATTERN-001 — Pattern-similarity validation study

## Purpose

This document describes the locked, point-in-time research study that evaluates whether the existing `tradex/patterns/matcher` Pearson-similarity output has predictive value for signed five-session returns. The study is **research-only** and is deliberately quarantined from production scoring, ranking, eligibility, and automatic alerts.

## What is being measured

- For the fixed `MINING_UNIVERSE` from `tradex/patterns/miner.py`, historical run-up and decline events are mined from the development split only.
- One immutable fingerprint per event type is built from those development events.
- Validation and holdout decision dates are scored against the development fingerprint using the exact production weighted-Pearson similarity.
- Returns are measured with signal known after the decision-date close, entry at the next open, and exit at the close of the fifth session.
- Frequency-matched controls are selected deterministically by `(ticker, split, year, event_type)` and seeded with `20260803`.
- Evidence gates include sample size, concentration, mean net return, bootstrap CIs, lift over controls, and split-holdout consistency.

## Locked parameters

- Universe: exact ordered `MINING_UNIVERSE`
- Provider: `schwab`
- Study range: `2018-01-02` to `2026-07-31`
- Splits: development `2018-01-02–2021-12-31`, validation `2022-01-03–2023-12-29`, holdout `2024-01-02–2026-07-31`
- Profile: `standard`
- Lookback: `10` days
- Move / holding horizon: `5` sessions
- Threshold: `75`
- `SERIES_WEIGHTS`: unchanged (`price_pct=0.35`, `volume_ratio=0.30`, `rsi=0.15`, `macd_diff=0.10`, `bb_width=0.10`)
- Run-up / decline thresholds: `15%` / `-12%`
- Cost scenarios: `0 / 5 / 10` bps per side
- Decision slippage: `10` bps
- Commission: `0` bps
- Bootstrap: ticker-cluster, `5000` resamples, seed `20260803`, 2.5/97.5 percentiles
- `production_promotion_eligible`: always `false`

## Safe-handoff bundle

When contributing a real Schwab run to this PR, share **only** the following artifacts. Raw OHLCV, `.env`, OAuth tokens, credentials, HTTP headers, and provider responses must never be committed or posted.

Allowed bundle contents:

1. `manifest.lock.json` — with file hashes and provenance metadata only (no bar data).
2. `study_spec.lock.json` — the exact locked spec.
3. `development_fingerprints.json` — aggregated fingerprint statistics.
4. `promotion_decision.json` — the final classification and gate results.
5. `period_summary.csv`, `ticker_summary.csv`, `baseline_comparison.csv`, `data_quality.csv` — aggregate result tables.
6. `report.md` — the generated human-readable report.
7. `artifact_manifest.json` — deterministic artifact checksum list.
8. A short `README.txt` noting the workflow run/job, merge ref, and that raw data is excluded.

Never include:

- `*.csv` files containing per-ticker OHLCV rows
- `observations.csv`, `qualifying_signals.csv`, `frequency_matched_controls.csv`, `event_study.csv`, `executable_trades.csv`
- `.env`, `.env.example`, or any file containing credentials
- OAuth token files or token paths
- Schwab account, position, order, or transaction data
- HTTP request/response logs or headers

## Windows PowerShell workflow

```powershell
# Verify the token exists (do not print token contents).
Test-Path "$env:USERPROFILE\.tradex_schwab_token.json"
Get-Item "$env:USERPROFILE\.tradex_schwab_token.json" | Select-Object FullName, Length, LastWriteTime

# Optional read-only Schwab smoke test.
uv --system-certs run python scripts/schwab_smoke_test.py

# Build the locked offline snapshot.
$SnapshotDir = "$env:USERPROFILE\.tradex\research\pattern-validation\snapshot"
uv --system-certs run python -m tradex.research.pattern_validation snapshot `
  --universe current-mining-universe `
  --start 2018-01-02 `
  --end 2026-07-31 `
  --provider schwab `
  --output $SnapshotDir

# Evaluate offline (no network, no credentials, no ~/.tradex/fingerprints.db)
$ResultsDir = "$env:USERPROFILE\.tradex\research\pattern-validation\results"
uv --system-certs run python -m tradex.research.pattern_validation evaluate `
  --manifest "$SnapshotDir\manifest.lock.json" `
  --output $ResultsDir
```

## Adjustment policy

For Schwab, the study uses the provider-returned daily candles as-is. The `adjustment_policy` field is set to `provider_default`; the study does not apply additional split or dividend adjustment, and the exact corporate-action methodology is not independently verified beyond the provider contract.

## Real Schwab study results

The locked local Schwab study was completed on the `MINING_UNIVERSE` using exact head `6035a7d7e4c7b4c31eb2c5bad34d809a0ce559e0`. The sanitized aggregate safe-handoff bundle is preserved at `docs/research/artifacts/PATTERN-001/2026-08-03-9ea40e85/`.

### Verified identifiers

| Identifier | Value |
|---|---|
| ZIP SHA-256 | `b0171d7e221c4e21e808eca0ffa27dba30d7ef7a835598133c3ef63cd1e5e424` |
| Study-spec SHA-256 | `68a3d59cf4b06f21889207dde67e217d2a61916ec7c331adb9fe629c521bf8c7` |
| Manifest SHA-256 | `9ea40e85d3c2388ec33f582988a79e66b8f0e5d18a04800c714db358db3080ef` |
| Universe SHA-256 | `554c6933750be1f10716ce45912e70ff6c963cc190157f730ef1d7ddbd850404` |
| Provider | `schwab` |
| Date range | `2018-01-02` to `2026-07-31` |
| Requested / successful / failed tickers | `44 / 44 / 0` |
| Validated daily bars | `90,825` |
| Invalid OHLC rows removed | `13` across `12` tickers |

### Development fingerprints

| Event type | Events | Tickers | Fingerprint SHA-256 |
|---|---|---|---|
| Run-up | `274` | `41` | `dfda89180393330da667f005db90cb1d0b49e80b37ea6a4982b13ab9030661e9` |
| Decline | `322` | `42` | `35c632dcb4b5f245851c111dfb05c3a8d1cf6633c07741f89a54e273ed3e3ba1` |

### Locked-study results at 10 bps per side

**Run-up**

- Validation: `170` signals / `42` tickers; mean net return `-0.071576%`; lift `+7.072294 bps`; lift CI `[-95.613019, 123.821956]`
- Holdout: `234` signals / `44` tickers; mean net return `+0.258650%`; lift `+10.238333 bps`; lift CI `[-103.220270, 124.515187]`
- Classification: `rejected`

**Decline**

- Validation: `1,816` signals / `43` tickers; mean signed net return `-1.343259%`; lift `-98.634383 bps`; lift CI `[-151.294198, -45.900568]`
- Holdout: `2,341` signals / `44` tickers; mean signed net return `-0.979449%`; lift `-21.393567 bps`; lift CI `[-54.078555, 12.556656]`
- Classification: `rejected`

### Overall decision

- **Overall classification:** `rejected`
- **Run-up classification:** `rejected`
- **Decline classification:** `rejected`
- **`production_promotion_eligible`:** `false`
- **`research_test_mode`:** `false`

### Product decisions

- Keep automatic pattern-match alerts disabled.
- Keep the dashboard Pattern Similarity tab and matcher output explicitly experimental/non-predictive.
- Do not add pattern similarity to production scoring, ranking, eligibility, or confluence.
- Do not tune matcher weights, thresholds, profiles, event definitions, lookbacks, holding periods, or universe from these results.
- Do not introduce an automatic inversion or alternative strategy without a separate approved study.

## Interpretation of results

A result of `supported`, `rejected`, or `inconclusive` is research-only. Because the universe is a fixed convenience cohort rather than a point-in-time index, the result cannot be promoted to production pattern-match alerts, scoring, ranking, or eligibility.
