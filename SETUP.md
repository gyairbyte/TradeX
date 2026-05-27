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
Only install what the user actually uses. Default `yahoo` provider needs nothing extra.
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

Key variables:
| Variable | Required? | Notes |
|---|---|---|
| `DATA_PROVIDER` | Yes | One of `yahoo`, `alpaca`, `ibkr`, `schwab`. Default `yahoo`. |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Only for Alpaca | From alpaca.markets dashboard |
| `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` | Only for Schwab | From developer.schwab.com |
| `IBKR_HOST` / `IBKR_PORT` | Only for IBKR | TWS or Gateway must be running locally |
| `DISCORD_BOT_TOKEN` / `DISCORD_CHANNEL_ID` | Only for Discord alerts | Optional |
| `SMTP_*` | Only for email alerts | Optional |

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
.venv/bin/python -m tradex.tracker.watcher --timeframe intraday --interval 5

# Windows
.venv\Scripts\python -m tradex.tracker.watcher --timeframe intraday --interval 5
```

Run during market hours. The outcome-tracker pass fires daily at 4:30pm ET automatically.

---

## 7. Known caveats and gotchas

1. **macOS Gatekeeper blocks the first launch** of `TradeX.app`. Right-click → Open the first time. Subsequent double-clicks work normally.
2. **The launcher needs `~/.tradex/config`** (or `$TRADEX_HOME`) when run from outside the repo (e.g. from `/Applications`). If you see "Could not locate the TradeX project directory," go back to step 3.
3. **The `.venv` must live at `<repo>/.venv`** — the launchers won't find it anywhere else. If you already have a venv at a different path, recreate it at `.venv`.
4. **Port 8501 must be free** for the dashboard. The launchers reuse an existing server if 8501 is already listening, so double-clicking twice is safe — but if a *different* process holds 8501, change Streamlit's port: `streamlit run ... --server.port=8502`.
5. **yfinance rate-limits** — large watchlists (100+ tickers) on the default Yahoo provider may hit transient failures. The screener prints `[skip] <ticker>: <reason>` and continues; this is expected.
6. **TD Ameritrade is dead** — its API shut down September 2024. Use `DATA_PROVIDER=schwab` (their replacement) instead. Do not reference the old `tda-api` library.
7. **Earnings filter caches for 24h** in `~/.tradex/earnings_cache.db`. If a user just announced earnings and the date isn't showing, delete that file to force a refresh.
8. **Line endings are pinned by `.gitattributes`** — don't override `core.autocrlf` for this repo or the launcher scripts will break. The repo enforces CRLF for `.bat`/`.ps1` and LF for `tradex-launcher` automatically.
9. **Streamlit prints `use_container_width` deprecation warnings** at startup. Harmless — they refer to an API the dashboard uses; will be cleaned up in a future commit.

---

## 8. Navigation cheat-sheet for the user

Once the dashboard is running at `http://localhost:8501`:

| Tab | First time? Start here |
|---|---|
| **Scanner** | Pick a watchlist in the sidebar, pick a timeframe (intraday / short / long), set `min_score` (try 40), click Scan. |
| **Coil Detector** | Only meaningful after the watcher has been running for several days — needs scan history to detect coiling stocks. |
| **Confluence** | Stocks scoring well across all three timeframes simultaneously. Fast to compute, no history needed. |
| **Pattern Match** | Compares current 10-day windows against historical run-up / decline fingerprints. |
| **Pre-Market** | Gap-up / gap-down detection vs. previous close. Only useful between ~7am and 9:30am ET. |
| **Options Flow** | Unusual options volume vs. open interest. Requires market hours for live data. |
| **Alerts** | Configure Discord / email thresholds. Requires `.env` credentials. |
| **Signal Journal** | Win rate and expectancy by score bucket — only meaningful after weeks of watcher runs. |
| **Weights** | Tune per-signal point values. Persists to `~/.tradex/weights.json`. |
| **Help** | In-app docs for every feature. |

---

## 9. After-setup sanity checks (agent should run these)

Before reporting success to the user, the agent should verify:
- [ ] `.venv/` exists and contains `streamlit`
- [ ] `.env` exists (even if mostly empty — at minimum `DATA_PROVIDER=yahoo`)
- [ ] `~/.tradex/config` exists and `TRADEX_HOME` resolves to a directory containing `pyproject.toml`
- [ ] `streamlit run tradex/ui/dashboard.py` (via the venv) starts a server on port 8501 without crashing in the first 10 seconds
- [ ] On macOS: `launchers/macos/TradeX.app/Contents/MacOS/tradex-launcher` is executable (`-rwxr-xr-x`)
- [ ] On Windows: `launchers\windows\TradeX.bat` has CRLF line endings (open in Notepad → no jumbled-onto-one-line text)

Report any failures. Do not silently skip.
