# TradeX launcher (Windows / PowerShell)
# Starts the Streamlit dashboard and opens the default browser.
#
# Resolves the project root in this order:
#   1. $env:TRADEX_HOME environment variable
#   2. %USERPROFILE%\.tradex\config  (single line: TRADEX_HOME=C:\path\to\repo)
#   3. Walking up from the script location (works when launched in-place from the repo)

$ErrorActionPreference = "Stop"

$LogDir  = Join-Path $env:USERPROFILE ".tradex"
$LogFile = Join-Path $LogDir "dashboard.log"
$Url     = "http://localhost:8501"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Show-Error($message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($message, "TradeX cannot start", "OK", "Error") | Out-Null
}

function Resolve-ProjectRoot {
    # 1. Environment variable
    if ($env:TRADEX_HOME -and (Test-Path $env:TRADEX_HOME -PathType Container)) {
        return (Resolve-Path $env:TRADEX_HOME).Path
    }

    # 2. User config file
    $ConfigPath = Join-Path $env:USERPROFILE ".tradex\config"
    if (Test-Path $ConfigPath) {
        $line = Get-Content $ConfigPath | Where-Object { $_ -match '^TRADEX_HOME=' } | Select-Object -First 1
        if ($line) {
            $path = ($line -replace '^TRADEX_HOME=', '').Trim().Trim('"').Trim("'")
            if ($path -and (Test-Path $path -PathType Container)) {
                return (Resolve-Path $path).Path
            }
        }
    }

    # 3. Walk up from the script location
    $ScriptDir = Split-Path -Parent $MyInvocation.PSCommandPath
    $Candidate = Resolve-Path (Join-Path $ScriptDir "..\..") -ErrorAction SilentlyContinue
    if ($Candidate -and (Test-Path (Join-Path $Candidate "pyproject.toml")) -and (Test-Path (Join-Path $Candidate "tradex"))) {
        return $Candidate.Path
    }

    return $null
}

$ProjectRoot = Resolve-ProjectRoot

if (-not $ProjectRoot) {
    Show-Error "Could not locate the TradeX project directory.`n`nFix: create %USERPROFILE%\.tradex\config with a single line:`n  TRADEX_HOME=C:\absolute\path\to\tradex`n`nOr set the TRADEX_HOME environment variable."
    exit 1
}

$VenvStreamlit = Join-Path $ProjectRoot ".venv\Scripts\streamlit.exe"
$Dashboard     = Join-Path $ProjectRoot "tradex\ui\dashboard.py"

if (-not (Test-Path $VenvStreamlit)) {
    Show-Error "Could not find streamlit at:`n$VenvStreamlit`n`nRun ``uv sync`` (or ``pip install -e .``) in the project directory first."
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
