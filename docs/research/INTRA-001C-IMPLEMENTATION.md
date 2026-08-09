# INTRA-001C — Synthetic Intraday Detector and Execution Engine

This document records the implementation of the `INTRA-001C` phase:
a deterministic, research-only engine that evaluates the locked `INTRA-001`
long open-drive VWAP pullback continuation hypothesis against purely
synthetic 5-minute OHLCV data.

## Scope

- Implement the locked strategy rules verbatim from `docs/research/specs/INTRA-001-v1.json`.
- Use only synthetic ticker names and synthetic sessions.
- Run candidate, Baseline A (production intraday score), and Baseline B
  (simple VWAP reclaim) side-by-side.
- Produce metrics, validation gates, and a `synthetic=true`/`evidence_eligible=false`
  artifact bundle.
- Do **not** run on real symbols, do **not** start `INTRA-001D`.

## Package layout

```
tradex/research/intraday_engine/
  __init__.py        public exports and version
  __main__.py        `python -m tradex.research.intraday_engine` entry point
  cli.py             `synthetic-smoke` command and artifact writer
  spec.py            locked spec loader + SHA-256 verification
  calendar.py        XNYS regular-session 5-minute grid construction
  normalize.py       DataFrame → validated `Session`/`Bar` objects
  vwap.py            Session VWAP (typical price, cumulative PV/V)
  opening_drive.py   Frozen 10:00 AM qualification and volume baseline
  reclaim.py         First VWAP pullback/reclaim detection
  baseline_a.py      Production `tradex.signals.intraday.score` with fresh `IntradayWeights()`
  baseline_b.py      Simple VWAP reclaim without opening-drive filters
  execution.py       Next-bar entry, stop/target, exit priority, time exit
  metrics.py         Per-symbol and pooled expectancy, drawdown, profit factor, concentration
  gates.py           Locked validation gate evaluator and outcome disposition
  synthetic.py       Deterministic synthetic OHLCV fixture generator
  report.py          Markdown/JSON report serialization
  engine.py          `run_study` orchestrator
```

## Key locked semantics implemented

- **Long-only**, `XNYS`, `America/New_York`, regular session 09:30–16:00 ET.
- **No early-close sessions**, no pre/post-market bars.
- Bar timestamps stored as UTC but interpreted in ET; `available_at = bar_start + 5min`.
- VWAP resets every session; no filling/interpolation; no future-bar access.
- At most one trade per ticker-session; no overnight positions.
- Opening drive: six completed bars, return ≥ +0.75%, close > VWAP,
  cumulative volume ≥ 1.5× prior-20-session same-window median.
- Reclaim: 10:00–11:25 bar starts, `low <= VWAP`, `close > VWAP`, `close > open`,
  `close >= 09:30 open`, first only.
- Stops/targets/costs/exit priority match the locked spec exactly.
- Baseline A uses an explicit fresh `IntradayWeights()` instance; no saved weights.
- Validation gates and outcome hierarchy (`supported`/`not_supported`/`inconclusive`/`invalid`)
  follow the locked spec.

## Running the synthetic smoke test

```bash
uv run python -m tradex.research.intraday_engine synthetic-smoke --output /tmp/intra001c-smoke
```

The command writes `result.json`, `report.md`, and `trades_*.csv` to the supplied
directory. All outputs are marked `synthetic=true` and `evidence_eligible=false`.

## Verification

- `uv run pytest tests/research/intraday_engine -q`
- `uv run ruff check tradex/research/intraday_engine tests/research/intraday_engine`
- `git diff --check`
- `sha256sum docs/research/specs/INTRA-001-v1.json` (locked hash)

## Limitations and next steps

- This engine is intentionally research-only; it never touches the locked `INTRA-001B`
  real-data directory or provider APIs.
- Real-data development, validation, and holdout evaluation belong exclusively to
  `INTRA-001D` and require explicit approval before starting.
- The synthetic generator is designed to exercise pass/fail/reject/invalid paths;
  it is not tuned to imply real performance.
