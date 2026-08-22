# TradeX — Setup Guide for AI Agents

> **For the agent reading this:** this file is the canonical end-to-end setup procedure for TradeX. Execute the steps for the user's OS. Detect the OS first. Do not skip the verification steps — they catch the failure modes that have actually happened. When the user says "set up TradeX" or "read SETUP.md and do it," this is your script.

For an architecture overview see [`README.md`](README.md). For desktop-launcher install details see [`launchers/README.md`](launchers/README.md). For project internals and signal logic see [`CLAUDE.md`](CLAUDE.md).

---

## 0. Detect the environment

Before doing anything, confirm:
1. **OS** — macOS or Windows? Use `uname` (Mac/Linux) or `$PSVersionTable` / `ver` (Windows).
2. **Python ≥ 3.11 is on PATH** — `python3 --version` (Mac) or `python --version` (Windows). If not, install it first (`brew install python@3.11` on Mac, [python.org](https://python.org) installer on Windows — make sure "Add to PATH" is checked).
3. **`uv` is installed.** Check with `uv --version`. If missing:
   - macOS: `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
4. **You are in the project root** — the directory containing `pyproject.toml`. If not, `cd` there.

If any of the above fails, stop and report the gap to the user before proceeding.

---

## 1. Create the venv and install dependencies

The project venv must live at `<repo>/.venv` — the desktop launchers hard-code that path.

### macOS / Linux
```bash
uv sync
```

### Windows (PowerShell)
```powershell
uv sync
```

`uv sync` creates `.venv/` and installs everything in `pyproject.toml`. It is idempotent — safe to run again.

**Verify:**
- macOS: `.venv/bin/streamlit --version` should print a version string.
- Windows: `.venv\Scripts\streamlit.exe --version` should print a version string.

If `uv` is unavailable, fallback (slower):
```bash
# macOS
python3.11 -m venv .venv && .venv/bin/pip install -e .

# Windows
python -m venv .venv
.venv\Scripts\pip install -e .
```

### Optional provider extras
The base installation includes `schwab-py>=1.4.0` for Schwab market data. For the full test suite and every provider used in CI, install the `all` extra together with `dev`:
```bash
uv sync --extra dev --extra all
```

To add only specific providers after a base `uv sync`:
```bash
uv pip install -e ".[alpaca]"   # Alpaca real-time (free tier)
uv pip install -e ".[ibkr]"     # Interactive Brokers (requires local TWS/Gateway)
uv pip install -e ".[schwab]"   # Charles Schwab (backward-compatible alias)
uv pip install -e ".[all]"      # Everything
```

---

## 2. Configure environment variables

```bash
cp .env.example .env      # macOS / Linux
copy .env.example .env    # Windows
```

`.env` is gitignored — credentials never leave the machine. Open `.env` and fill in only what the user needs. **Do not invent values.** If the user hasn't said which provider they want, default to `DATA_PROVIDER=schwab` (or `DATA_PROVIDER=yahoo` if they prefer a zero-setup fallback).

`DATA_PROVIDER` controls **OHLCV data** only. Options activity, earnings, and market-cap ranking have their own source overrides (see `.env.example`).

For options, the source also determines the *kind* of data available:
- `unusual_whales` (or `auto` when `UNUSUAL_WHALES_API_KEY` is set) provides **true options-flow** events (sweeps, premium, side). Events without a valid `open_interest` value receive `vol_oi_ratio=None` and are excluded from `min_vol_oi` filtering.
- `tradier` (or `auto` when `TRADIER_API_KEY` is set) and `yahoo` provide **options-chain snapshots** (volume, open interest, bid/ask/last) only. They cannot supply transaction-level flow.

Signal history records the OHLCV provider that produced each signal (`signal_history.provider`), and resolved outcomes record `outcome_provider`. Every scan now writes a `scan_sessions` row and one `scan_observations` row per ticker requested, including tickers that scored below threshold or failed to fetch. A linked `scan_runs` audit row records `tickers_n` (requested), `hits_n` (qualifying signals), `status` (completed / partial / failed / unknown), `requested_provider` / `actual_provider`, and `source` (native / compatibility / legacy). Pre-existing databases are migrated safely; rows created before this feature are labeled `unknown` and assigned to synthetic legacy sessions, while old `scan_runs` rows are preserved with `source='legacy'` and `counts_complete=0`.

Key variables:
| Variable | Required? | Notes |
|---|---|---|
| `DATA_PROVIDER` | Yes | OHLCV provider: `schwab` (primary/default), `alpaca` (degraded intraday), `yahoo` (research/fallback/premarket), `ibkr` (archived/manual). Default `schwab`. |
| `OHLCV_MAX_RETRIES` | No | Extra retry attempts per ticker for transient failures only. Default `0`, max `3`. |
| `OHLCV_FALLBACK_ORDER` | No | Comma-separated whole-scan fallback provider chain (e.g. `schwab,yahoo`). Empty/missing = disabled. |
| `OPTIONS_DATA_SOURCE` | No | `auto` (default), `unusual_whales`, `tradier`, `yahoo`. `unusual_whales` gives true flow; `tradier`/`yahoo` give chain snapshots. |
| `EARNINGS_DATA_SOURCE` | No | `yahoo` (default) |
| `MARKET_CAP_DATA_SOURCE` | No | `yahoo` (default), `schwab` |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Only for Alpaca | From alpaca.markets dashboard |
| `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` | Only for Schwab | From developer.schwab.com — also requires OAuth bootstrap (see §3a) |
| `IBKR_HOST` / `IBKR_PORT` | Only for IBKR | TWS or Gateway must be running locally |
| `ALERT_DISCORD_TOKEN` / `ALERT_DISCORD_CHANNEL_ID` | Only for Discord alerts | Optional |
| `ALERT_EMAIL_TO` / `ALERT_EMAIL_FROM` / `ALERT_EMAIL_HOST` / `ALERT_EMAIL_USER` / `ALERT_EMAIL_PASS` | Only for email alerts | Optional |
| `ALERT_COOLDOWN_ENABLED` | No | `true` (default) / `false` to disable all automatic alert cooldowns |
| `ALERT_COOLDOWN_MINUTES` | No | Default cooldown in minutes, `1` to `10080`. Default `60`. |
| `ALERT_COIL_COOLDOWN_MINUTES` | No | Optional per-type override. Default `ALERT_COOLDOWN_MINUTES`. |
| `ALERT_CONFLUENCE_COOLDOWN_MINUTES` | No | Optional per-type override. Default `ALERT_COOLDOWN_MINUTES`. |
| `ALERT_PATTERN_COOLDOWN_MINUTES` | No | Optional per-type override. Default `ALERT_COOLDOWN_MINUTES`. Parsed for backward compatibility; pattern matching is research-only and is not dispatched by automatic watcher alerts. |
| `ALERT_GAP_COOLDOWN_MINUTES` | No | Optional per-type override. Default `ALERT_COOLDOWN_MINUTES`. |
| `ALERT_STATE_PATH` | No | Isolated SQLite alert state database. Default `~/.tradex/alerts.db`. |
| `TRADEX_DB_PATH` | No | Signal history / scan session SQLite DB. Default `~/.tradex/signals.db`. |
| `TRADEX_FP_DB` | No | Pattern fingerprint SQLite DB. Default `~/.tradex/fingerprints.db`. |
| `TRADEX_WATCHLISTS_DB_PATH` | No | Watchlists SQLite DB. Default `~/.tradex/watchlists.db`. |
| `TRADEX_EARNINGS_CACHE_PATH` | No | Earnings calendar cache SQLite DB. Default `~/.tradex/earnings_cache.db`. |
| `TRADEX_WEIGHTS_PATH` | No | Custom scoring weights JSON. Default `~/.tradex/weights.json`. |

`tradex/config.py` is the single configuration boundary. `load_runtime_settings()` reads `.env` once, applies `os.environ` overrides, and returns an immutable `TradeXSettings`. Every public entry point accepts an optional `settings` keyword for explicit injection; when omitted it calls `load_runtime_settings()` at call time, so modules can be imported without a `.env` or credentials.

### 2a. Schwab OAuth bootstrap (only if `DATA_PROVIDER=schwab`)

Schwab requires a one-time browser OAuth flow to mint a token. Run from an interactive terminal (not a subprocess):

```bash
.venv/bin/python scripts/schwab_oauth.py
```

The script prints an authorization URL. Open it in any browser, log in with your **Schwab brokerage** credentials (not developer.schwab.com), complete 2FA, click **Allow**. The browser redirects to `https://127.0.0.1/?code=...` and shows a "can't connect" page — **that's expected**. Copy the entire URL from the address bar and paste it at the `Redirect URL>` prompt. Token is written to `~/.tradex_schwab_token.json`.

The refresh token is currently short-lived — Schwab's published guidance treats refresh credentials as roughly a 7-day window, with automatic access-token refresh inside that window. Once the refresh window expires, re-run `scripts/schwab_oauth.py` to authorize again.

App registration in the Schwab Developer Portal must use:
- **Callback URL:** `https://127.0.0.1` (exact match, no trailing slash, must be https)
- **API Products:** "Accounts and Trading Production" + "Market Data Production"
- **Order Limit:** `0` is fine for TradeX — this project only reads market data and never places orders

**Token-file safety:** keep `SCHWAB_TOKEN_PATH` outside the repo directory (the default `~/.tradex_schwab_token.json` is fine). The OAuth script refuses to write a token inside the project, and `.gitignore` ignores common token filenames.

### 2b. Validate the Schwab provider (optional, local only)

After generating the token, run the read-only smoke test to confirm Schwab market data works. On Windows, use PowerShell from the repo root:

```powershell
uv --system-certs sync --extra dev --extra all
$token = "$env:USERPROFILE\.tradex_schwab_token.json"
Test-Path $token
Get-Item $token | Select-Object FullName, Length, LastWriteTime
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.tradex\research\pattern-validation\snapshot" | Out-Null
uv --system-certs run python scripts/schwab_smoke_test.py
```

On macOS / Linux:

```bash
uv sync --extra dev --extra all
test -f ~/.tradex_schwab_token.json && ls -l ~/.tradex_schwab_token.json
mkdir -p ~/.tradex/research/pattern-validation/snapshot
uv run python scripts/schwab_smoke_test.py
```

It fetches `SPY` (or `SCHWAB_SMOKE_SYMBOL` from `.env`) for the intraday, short, and long timeframes and verifies the canonical OHLCV contract. It never accesses account, position, balance, or order endpoints.

---

## 3. Point the launcher at this machine's repo (one-time)

The desktop launchers need to know where the repo lives. Without this, they only work when launched from inside the repo — copying `TradeX.app` to `/Applications` or making a Windows Desktop shortcut would fail.

Create `~/.tradex/config` (macOS/Linux) or `%USERPROFILE%\.tradex\config` (Windows) containing a single line:

```
TRADEX_HOME=<absolute path to this repo>
```

### macOS / Linux
```bash
mkdir -p ~/.tradex
echo "TRADEX_HOME=$(pwd)" > ~/.tradex/config
cat ~/.tradex/config   # verify
```

### Windows (PowerShell, run from the repo root)
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.tradex" | Out-Null
"TRADEX_HOME=$(Get-Location)" | Out-File -Encoding ascii "$env:USERPROFILE\.tradex\config"
Get-Content "$env:USERPROFILE\.tradex\config"   # verify
```

Alternative: set the `TRADEX_HOME` environment variable instead of writing the config file. Either works.

---

## 4. First launch

### Option A — desktop launcher (one-click going forward)

**macOS:**
1. Drag `launchers/macos/TradeX.app` to `/Applications` (or Desktop).
2. First time only: right-click the app → **Open** (it's unsigned, so Gatekeeper blocks the normal double-click).
3. The browser should open to `http://localhost:8501` within ~5 seconds.

**Windows:**
1. Right-click `launchers\windows\TradeX.bat` → **Create shortcut**.
2. Move the shortcut to Desktop (or pin to Taskbar).
3. Optional: right-click shortcut → **Properties** → **Change Icon...** → point at `launchers\windows\TradeX.ico`.
4. Double-click the shortcut. Browser opens to `http://localhost:8501`.

### Option B — command line
```bash
# macOS / Linux
.venv/bin/streamlit run tradex/ui/dashboard.py

# Windows
.venv\Scripts\streamlit run tradex\ui\dashboard.py
```

---

## 5. Verify the install actually worked

Don't trust "it didn't error" — open the dashboard and check:
1. The **Scanner** tab loads with the Default watchlist (20 tickers).
2. Clicking "Scan" returns rows (may be empty if scores are below the `min_score` threshold — try lowering it).
3. The **Help** tab loads.

If the dashboard fails to start, check the log at `~/.tradex/dashboard.log` (Mac/Linux) or `%USERPROFILE%\.tradex\dashboard.log` (Windows).

---

## 6. Optional: scheduled background scanner

The watcher runs the screener on an interval and writes results to `~/.tradex/signals.db`. This is what powers the **Coil Detector** and **Signal Journal** tabs over time. It evaluates automatic alerts for coil, confluence, and pre-market gap setups, using a separate `~/.tradex/alerts.db` state database for cooldown and deduplication. Pattern matching is research-only and is quarantined from automatic watcher alerts.

```bash
# macOS / Linux
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only

# Windows
.venv\Scripts\python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only
```

Run during market hours. With `--market-hours-only`, scans are skipped outside the NYSE regular session (weekends, NYSE holidays including Good Friday, and early-close days are handled automatically via the `exchange-calendars` XNYS calendar). Manual one-off scans omit the flag. The daily pre-market gap scan fires at `08:00 America/New_York` and the outcome pass at `16:30 America/New_York`; both stay at the same New York wall-clock time across DST changes and skip non-trading days. The watcher persists the effective `provider` with each scan run and outcome pass.

Alert cooldown is enabled by default. Override it at runtime:

```bash
# 120-minute default cooldown
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-cooldown-minutes 120

# Disable cooldown entirely (send every eligible alert)
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --disable-alert-cooldown

# Use a custom alert state database
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --alert-state-path /path/to/alerts.db
```

Each automatic alert is keyed by `(ticker, alert_type, timeframe)`. The first eligible alert is sent and starts a cooldown; repeats during that window are suppressed and recorded in the state database. Cooldown only starts when at least one configured channel successfully receives the alert. Manual test alerts from the dashboard bypass cooldown.

---

## 7. Pre-Market Gap Scanner

The `tradex/premarket` scanner finds pre-market gaps and produces a structured `GapScanReport` with counts, per-ticker observations, and optional quality filters.

```bash
# Basic scan (Yahoo, default 2% minimum absolute gap)
uv run python -m tradex.premarket scan --tickers AAPL,TSLA,NVDA --min-gap 2.0

# With quality filters (all opt-in)
uv run python -m tradex.premarket scan \
  --tickers AAPL,TSLA,NVDA \
  --min-gap 4.0 \
  --min-premarket-volume 5000 \
  --min-premarket-volume-ratio 0.2 \
  --max-data-age-minutes 15 \
  --include-catalysts

# Write results to JSON/CSV for downstream use
uv run python -m tradex.premarket scan \
  --tickers AAPL,TSLA,NVDA \
  --json-output gap_report.json \
  --csv-output gap_results.csv
```

All filters are off by default except `min-gap`. Spread filtering only uses real bid/ask quotes and is never inferred from the candle range. The scheduled watcher calls the same `scan_gaps_with_report` API and logs requested, qualified, filtered, failed, and outside-window counts.

---

## 8. Backtesting (optional)

TradeX includes a deterministic, point-in-time backtest engine in `tradex/backtest`. It is a research tool, not a live-trading system.

```bash
# From an offline CSV (the --ticker flag identifies the security)
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

# Provider-backed daily history (Yahoo requires no credentials; Schwab requires OAuth)
uv run python -m tradex.backtest \
  --ticker SPY \
  --start 2023-01-01 \
  --end 2023-12-31 \
  --provider yahoo
```

The CSV must contain `datetime` (or `date`), `open`, `high`, `low`, `close`, and `volume`. Naive datetimes can be localized with `--timezone` (e.g. `--timezone America/New_York`). The engine reuses the production `tradex.signals.short_term.score` scorer unchanged and defaults to a fresh `ShortWeights()` snapshot so results are independent of `~/.tradex/weights.json`.

### Execution model

- Long-only, one position at a time, 100% capital per trade, fractional shares.
- The scorer sees only bars up to and including the current close (`bars.iloc[:i+1]`) at every historical bar.
- Entry is at the next bar's open.
- Stop and target are anchored to the **entry fill** (`open * (1 + slippage_bps / 10_000)`), not the signal bar close.
- Cost model:
  - `entry_fill = open * (1 + slippage_bps / 10_000)`
  - `cash_per_share = entry_fill * (1 + commission_bps / 10_000)`
  - `quantity = capital / cash_per_share`
  - `exit_fill = raw_exit * (1 - slippage_bps / 10_000)`
  - `ending_cash = quantity * exit_fill * (1 - commission_bps / 10_000)`
- Exit priority per holding bar:
  1. Opening gap through stop/target (`gap_stop` / `gap_target`) — exit at the open.
  2. Intrabar stop or target touch. If both are touched in the same bar, the conservative default `intrabar_policy=stop_first` elects the stop; use `target_first` to elect the target instead.
  3. `time_exit` at the close of the last allowed bar (`max_holding_bars`).
- The equity curve marks a bar as exposed (`position_open=True`) if a position is held at any point during that bar, including the entry and exit bars. The `position_ticker` column records the active ticker.
- Max drawdown is the largest peak-to-trough decline of the equity curve, expressed as a negative percentage. The buy-and-hold benchmark applies the same cost model once over the evaluation window.

### Backtest verification

After install, run the built-in tests and a credential-free offline example:

```bash
uv run pytest tests/backtest -q
uv run python -m tradex.backtest --help
```

---

## 9. Score-validation study (optional)

TradeX includes a reproducible event-study package in `tradex/research/score_validation` for evaluating whether the short-term scorer is calibrated to forward returns. It is research-only and does not alter the production score.

```bash
# Build an offline snapshot (network allowed; credentials optional)
uv run python -m tradex.research.score_validation snapshot \
  --tickers AAPL,MSFT,SPY \
  --start 2020-01-01 \
  --end 2023-12-31 \
  --provider yahoo \
  --output-dir data/score_validation_snapshot \
  --development-split 2018-01-01,2022-12-31 \
  --validation-split 2023-01-01,2024-12-31 \
  --holdout-split 2025-01-01,2025-12-31

# Evaluate offline (no network, no credentials, no saved weights)
uv run python -m tradex.research.score_validation evaluate \
  --manifest data/score_validation_snapshot/manifest.json \
  --output-dir results/score_validation \
  --warmup-bars 60 \
  --horizons 1,3,5 \
  --slippage-bps 0.0,5.0,10.0
```

The `evaluate` command produces deterministic CSV, JSON, and Markdown outputs. It always uses a fresh `ShortWeights()` instance and separates the event study from the executable backtest engine in `tradex/backtest`.

Verify the package:

```bash
uv run pytest tests/research/score_validation -q
uv run python -m tradex.research.score_validation --help
uv run python -m tradex.research.score_validation snapshot --help
uv run python -m tradex.research.score_validation evaluate --help
```

---

## 10. Pattern similarity validation (optional)

`tradex/research/pattern_validation` runs a locked, point-in-time study of the existing pattern matcher. It is research-only and does not alter production scoring, ranking, eligibility, or automatic alerts.

Windows PowerShell:

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

The locked study uses the exact ordered `MINING_UNIVERSE` from `tradex/patterns/miner.py`. Keep raw OHLCV, `.env`, OAuth tokens, credentials, and provider responses outside the repository. The handoff bundle is described in `docs/research/PATTERN-001.md`.

Verify the package:

```bash
uv run pytest tests/research/pattern_validation -q
uv run python -m tradex.research.pattern_validation --help
uv run python -m tradex.research.pattern_validation snapshot --help
uv run python -m tradex.research.pattern_validation evaluate --help
```

The package builds one fingerprint per event type from the development split only, evaluates validation/holdout against that immutable fingerprint, and enforces the locked splits, weights, thresholds, and `MINING_UNIVERSE`. `production_promotion_eligible` is always `false` because the universe is not point-in-time.

For Schwab, the adjustment policy is `provider_default`: the provider-returned daily candles are used as-is, the study does not apply additional split or dividend adjustment, and the exact corporate-action methodology is not independently verified beyond the provider contract.

---

## 11. Short-term market context research (optional)

`tradex/research/short_context` evaluates whether adding market-regime and relative-strength filters improves the short-term scorer. It reuses the VAL-002 snapshot/evaluation design and adds point-in-time context computation in `tradex/market/context.py`.

```bash
# Inspect commands
uv run python -m tradex.research.short_context --help
uv run python -m tradex.research.short_context snapshot --help
uv run python -m tradex.research.short_context evaluate --help

# Verify the package
uv run pytest tests/market tests/research/short_context -q
```

The candidate policies are `off` (baseline), `market_rs`, and `market_sector_rs`. A candidate becomes eligible for a future production-integration PR if both the event-study and paired-backtest holdout gates pass; until then, the production screener does not expose context filtering and the existing short-term score, weights, and thresholds remain unchanged.

**Current status:** The synthetic verification run confirmed the pipeline is deterministic and the gates are enforced, but the selected `market_sector_rs` candidate failed both holdout gates on synthetic data. The pre-registered real-data v1 study was attempted on Schwab daily OHLCV, but `23` malformed candles across `19` of 45 locked symbols violated hard OHLC invariants (e.g., `low > open` or `high < open`) out of approximately `82,035` fetched rows (`0.028%`), so the snapshot failed before a manifest could be generated. The v2 rerun applied the locked `short-001-hard-invalid-row-exclusion-v2` ingestion policy, dropped the `23` malformed rows while preserving the complete 45-symbol panel, and re-ran the unchanged evaluation. No candidate policy passed the predefined development/validation criteria (`selected_policy: null`; `selection_reason: "no policy passed development and validation criteria"`), so SHORT-001 is **Completed — Not supported** (`production_promotion_eligible=false`). The production short-term score, weights, thresholds, and behavior remain unchanged. See `docs/research/SHORT-001.md` for the disposition, `docs/research/SHORT-001-SCHWAB-STUDY.md` for the v1 audit, and `docs/research/SHORT-001-SCHWAB-STUDY-V2.md` for the v2 report.

---

## 12. Intraday open-drive VWAP pullback specification (optional)

`docs/research/INTRA-001-SPEC.md` pre-registers a concrete, research-only intraday setup. It defines the candidate long open-drive VWAP pullback continuation strategy, two baselines (current production `intraday.score` and a simple VWAP reclaim), locked 2022–2025 splits, sample minimums, validation/holdout gates, and a provider-feasibility review.

`INTRA-001` is now complete and inconclusive. The locked real-data study at `docs/research/artifacts/INTRA-001D/2026-08-10-151816/` returned `inconclusive` with `production_promotion_eligible=false`; the holdout was not parsed. No further work on this hypothesis is authorized without a new Gary-approved plan. The current research program is `LONG-002` (see `docs/research/LONG-002.md`).

---

## 13. Known caveats and gotchas

1. **macOS Gatekeeper blocks the first launch** of `TradeX.app`. Right-click → Open the first time. Subsequent double-clicks work normally.
2. **The launcher needs `~/.tradex/config`** (or `$TRADEX_HOME`) when run from outside the repo (e.g. from `/Applications`). If you see "Could not locate the TradeX project directory," go back to step 3.
3. **The `.venv` must live at `<repo>/.venv`** — the launchers won't find it anywhere else. If you already have a venv at a different path, recreate it at `.venv`.
4. **Port 8501 must be free** for the dashboard. The launchers reuse an existing server if 8501 is already listening, so double-clicking twice is safe — but if a *different* process holds 8501, change Streamlit's port: `streamlit run ... --server.port=8502`.
5. **yfinance rate-limits** — large watchlists (100+ tickers) on the Yahoo fallback provider may hit transient failures. The screener logs the failure category and continues. You can set `OHLCV_MAX_RETRIES` (max 3) for automatic retry of transient network errors, and `OHLCV_FALLBACK_ORDER` to enable a whole-scan fallback chain.
6. **TD Ameritrade is dead** — its API shut down September 2024. Use `DATA_PROVIDER=schwab` (their replacement) instead. Do not reference the old `tda-api` library.
7. **Schwab token path** — keep `SCHWAB_TOKEN_PATH` outside the repo; `scripts/schwab_oauth.py` enforces this and sets restrictive file permissions. Validate with `scripts/schwab_smoke_test.py` after OAuth.
8. **Earnings filter caches for 24h** in `~/.tradex/earnings_cache.db`. If a user just announced earnings and the date isn't showing, delete that file to force a refresh.
9. **Line endings are pinned by `.gitattributes`** — don't override `core.autocrlf` for this repo or the launcher scripts will break. The repo enforces CRLF for `.bat`/`.ps1` and LF for `tradex-launcher` automatically.
10. **Streamlit prints `use_container_width` deprecation warnings** at startup. Harmless — they refer to an API the dashboard uses; will be cleaned up in a future commit.

---

## 14. Navigation cheat-sheet for the user

Once the dashboard is running at `http://localhost:8501`:

| Tab | First time? Start here |
|---|---|
| **Scanner** | Pick a watchlist in the sidebar, pick a timeframe (intraday / short / long), set `min_score` (try 40), click Scan. |
| **Coil Detector** | Needs scan history across several NYSE trading sessions to detect coiling stocks; appears count distinct sessions, not scan rows. |
| **Confluence** | Stocks scoring well across all three timeframes simultaneously. Missing timeframes contribute zero and are shown as `0/3`–`3/3` coverage. `all timeframes aligned` requires 3/3 coverage and all active. |
| **Pattern Similarity — Experimental Research** | Compares current 10-day windows against historical run-up / decline fingerprints. Research-only; not used in production scoring or automatic alerts. |
| **Pre-Market** | Gap-up / gap-down detection vs. previous close with optional liquidity, spread, catalyst, and freshness filters. All new filters are off by default. |
| **Options Activity** | Two separate sections: true options-flow events (Unusual Whales) and options-chain snapshots (Tradier/Yahoo). Chain volume/OI is non-directional. The true-flow scanner is disabled if no Unusual Whales key is configured. |
| **Alerts** | Configure Discord / email thresholds, view effective cooldown durations, and inspect recent persistent alert state. Requires `.env` credentials for notifications. |
| **Signal Journal** | Win rate and expectancy by score bucket, plus signal/outcome provider columns — only meaningful after weeks of watcher runs. |
| **Weights** | Tune per-signal point values. Persists to `~/.tradex/weights.json`. |
| **Help** | In-app docs for every feature. |

---

## 15. After-setup sanity checks (agent should run these)

Before reporting success to the user, the agent should verify:
- [ ] `.venv/` exists and contains `streamlit`
- [ ] `.env` exists (even if mostly empty — at minimum `DATA_PROVIDER=schwab` or `DATA_PROVIDER=yahoo`)
- [ ] `~/.tradex/config` exists and `TRADEX_HOME` resolves to a directory containing `pyproject.toml`
- [ ] `streamlit run tradex/ui/dashboard.py` (via the venv) starts a server on port 8501 without crashing in the first 10 seconds
- [ ] On macOS: `launchers/macos/TradeX.app/Contents/MacOS/tradex-launcher` is executable (`-rwxr-xr-x`)
- [ ] On Windows: `launchers\windows\TradeX.bat` has CRLF line endings (open in Notepad → no jumbled-onto-one-line text)
- [ ] `uv run pytest tests -q` reports over 1,200 credential-free tests (no credentials or network required)

Report any failures. Do not silently skip.
