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

## Dashboard

For explicitly requested manual UI testing:

```bash
uv run streamlit run tradex/ui/dashboard.py
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
