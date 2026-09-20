# TradeX Stop launcher (Windows / PowerShell)
# Identifies and cleanly terminates the TradeX dashboard process tree.
#
# Defense-in-depth identification:
#   1. Persisted dashboard PID (%USERPROFILE%\.tradex\dashboard.pid)
#   2. Listening process on port 8501
#   3. Running process command line matching canonical tradex\ui\dashboard.py
#
# Invariant: Only processes verified as belonging to this TradeX installation are terminated.
# Unrelated processes on port 8501 are NEVER terminated.

[CmdletBinding()]
param (
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$LogDir  = Join-Path $env:USERPROFILE ".tradex"
$PidFile = Join-Path $LogDir "dashboard.pid"

function Show-Message($message, $title = "TradeX", $icon = "Information") {
    if ($Quiet) {
        Write-Host "[$icon] $($title): $message"
        return
    }
    try {
        Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
        [System.Windows.MessageBox]::Show($message, $title, "OK", $icon) | Out-Null
    } catch {
        Write-Host "[$icon] $($title): $message"
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
    Show-Message "Could not locate the TradeX project directory.`n`nFix: create %USERPROFILE%\.tradex\config with a single line:`n  TRADEX_HOME=C:\absolute\path\to\tradex`n`nOr set the TRADEX_HOME environment variable." "TradeX Stop" "Error"
    exit 1
}

$Dashboard = Join-Path $ProjectRoot "tradex\ui\dashboard.py"
$CanonicalDashboard = if (Test-Path $Dashboard) { (Resolve-Path $Dashboard).Path } else { $Dashboard }

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

# --- 1. Gather candidate PIDs from evidence sources ---
$candidatePids = @()

# Evidence Source 1: Persisted PID file
if (Test-Path $PidFile) {
    try {
        $fileContent = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($fileContent -match '^\d+$') {
            $candidatePids += [int]$fileContent
        }
    } catch {}
}

# Evidence Source 2: Active listeners on port 8501
$portListeners = Get-PortListeners 8501
foreach ($lp in $portListeners) {
    $candidatePids += [int]$lp
}

# Evidence Source 3: Process table search for dashboard.py
try {
    $runningProcesses = Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue
    foreach ($rp in $runningProcesses) {
        if ($rp.CommandLine -and $rp.CommandLine.ToLowerInvariant().Contains("dashboard.py")) {
            $candidatePids += [int]$rp.ProcessId
        }
    }
} catch {}

$uniqueCandidates = @($candidatePids | Select-Object -Unique)

# --- 2. Defense-in-depth verification ---
$verifiedTradeXPids = @()
foreach ($candPid in $uniqueCandidates) {
    if (Test-IsTradeXProcess $candPid $CanonicalDashboard) {
        $verifiedTradeXPids += $candPid
    }
}

# --- 3. Process termination or report ---
if ($verifiedTradeXPids.Count -gt 0) {
    # Expand to complete TradeX process tree (parents + children)
    $treePids = @()
    foreach ($vPid in $verifiedTradeXPids) {
        $treePids += $vPid
        try {
            $proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $vPid" -ErrorAction SilentlyContinue
            if ($proc) {
                if ($proc.ParentProcessId -and $proc.ParentProcessId -gt 0) {
                    if (Test-IsTradeXProcess $proc.ParentProcessId $CanonicalDashboard) {
                        $treePids += $proc.ParentProcessId
                    }
                }
                $children = Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $vPid" -ErrorAction SilentlyContinue
                foreach ($child in $children) {
                    $treePids += $child.ProcessId
                }
            }
        } catch {}
    }

    $targetsToKill = @($treePids | Select-Object -Unique)

    # Terminate the verified TradeX processes
    foreach ($targetPid in $targetsToKill) {
        try {
            Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        } catch {}
    }

    # If any root process is still alive after brief wait, use taskkill
    Start-Sleep -Milliseconds 500
    foreach ($rootPid in ($verifiedTradeXPids | Select-Object -Unique)) {
        if (Get-Process -Id $rootPid -ErrorAction SilentlyContinue) {
            try {
                Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", $rootPid, "/T", "/F") -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
            } catch {}
        }
    }

    # Wait up to 10s to confirm port 8501 is released
    $portReleased = $false
    for ($i = 0; $i -lt 20; $i++) {
        $remaining = Get-PortListeners 8501
        if ($remaining.Count -eq 0) {
            $portReleased = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    # Remove stale runtime PID metadata
    if (Test-Path $PidFile) {
        Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
    }

    if ($portReleased) {
        Show-Message "TradeX dashboard has been stopped." "TradeX" "Information"
        exit 0
    }

    Show-Message "TradeX shutdown could not be fully confirmed: port 8501 is still listening after the timeout." "TradeX Stop" "Warning"
    exit 1
}

# --- 4. No verified TradeX process found ---
# Check if port 8501 is occupied by an unrelated application
$activeListeners = Get-PortListeners 8501
if ($activeListeners.Count -gt 0) {
    $occupantPid = $activeListeners[0]
    $occupantProc = Get-Process -Id $occupantPid -ErrorAction SilentlyContinue
    $occupantName = if ($occupantProc) { $occupantProc.ProcessName } else { "Unknown" }
    Show-Message "Port 8501 is occupied by an unrelated application (PID $($occupantPid): $occupantName).`n`nTradeX is not running on port 8501 and will not terminate this process." "TradeX Stop" "Warning"
    exit 1
}

# Free port, clean up any stale PID file
if (Test-Path $PidFile) {
    Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
}

Show-Message "TradeX is not currently running." "TradeX" "Information"
exit 0
