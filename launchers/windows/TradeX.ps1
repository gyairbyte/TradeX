# TradeX launcher (Windows / PowerShell)
# Starts the Streamlit dashboard and opens the default browser.
#
# Resolves the project root in this order:
#   1. $env:TRADEX_HOME environment variable
#   2. %USERPROFILE%\.tradex\config  (single line: TRADEX_HOME=C:\path\to\repo)
#   3. Walking up from the script location (works when launched in-place from the repo)

[CmdletBinding()]
param (
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$LogDir  = Join-Path $env:USERPROFILE ".tradex"
$LogFile = Join-Path $LogDir "dashboard.log"
$PidFile = Join-Path $LogDir "dashboard.pid"
$Url     = "http://localhost:8501"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Show-Error($message) {
    if ($Quiet) {
        Write-Error $message
        return
    }
    try {
        Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
        [System.Windows.MessageBox]::Show($message, "TradeX cannot start", "OK", "Error") | Out-Null
    } catch {
        Write-Error $message
    }
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

$CanonicalDashboard = (Resolve-Path $Dashboard).Path

function Get-PortListeners($port) {
    try {
        $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($conns) {
            return @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
        }
    } catch {}
    return @()
}

function Get-ProcessCommandLine($procId) {
    try {
        $proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
        if ($proc) {
            return $proc.CommandLine
        }
    } catch {}
    return $null
}

function Test-IsTradeXProcess($procId, $expectedDashboardPath) {
    if (-not $procId -or -not $expectedDashboardPath) {
        return $false
    }
    $normTarget = $expectedDashboardPath.Trim().ToLowerInvariant().Replace("/", "\")
    $relativeTail = (Join-Path "tradex" (Join-Path "ui" "dashboard.py")).ToLowerInvariant().Replace("/", "\")
    $repoRootNorm = $ProjectRoot.Trim().ToLowerInvariant().Replace("/", "\")

    # Check candidate process itself, plus its parent and immediate children
    $candidatePids = @($procId)
    try {
        $proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
        if ($proc) {
            if ($proc.ParentProcessId -and $proc.ParentProcessId -gt 0) {
                $candidatePids += $proc.ParentProcessId
            }
            $children = Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $procId" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                $candidatePids += $child.ProcessId
            }
        }
    } catch {}

    foreach ($pidToCheck in ($candidatePids | Select-Object -Unique)) {
        $cmd = Get-ProcessCommandLine $pidToCheck
        if ($cmd) {
            $normCmd = $cmd.ToLowerInvariant().Replace("/", "\")
            if ($normCmd.Contains($normTarget)) {
                return $true
            }
            if ($normCmd.Contains($relativeTail) -and $normCmd.Contains($repoRootNorm)) {
                return $true
            }
        }
    }
    return $false
}

# --- Check current listener on port 8501 ---
$existingListeners = Get-PortListeners 8501
if ($existingListeners.Count -gt 0) {
    $verifiedExistingPid = $null
    foreach ($lp in $existingListeners) {
        if (Test-IsTradeXProcess $lp $CanonicalDashboard) {
            $verifiedExistingPid = $lp
            break
        }
    }

    if ($verifiedExistingPid) {
        # TradeX is already running; refresh PID metadata and open browser.
        "$verifiedExistingPid" | Out-File -Encoding ascii -FilePath $PidFile
        Start-Process $Url
        exit 0
    } else {
        # Port 8501 is occupied by an unrelated process.
        $occupantPid = $existingListeners[0]
        $occupantProc = Get-Process -Id $occupantPid -ErrorAction SilentlyContinue
        $occupantName = if ($occupantProc) { $occupantProc.ProcessName } else { "Unknown" }
        Show-Error "Port 8501 is already in use by an unrelated application (PID $($occupantPid): $occupantName).`n`nTradeX cannot start on port 8501. Please stop the conflicting application or configure a different port."
        exit 1
    }
}

# --- Clean up stale PID file if present ---
if (Test-Path $PidFile) {
    try {
        $rawPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($rawPid -match '^\d+$') {
            $stalePid = [int]$rawPid
            if (-not (Test-IsTradeXProcess $stalePid $CanonicalDashboard)) {
                Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
            }
        } else {
            Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
        }
    } catch {
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
    }
}

Set-Location $ProjectRoot

# Launch Streamlit in a hidden background process.
$spawnedProcess = Start-Process -FilePath $VenvStreamlit `
    -ArgumentList @("run", $Dashboard, "--server.headless=true", "--server.port=8501") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError  "$LogFile.err" `
    -PassThru

$spawnedPid = $spawnedProcess.Id

# Wait up to ~20s for confirmed TradeX listener on port 8501.
$confirmedPid = $null
for ($i = 0; $i -lt 40; $i++) {
    $activeListeners = Get-PortListeners 8501
    if ($activeListeners.Count -gt 0) {
        foreach ($lp in $activeListeners) {
            if (Test-IsTradeXProcess $lp $CanonicalDashboard) {
                $confirmedPid = $lp
                break
            }
        }

        if ($confirmedPid) {
            break
        } else {
            # Port is listening but belongs to something else!
            $occupantPid = $activeListeners[0]
            $occupantProc = Get-Process -Id $occupantPid -ErrorAction SilentlyContinue
            $occupantName = if ($occupantProc) { $occupantProc.ProcessName } else { "Unknown" }
            Show-Error "Port 8501 became occupied by an unrelated application (PID $($occupantPid): $occupantName) during startup."
            if (Test-Path $PidFile) {
                Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
            }
            exit 1
        }
    }
    Start-Sleep -Milliseconds 500
}

if ($confirmedPid) {
    "$confirmedPid" | Out-File -Encoding ascii -FilePath $PidFile
    Start-Process $Url
    exit 0
}

# Startup timed out. Clean up unverified PID file and report error.
if (Test-Path $PidFile) {
    Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
}
Show-Error "TradeX did not start in time. Check the log at $LogFile"
exit 1
