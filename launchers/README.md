# TradeX Desktop Launchers

Cross-platform launchers that start the Streamlit dashboard and open it in the default browser.

Both launchers:
- Reuse an existing server if port `8501` is already listening (clicking twice won't spawn a second instance).
- Run Streamlit headless and open the browser once the port is up.
- Log to `~/.tradex/dashboard.log`.

Both assume the project venv lives at `<repo>/.venv` with `streamlit` installed. The venv is **not** committed (it's in `.gitignore`), so each machine needs to create it once — see the per-OS sections below.

The launchers find the repo using this lookup, in order:
1. `$TRADEX_HOME` environment variable
2. `~/.tradex/config` (single line: `TRADEX_HOME=/abs/path/to/repo`)
3. Walking up from the launcher's own location (only works if the launcher hasn't been copied out of the repo)

You only need (1) or (2) if you copy the launcher outside the repo (e.g. drag `TradeX.app` to `/Applications`).

---

## macOS

### One-time setup (fresh clone)
```bash
cd tradex
uv sync                        # or: python3.11 -m venv .venv && .venv/bin/pip install -e .
```

### Point the launcher at the repo (only needed if you move the .app outside the repo)
```bash
mkdir -p ~/.tradex
echo "TRADEX_HOME=$(pwd)" > ~/.tradex/config
```

### Install the launcher
1. Drag `launchers/macos/TradeX.app` to `/Applications` (or anywhere — Desktop works).
2. First launch: right-click → **Open** to bypass Gatekeeper (the app is unsigned).
3. Optional: keep it in the Dock for one-click access.

If the icon doesn't refresh in Finder: `touch launchers/macos/TradeX.app`.

---

## Windows
 
### One-time setup (fresh clone)
Open PowerShell in the repo root:
```powershell
# If you have uv:
uv sync

# Otherwise, with a Python 3.11+ install on PATH:
python -m venv .venv
.venv\Scripts\pip install -e .
```

Verify `.venv\Scripts\streamlit.exe` exists before continuing.

### Point the launcher at the repo (only needed if you move the shortcut outside the repo)
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.tradex" | Out-Null
"TRADEX_HOME=$(Get-Location)" | Out-File -Encoding ascii "$env:USERPROFILE\.tradex\config"
```

### Install Desktop shortcuts (recommended)
Run the automated shortcut installer from PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File launchers\windows\install_desktop_shortcuts.ps1
```
This automatically creates:
- `Start TradeX.lnk` (points to `TradeX.bat`, with `TradeX.ico`)
- `Stop TradeX.lnk` (points to `TradeX-Stop.bat`, with `TradeX-Stop.ico`)
directly on your Windows Desktop.

### Manual shortcut creation (alternative)
1. Right-click `launchers\windows\TradeX.bat` → **Create shortcut** → move to Desktop as `Start TradeX.lnk`.
2. Properties → **Change Icon...** → browse to `launchers\windows\TradeX.ico`.
3. Right-click `launchers\windows\TradeX-Stop.bat` → **Create shortcut** → move to Desktop as `Stop TradeX.lnk`.
4. Properties → **Change Icon...** → browse to `launchers\windows\TradeX-Stop.ico`.

### Process identity and safety invariants
- **Port 8501 is not identity**: Neither launcher treats port 8501 as proof of TradeX. The listener command line is inspected via `Get-CimInstance Win32_Process` and must match the canonical dashboard (`<repo>\tradex\ui\dashboard.py`).
- **Start launcher**: Captures the spawned Streamlit PID (`Start-Process -PassThru`), verifies port 8501 ownership, and writes `%USERPROFILE%\.tradex\dashboard.pid`. Unrelated applications holding port 8501 are never killed; Start fails safely with a descriptive error.
- **Stop launcher**: Employs defense in depth across the persisted PID file, port 8501 listeners, and `Win32_Process` process table. Only confirmed TradeX process trees are terminated. It verifies port 8501 is released, cleans up `dashboard.pid`, and reports confirmation. Unrelated applications on port 8501 are never terminated.

### Note on PowerShell execution policy
`TradeX.bat` and `TradeX-Stop.bat` invoke PowerShell with `-ExecutionPolicy Bypass`, so the default Windows policy won't block them. No manual policy change required.

---

## Regenerating the icons

```bash
.venv/bin/python launchers/make_icon.py        # macOS / Linux
.venv\Scripts\python launchers\make_icon.py    # Windows
```

Generates:
- `TradeX.ico` & `tradex_icon.png`: TradeX slate-900 background, slate-200 TX wordmark, green rising-candle motif.
- `TradeX-Stop.ico` & `tradex_stop_icon.png`: Same slate-900 background, slate-200 TX wordmark, red stop-themed motif.
- `TradeX.icns` (macOS, if `iconutil` is available).

---

## Line endings & exec bit

The repo's `.gitattributes` enforces:
- `*.bat`, `*.ps1`, `*.cmd` → **CRLF** (Windows-correct on any clone)
- `tradex-launcher` → **LF** (so the `#!/bin/bash` shebang parses on macOS)
- `*.icns`, `*.ico`, `*.png` → binary (never line-end-converted)

Git also tracks the macOS launcher with mode `100755`, preserving the executable bit through clone/checkout.
