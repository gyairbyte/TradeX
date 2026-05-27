# TradeX launcher (Windows / PowerShell)
# Starts the Streamlit dashboard and opens the default browser.

$ErrorActionPreference = "Stop"

# Resolve the project root by walking up from this script.
# Script lives at: <PROJECT_ROOT>\launchers\windows\TradeX.ps1
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

$VenvStreamlit = Join-Path $ProjectRoot ".venv\Scripts\streamlit.exe"
$Dashboard     = Join-Path $ProjectRoot "tradex\ui\dashboard.py"
$LogDir        = Join-Path $env:USERPROFILE ".tradex"
$LogFile       = Join-Path $LogDir "dashboard.log"
$Url           = "http://localhost:8501"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Show-Error($message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($message, "TradeX cannot start", "OK", "Error") | Out-Null
}

if (-not (Test-Path $VenvStreamlit)) {
    Show-Error "Could not find .venv\Scripts\streamlit.exe. Run `uv sync` (or `pip install -e .`) in the project directory first."
    exit 1
}

if (-not (Test-Path $Dashboard)) {
    Show-Error "Dashboard not found at $Dashboard"
    exit 1
}

function Test-PortListening($port) {
    try {
        $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop
        return $conns.Count -gt 0
    } catch {
        return $false
    }
}

# If already running, just open the browser.
if (Test-PortListening 8501) {
    Start-Process $Url
    exit 0
}

Set-Location $ProjectRoot

# Launch Streamlit in a hidden background process. --server.headless skips its
# built-in browser open; we open the browser ourselves once the port is live.
Start-Process -FilePath $VenvStreamlit `
    -ArgumentList @("run", $Dashboard, "--server.headless=true", "--server.port=8501") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError  "$LogFile.err"

# Wait up to ~20s for the port to come up.
for ($i = 0; $i -lt 40; $i++) {
    if (Test-PortListening 8501) {
        Start-Process $Url
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

Show-Error "TradeX did not start in time. Check the log at $LogFile"
exit 1
