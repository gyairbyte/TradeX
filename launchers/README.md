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

### Install the launcher
1. Right-click `launchers\windows\TradeX.bat` → **Create shortcut**.
2. Move the shortcut wherever you want it (Desktop, Start Menu).
3. Right-click the shortcut → **Properties** → **Change Icon...** → browse to `launchers\windows\TradeX.ico`.
4. Optional: right-click the shortcut → **Pin to taskbar**.

### Note on PowerShell execution policy
`TradeX.bat` invokes PowerShell with `-ExecutionPolicy Bypass`, so the default Windows policy won't block it. No manual policy change required.

---

## Regenerating the icon

```bash
.venv/bin/python launchers/make_icon.py        # macOS / Linux
.venv\Scripts\python launchers\make_icon.py    # Windows
```

Writes `TradeX.icns` (Mac) and `TradeX.ico` (Windows).

---

## Line endings & exec bit

The repo's `.gitattributes` enforces:
- `*.bat`, `*.ps1`, `*.cmd` → **CRLF** (Windows-correct on any clone)
- `tradex-launcher` → **LF** (so the `#!/bin/bash` shebang parses on macOS)
- `*.icns`, `*.ico`, `*.png` → binary (never line-end-converted)

Git also tracks the macOS launcher with mode `100755`, preserving the executable bit through clone/checkout.
