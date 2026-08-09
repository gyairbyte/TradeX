# INTRA-001D — Locked Real-Data Intraday Study

This document records the `INTRA-001D` phase: a narrowly scoped adapter and orchestrator that connects the accepted `INTRA-001C` synthetic intraday engine to the locked private `INTRA-001B-DATASET-V1` 2025 snapshot and executes the pre-registered development, validation, and conditional-holdout study.

## Scope

- Run the locked `INTRA-001C` engine on the existing `INTRA-001B-DATASET-V1` snapshot only.
- Verify manifests, locked hashes, and per-split symbol-month integrity before loading OHLCV.
- Load only the requested split's symbol-month files.
- Respect monthly point-in-time universes, warmup history, and split boundaries.
- Carry the locked `pre_normalization_metrics_available = False` (unverified) condition into split-level data-sufficiency evaluation.
- Freeze evaluation code before validation and use the same frozen commit for the one-time holdout run.
- Refuse to parse holdout OHLCV unless validation disposition is exactly `supported`.
- Write safe, reproducible artifact bundles per split with the locked file list.
- Do **not** make provider calls, re-download data, tune parameters, modify locked strategy files, or start production promotion.

## Package layout

```
tradex/research/intraday_study/
  __init__.py     public exports
  __main__.py     `python -m tradex.research.intraday_study` entry point
  cli.py          `run` (dev/val/holdout pipeline) and `freeze` subcommands
  manifest.py     manifest.lock.json / ohlcv_manifest.csv / data_quality.csv / universe_manifest.csv loading and integrity checks
  loader.py       Parquet → TickerInput with PIT warmup/evaluation semantics
  split.py        locked dev/val/holdout date ranges and month map
  study.py        `run_split` orchestration using `run_study`
  freeze.py       evaluation-code freeze (git HEAD, cleanliness, locked hashes)
  artifacts.py    CSV/JSON report bundle writer and checksums
```

## CLI

```bash
uv run python -m tradex.research.intraday_study run \
  --dataset-root <private-INTRA-001B-root> \
  --output <explicit-safe-output-directory> \
  --generated-at <fixed-UTC-timestamp>
```

The CLI also accepts `--manifest-lock` and `--spec` with sensible locked defaults.

## Locked semantics enforced

- All symbol-month Parquet files are SHA-256 verified against `manifest.lock.json` before parsing.
- Each symbol-month's `evaluation_session_dates` are restricted to the effective month inside the requested split; earlier sessions are retained as warmup but never generate signals.
- `pre_normalization_metrics_available` is read from `data_quality.csv` and passed through `DataQualitySummary` to `evaluate_data_sufficiency`.
- Validation is the only gating split; development is diagnostic and non-gating.
- Holdout is parsed at most once and only when validation returns `supported`.
- The frozen `evaluation_code_sha` is recorded in every evidence-eligible artifact bundle.

## Verification

- `uv run pytest tests/research/intraday_study -q`
- `uv run pytest tests/research/intraday_engine -q`
- `uv run pytest tests -q`
- `uv run ruff check tradex/research/intraday_study tradex/research/intraday_engine tests/research/intraday_study tests/research/intraday_engine`
- `git diff --check`
- All locked hashes verified (`INTRA-001-v1.json`, `INTRA-001-data-sufficiency-amendment-v3.json`, `INTRA-001B-dataset-v1.json`).
- Artifact checksums verified against `checksums.sha256`.

## Limitations

- The `INTRA-001B-DATASET-V1` snapshot is marked `pre_normalization_metrics_available = False`; therefore split-level data sufficiency cannot be verified and the canonical disposition is at best `inconclusive` unless additional evidence is accepted by explicit amendment.
- No new live provider calls are made; no OHLCV is re-downloaded, repaired, or interpolated.
- Production promotion is out of scope and requires a separate Gary-approved PR.
