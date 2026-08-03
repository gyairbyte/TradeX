---
name: TradeX Local Testing
description: How to install dependencies, run deterministic tests, lint the supported paths, and inspect the TradeX watcher CLI.
---

## Purpose

Use this skill when validating changes to the TradeX repository.

All automated tests must remain:

- Credential-free
- Network-free
- Deterministic
- Safe for CI

Do not use real provider credentials or call live market-data APIs unless the user explicitly requests a separate local smoke test.

## Environment

TradeX is a Python project managed with `uv`.

The complete test suite imports optional provider packages, including:

- `schwab-py`
- `alpaca-py`
- `ib_insync`

Install both development and all optional dependencies before running the full suite:

```bash
uv sync --extra dev --extra all
```

Running only `uv sync --extra dev` is not sufficient for the complete test suite.

Run all commands from the repository root.

## Standard verification

### Lint

Use the repository's current supported lint command:

```bash
uv run ruff check tests scripts
```

Do not substitute `ruff check .` as the required validation command unless the task explicitly includes resolving repository-wide lint debt.

### Tests

Run:

```bash
uv run pytest tests -q
```

Tests must not contact:

- Yahoo
- Schwab
- Alpaca
- IBKR
- Tradier
- Unusual Whales
- Wikipedia
- Exchange calendar web services
- Any other external service

Mock all provider and network boundaries.

### Combined verification

```bash
uv sync --extra dev --extra all
uv run ruff check tests scripts
uv run pytest tests -q
```

## Watcher CLI

Inspect available watcher options with:

```bash
uv run python -m tradex.tracker.watcher --help
```

Example scheduled watcher command:

```bash
uv run python -m tradex.tracker.watcher \
  --timeframe intraday \
  --interval 5 \
  --market-hours-only
```

Do not start a blocking watcher loop during automated testing.
Patch the scheduler or inject deterministic time values instead.

## Backtest CLI

Inspect available backtest options with:

```bash
uv run python -m tradex.backtest --help
```

Example offline CSV backtest command (no credentials or live APIs). The `--ticker` flag identifies the security; `--csv` only supplies the price history:

```bash
uv run python -m tradex.backtest \
  --csv data/spy_daily.csv \
  --ticker SPY \
  --min-score 40 \
  --warmup-bars 60 \
  --holding-bars 3 \
  --stop-loss-pct 5 \
  --take-profit-pct 10 \
  --json-output result.json \
  --trades-output trades.csv \
  --equity-output equity.csv
```

Provider-backed daily history (Yahoo requires no credentials; Schwab requires OAuth):

```bash
uv run python -m tradex.backtest \
  --ticker SPY \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --provider yahoo
```

Run the focused backtest suite with:

```bash
uv run pytest tests/backtest -q
```

The CSV must contain `datetime` (or `date`), `open`, `high`, `low`, `close`, `volume`.
Use `--timezone` for naive datetimes. The JSON output must contain no `NaN` or `Infinity` values.

Key execution assumptions for credential-free tests:

- Long-only, one position at a time, 100% capital per trade, fractional shares.
- Signals are point-in-time: the scorer sees only bars up to and including the current close.
- Entry is at the next bar's open.
- Stop and target are anchored to the entry fill, not the signal bar close.
- Exit priority: opening gap through stop/target, then intraday stop/target (with `intrabar_policy` tie-break), then `time_exit` at `max_holding_bars`.
- The equity curve marks a bar as exposed if a position is held at any point during that bar; the `position_ticker` column records the active ticker.

## Score-validation CLI

Inspect score-validation commands with:

```bash
uv run python -m tradex.research.score_validation --help
uv run python -m tradex.research.score_validation snapshot --help
uv run python -m tradex.research.score_validation evaluate --help
```

Run the focused suite:

```bash
uv run pytest tests/research/score_validation -q
```

The `evaluate` command is fully offline and credential-free. It always uses a fresh `ShortWeights()` instance and never reads `~/.tradex/weights.json`. The `snapshot` command is the only mode that may contact a market-data provider.

Example offline workflow with a synthetic manifest:

```bash
# 1. Build a versioned offline snapshot (network allowed; credentials optional)
uv run python -m tradex.research.score_validation snapshot \
  --tickers AAPL,MSFT,SPY \
  --start 2020-01-01 \
  --end 2023-12-31 \
  --provider yahoo \
  --output-dir data/score_validation_snapshot \
  --development-split 2018-01-01,2022-12-31 \
  --validation-split 2023-01-01,2024-12-31 \
  --holdout-split 2025-01-01,2025-12-31

# 2. Evaluate offline (no network, no credentials, no saved weights)
uv run python -m tradex.research.score_validation evaluate \
  --manifest data/score_validation_snapshot/manifest.json \
  --output-dir tmp/score_validation \
  --warmup-bars 60 \
  --horizons 1,3,5 \
  --slippage-bps 0.0,5.0,10.0
```

Do not present event-study returns as portfolio equity, account returns, or proof of a tradable strategy. The executable backtest lives in `tradex/backtest`.

## Pre-market gap scanner CLI

Inspect pre-market scanner options with:

```bash
uv run python -m tradex.premarket --help
uv run python -m tradex.premarket scan --help
```

Run the focused pre-market suite:

```bash
uv run pytest tests/premarket -q
```

Example credential-free scan (it returns `Outside window` on weekends and holidays because no market session is active):

```bash
uv run python -m tradex.premarket scan \
  --tickers AAPL,TSLA,NVDA \
  --min-gap 4.0 \
  --min-premarket-volume 5000
```

All new filters are opt-in; the default behavior is a 2% minimum absolute gap. Spread filtering only uses real bid/ask quotes and is never inferred from the candle range. Catalyst context is explicitly sourced and does not claim a headline/earnings caused the gap.

## Short-term market context research CLI

Inspect context-study commands with:

```bash
uv run python -m tradex.research.short_context --help
uv run python -m tradex.research.short_context snapshot --help
uv run python -m tradex.research.short_context evaluate --help
```

Run the focused market-context and scorer suites:

```bash
uv run pytest tests/market tests/research/short_context -q
```

The `snapshot` command is the only mode that may contact a market-data provider. The `evaluate` command is offline and credential-free once a manifest exists. The candidate policies are `off`, `market_rs`, and `market_sector_rs`; a candidate is only promoted when both the event-study and paired-backtest holdout gates pass. A failed or inconclusive study leaves the short-term scorer unchanged.

## Dashboard

For explicitly requested manual UI testing:

```bash
uv run streamlit run tradex/ui/dashboard.py
```

If Streamlit prompts for an email address on first run, stop the server and create `~/.streamlit/config.toml` with telemetry disabled so the dashboard starts non-interactively:

```toml
[server]
headless = true

[browser]
gatherUsageStats = false
```

Do not launch a real Streamlit server during unit tests.

## Deterministic time handling

Watcher functions and market-hours helpers accept injectable aware datetimes for testing.

Use timezone-aware values in:

- UTC
- America/New_York
- Another explicit IANA timezone when testing conversion

The centralized market-hours API rejects naive datetimes.

Do not depend on:

- The host machine timezone
- The real current date or time
- Fixed UTC assumptions for New York market hours
- Real-time sleeps

## Provider credentials

Automated tests require no credentials.

Credentials are relevant only for an explicitly requested, separate live smoke test:

- SCHWAB_APP_KEY
- SCHWAB_APP_SECRET
- SCHWAB_TOKEN_PATH
- ALPACA_API_KEY
- ALPACA_SECRET_KEY

Never:

- Print credentials
- Commit credentials
- Create repository-local OAuth token files
- Add GitHub secrets
- Run Schwab OAuth without explicit user authorization
- Call account, position, transaction, or order endpoints
- Place trades

## Reporting results

Report:

- Exact branch or commit tested
- Ruff result
- Pytest pass/xfail/fail counts
- Whether optional dependencies were installed
- Confirmation that no live APIs or credentials were used
- Any pre-existing failures or lint issues separately from regressions introduced by the current change

## PR requirements

The PR must:

- Contain only the skill file.
- Avoid machine-specific paths such as `/home/ubuntu/repos/TradeX`.
- Avoid references such as "on this box."
- Avoid screenshots and temporary adversarial test files.
- Avoid credentials, tokens, or local secrets.
- Avoid changing application code.
- Avoid changing CI.
- Avoid changing PR #11.
- Explain that the skill prevents future sessions from using an incomplete dependency installation.
- Explain why `uv sync --extra dev --extra all` is required.
- State that `ruff check tests scripts` remains the official scoped lint command until repository-wide lint debt is addressed.

## Verification

Run:

```bash
uv sync --extra dev --extra all
uv run ruff check tests scripts
uv run pytest tests -q
```

Do not prescribe an exact test count because main may change before this PR is opened.
