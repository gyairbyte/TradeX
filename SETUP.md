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
Default `yahoo` provider needs nothing extra. For the full test suite and every provider used in CI, install the `all` extra together with `dev`:
```bash
uv sync --extra dev --extra all
```

To add only specific providers after a base `uv sync`:
```bash
uv pip install -e ".[alpaca]"   # Alpaca real-time (free tier)
uv pip install -e ".[ibkr]"     # Interactive Brokers (requires local TWS/Gateway)
uv pip install -e ".[schwab]"   # Charles Schwab (requires OAuth app)
uv pip install -e ".[all]"      # Everything
```

---

## 2. Configure environment variables

```bash
cp .env.example .env      # macOS / Linux
copy .env.example .env    # Windows
```

`.env` is gitignored — credentials never leave the machine. Open `.env` and fill in only what the user needs. **Do not invent values.** If the user hasn't said which provider they want, default to `DATA_PROVIDER=yahoo` (no credentials required) and ask about the others.

`DATA_PROVIDER` controls **OHLCV data** only. Options flow, earnings, and market-cap ranking have their own source overrides (see `.env.example`).

Signal history records the OHLCV provider that produced each signal (`signal_history.provider`), and resolved outcomes record `outcome_provider`. Every scan now writes a `scan_sessions` row and one `scan_observations` row per ticker requested, including tickers that scored below threshold or failed to fetch. A linked `scan_runs` audit row records `tickers_n` (requested), `hits_n` (qualifying signals), `status` (completed / partial / failed / unknown), `requested_provider` / `actual_provider`, and `source` (native / compatibility / legacy). Pre-existing databases are migrated safely; rows created before this feature are labeled `unknown` and assigned to synthetic legacy sessions, while old `scan_runs` rows are preserved with `source='legacy'` and `counts_complete=0`.

Key variables:
| Variable | Required? | Notes |
|---|---|---|
| `DATA_PROVIDER` | Yes | OHLCV provider: `yahoo`, `alpaca`, `ibkr`, `schwab`. Default `yahoo`. |
| `OHLCV_MAX_RETRIES` | No | Extra retry attempts per ticker for transient failures only. Default `0`, max `3`. |
| `OHLCV_FALLBACK_ORDER` | No | Comma-separated whole-scan fallback provider chain (e.g. `schwab,yahoo`). Empty/missing = disabled. |
| `OPTIONS_DATA_SOURCE` | No | `auto` (default), `unusual_whales`, `tradier`, `yahoo` |
| `EARNINGS_DATA_SOURCE` | No | `yahoo` (default) |
| `MARKET_CAP_DATA_SOURCE` | No | `yahoo` (default), `schwab` |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Only for Alpaca | From alpaca.markets dashboard |
| `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` | Only for Schwab | From developer.schwab.com — also requires OAuth bootstrap (see §3a) |
| `IBKR_HOST` / `IBKR_PORT` | Only for IBKR | TWS or Gateway must be running locally |
| `DISCORD_BOT_TOKEN` / `DISCORD_CHANNEL_ID` | Only for Discord alerts | Optional |
| `SMTP_*` | Only for email alerts | Optional |

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

After generating the token, run the read-only smoke test to confirm Schwab market data works:

```bash
.venv/bin/python scripts/schwab_smoke_test.py
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

The watcher runs the screener on an interval and writes results to `~/.tradex/signals.db`. This is what powers the **Coil Detector** and **Signal Journal** tabs over time.

```bash
# macOS / Linux
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only

# Windows
.venv\Scripts\python -m tradex.tracker.watcher --timeframe intraday --interval 5 --market-hours-only
```

Run during market hours. With `--market-hours-only`, scans are skipped outside the NYSE regular session (weekends, NYSE holidays including Good Friday, and early-close days are handled automatically via the `exchange-calendars` XNYS calendar). Manual one-off scans omit the flag. The daily pre-market gap scan fires at `08:00 America/New_York` and the outcome pass at `16:30 America/New_York`; both stay at the same New York wall-clock time across DST changes and skip non-trading days. The watcher persists the effective `provider` with each scan run and outcome pass.

---

## 7. Backtesting (optional)

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

## 8. Score-validation study (optional)

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

## 9. Short-term market context research (optional)

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

---

## 10. Known caveats and gotchas

1. **macOS Gatekeeper blocks the first launch** of `TradeX.app`. Right-click → Open the first time. Subsequent double-clicks work normally.
2. **The launcher needs `~/.tradex/config`** (or `$TRADEX_HOME`) when run from outside the repo (e.g. from `/Applications`). If you see "Could not locate the TradeX project directory," go back to step 3.
3. **The `.venv` must live at `<repo>/.venv`** — the launchers won't find it anywhere else. If you already have a venv at a different path, recreate it at `.venv`.
4. **Port 8501 must be free** for the dashboard. The launchers reuse an existing server if 8501 is already listening, so double-clicking twice is safe — but if a *different* process holds 8501, change Streamlit's port: `streamlit run ... --server.port=8502`.
5. **yfinance rate-limits** — large watchlists (100+ tickers) on the default Yahoo provider may hit transient failures. The screener logs the failure category and continues. You can set `OHLCV_MAX_RETRIES` (max 3) for automatic retry of transient network errors, and `OHLCV_FALLBACK_ORDER` to enable a whole-scan fallback chain.
6. **TD Ameritrade is dead** — its API shut down September 2024. Use `DATA_PROVIDER=schwab` (their replacement) instead. Do not reference the old `tda-api` library.
7. **Schwab token path** — keep `SCHWAB_TOKEN_PATH` outside the repo; `scripts/schwab_oauth.py` enforces this and sets restrictive file permissions. Validate with `scripts/schwab_smoke_test.py` after OAuth.
8. **Earnings filter caches for 24h** in `~/.tradex/earnings_cache.db`. If a user just announced earnings and the date isn't showing, delete that file to force a refresh.
9. **Line endings are pinned by `.gitattributes`** — don't override `core.autocrlf` for this repo or the launcher scripts will break. The repo enforces CRLF for `.bat`/`.ps1` and LF for `tradex-launcher` automatically.
10. **Streamlit prints `use_container_width` deprecation warnings** at startup. Harmless — they refer to an API the dashboard uses; will be cleaned up in a future commit.

---

## 11. Navigation cheat-sheet for the user

Once the dashboard is running at `http://localhost:8501`:

| Tab | First time? Start here |
|---|---|
| **Scanner** | Pick a watchlist in the sidebar, pick a timeframe (intraday / short / long), set `min_score` (try 40), click Scan. |
| **Coil Detector** | Needs scan history across several NYSE trading sessions to detect coiling stocks; appears count distinct sessions, not scan rows. |
| **Confluence** | Stocks scoring well across all three timeframes simultaneously. Missing timeframes contribute zero and are shown as `0/3`–`3/3` coverage. `all timeframes aligned` requires 3/3 coverage and all active. |
| **Pattern Match** | Compares current 10-day windows against historical run-up / decline fingerprints. |
| **Pre-Market** | Gap-up / gap-down detection vs. previous close. Only useful between ~7am and 9:30am ET. |
| **Options Flow** | Unusual options volume vs. open interest. Requires market hours for live data. |
| **Alerts** | Configure Discord / email thresholds. Requires `.env` credentials. |
| **Signal Journal** | Win rate and expectancy by score bucket, plus signal/outcome provider columns — only meaningful after weeks of watcher runs. |
| **Weights** | Tune per-signal point values. Persists to `~/.tradex/weights.json`. |
| **Help** | In-app docs for every feature. |

---

## 12. After-setup sanity checks (agent should run these)

Before reporting success to the user, the agent should verify:
- [ ] `.venv/` exists and contains `streamlit`
- [ ] `.env` exists (even if mostly empty — at minimum `DATA_PROVIDER=yahoo`)
- [ ] `~/.tradex/config` exists and `TRADEX_HOME` resolves to a directory containing `pyproject.toml`
- [ ] `streamlit run tradex/ui/dashboard.py` (via the venv) starts a server on port 8501 without crashing in the first 10 seconds
- [ ] On macOS: `launchers/macos/TradeX.app/Contents/MacOS/tradex-launcher` is executable (`-rwxr-xr-x`)
- [ ] On Windows: `launchers\windows\TradeX.bat` has CRLF line endings (open in Notepad → no jumbled-onto-one-line text)

Report any failures. Do not silently skip.
