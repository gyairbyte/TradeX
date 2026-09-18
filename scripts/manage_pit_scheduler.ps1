# scripts/manage_pit_scheduler.ps1
# Deterministic Windows Task Scheduler management asset for TradeX PIT slot capture.
#
# Tasks:
#   1. "TradeX PIT Morning" — 09:00 America/New_York
#   2. "TradeX PIT Evening" — 20:30 America/New_York
#
# Invariants:
#   - Fail-closed timezone check: host timezone must be 'Eastern Standard Time'
#     (Windows timezone for America/New_York with automatic DST).
#   - No credentials, API keys, or tokens embedded in task specifications.
#   - Execution uses 'uv run' in repo working directory so normal settings loader handles configuration.
#   - Missed catch-up disabled (StartWhenAvailable = false) so missed slots surface truthfully in health.
#   - Validate performs zero OS task mutations.

[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [ValidateSet("Validate", "Status", "Install", "Remove")]
    [string]$Action = "Validate",

    [Parameter()]
    [string]$ProjectRoot,

    [Parameter()]
    [string]$ManifestPath
)

$ErrorActionPreference = "Stop"

$MorningTaskName = "TradeX PIT Morning"
$EveningTaskName = "TradeX PIT Evening"
$ExpectedTimezone = "Eastern Standard Time"
$CanonicalManifestRelative = "docs\product\manifests\pit-universe-2026-09-21-v1.json"

function Resolve-RepoRoot {
    if ($ProjectRoot -and (Test-Path $ProjectRoot -PathType Container)) {
        return (Resolve-Path $ProjectRoot).Path
    }
    if ($env:TRADEX_HOME -and (Test-Path $env:TRADEX_HOME -PathType Container)) {
        return (Resolve-Path $env:TRADEX_HOME).Path
    }
    # Walk up from script location: scripts/ -> repo root
    $ScriptDir = Split-Path -Parent $MyInvocation.PSCommandPath
    $Candidate = Resolve-Path (Join-Path $ScriptDir "..") -ErrorAction SilentlyContinue
    if ($Candidate -and (Test-Path (Join-Path $Candidate "pyproject.toml")) -and (Test-Path (Join-Path $Candidate "tradex"))) {
        return $Candidate.Path
    }
    throw "Could not resolve TradeX project root directory. Set -ProjectRoot or TRADEX_HOME."
}

function Check-HostTimezone {
    $localTz = [System.TimeZoneInfo]::Local.Id
    if ($localTz -ne $ExpectedTimezone) {
        throw "Host timezone '$localTz' does not match required '$ExpectedTimezone' (America/New_York). " +
              "Windows Task Scheduler executes in host local time. " +
              "Fail closed to prevent scheduling outside intended market times (09:00 and 20:30 ET)."
    }
    return $localTz
}

function Resolve-UvPath {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        throw "Could not locate 'uv' executable in PATH. Install uv or ensure it is available."
    }
    return $uvCmd.Source
}

function Resolve-ManifestFile ($RootPath) {
    if ($ManifestPath) {
        if (-not (Test-Path $ManifestPath)) {
            throw "Specified manifest file not found: $ManifestPath"
        }
        return (Resolve-Path $ManifestPath).Path
    }
    $DefaultPath = Join-Path $RootPath $CanonicalManifestRelative
    if (-not (Test-Path $DefaultPath)) {
        throw "Canonical manifest file not found at default path: $DefaultPath"
    }
    return (Resolve-Path $DefaultPath).Path
}

function Invoke-Validate {
    Write-Host "=== Validating TradeX PIT Scheduler Configuration ===" -ForegroundColor Cyan

    # 1. Timezone check
    $tz = Check-HostTimezone
    Write-Host "[PASS] Host timezone: $tz (America/New_York compatible)" -ForegroundColor Green

    # 2. Project root check
    $root = Resolve-RepoRoot
    Write-Host "[PASS] Project root: $root" -ForegroundColor Green

    # 3. uv check
    $uv = Resolve-UvPath
    Write-Host "[PASS] uv executable: $uv" -ForegroundColor Green

    # 4. Manifest check
    $manifest = Resolve-ManifestFile $root
    Write-Host "[PASS] Manifest file: $manifest" -ForegroundColor Green

    # 5. CLI manifest validation (no network, pure contract check)
    Write-Host "Running CLI universe validation..." -ForegroundColor Yellow
    Push-Location $root
    try {
        $valOutput = & $uv run python -m tradex.pit.ops validate-universe --universe-file $manifest
        if ($LASTEXITCODE -ne 0) {
            throw "Manifest validation failed via 'tradex.pit.ops validate-universe':`n$valOutput"
        }
        Write-Host "[PASS] Manifest validated successfully via CLI." -ForegroundColor Green
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Task Specifications for future activation:" -ForegroundColor Cyan
    Write-Host "  Task 1: $MorningTaskName"
    Write-Host "    Trigger: Daily at 09:00 ($ExpectedTimezone)"
    Write-Host "    Action:  $uv run python -m tradex.pit.ops run-slot --slot morning --universe-file $manifest"
    Write-Host "    Working Dir: $root"
    Write-Host "    Catch-up policy: Disabled (StartWhenAvailable = false)"
    Write-Host "  Task 2: $EveningTaskName"
    Write-Host "    Trigger: Daily at 20:30 ($ExpectedTimezone)"
    Write-Host "    Action:  $uv run python -m tradex.pit.ops run-slot --slot evening --universe-file $manifest"
    Write-Host "    Working Dir: $root"
    Write-Host "    Catch-up policy: Disabled (StartWhenAvailable = false)"
    Write-Host ""
    Write-Host "Safe validation completed. No OS scheduled tasks were created or modified." -ForegroundColor Green
    return $true
}

function Invoke-Status {
    Write-Host "=== TradeX PIT Scheduled Tasks Status ===" -ForegroundColor Cyan

    $morning = Get-ScheduledTask -TaskName $MorningTaskName -ErrorAction SilentlyContinue
    $evening = Get-ScheduledTask -TaskName $EveningTaskName -ErrorAction SilentlyContinue

    if (-not $morning -and -not $evening) {
        Write-Host "Neither '$MorningTaskName' nor '$EveningTaskName' is currently registered." -ForegroundColor Yellow
        Write-Host "Scheduler is INACTIVE (no OS tasks installed)." -ForegroundColor Yellow
        return $false
    }

    if ($morning) {
        $info = Get-ScheduledTaskInfo -TaskName $MorningTaskName -ErrorAction SilentlyContinue
        Write-Host "Task: $MorningTaskName" -ForegroundColor Green
        Write-Host "  State:        $($morning.State)"
        Write-Host "  Last Run:     $($info.LastRunTime)"
        Write-Host "  Last Result:  $($info.LastTaskResult)"
        Write-Host "  Next Run:     $($info.NextRunTime)"
    } else {
        Write-Host "Task: $MorningTaskName is NOT registered." -ForegroundColor Red
    }

    if ($evening) {
        $info = Get-ScheduledTaskInfo -TaskName $EveningTaskName -ErrorAction SilentlyContinue
        Write-Host "Task: $EveningTaskName" -ForegroundColor Green
        Write-Host "  State:        $($evening.State)"
        Write-Host "  Last Run:     $($info.LastRunTime)"
        Write-Host "  Last Result:  $($info.LastTaskResult)"
        Write-Host "  Next Run:     $($info.NextRunTime)"
    } else {
        Write-Host "Task: $EveningTaskName is NOT registered." -ForegroundColor Red
    }

    return $true
}

function Invoke-Install {
    Write-Host "=== Installing TradeX PIT Scheduled Tasks ===" -ForegroundColor Cyan

    # Pre-flight validation
    Invoke-Validate | Out-Null

    $root = Resolve-RepoRoot
    $uv = Resolve-UvPath
    $manifest = Resolve-ManifestFile $root

    # Common task settings: catch-up disabled, 1h execution time limit, allow start on battery
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew

    # 1. Morning Task (09:00 ET)
    $morningAction = New-ScheduledTaskAction `
        -Execute $uv `
        -Argument "run python -m tradex.pit.ops run-slot --slot morning --universe-file `"$manifest`"" `
        -WorkingDirectory $root

    $morningTrigger = New-ScheduledTaskTrigger -Daily -At "09:00"

    Register-ScheduledTask `
        -TaskName $MorningTaskName `
        -Action $morningAction `
        -Trigger $morningTrigger `
        -Settings $settings `
        -Description "TradeX prospective point-in-time slot capture (Morning: 09:00 America/New_York)" `
        -Force | Out-Null

    Write-Host "[SUCCESS] Registered '$MorningTaskName' (Daily at 09:00 ET)" -ForegroundColor Green

    # 2. Evening Task (20:30 ET)
    $eveningAction = New-ScheduledTaskAction `
        -Execute $uv `
        -Argument "run python -m tradex.pit.ops run-slot --slot evening --universe-file `"$manifest`"" `
        -WorkingDirectory $root

    $eveningTrigger = New-ScheduledTaskTrigger -Daily -At "20:30"

    Register-ScheduledTask `
        -TaskName $EveningTaskName `
        -Action $eveningAction `
        -Trigger $eveningTrigger `
        -Settings $settings `
        -Description "TradeX prospective point-in-time slot capture (Evening: 20:30 America/New_York)" `
        -Force | Out-Null

    Write-Host "[SUCCESS] Registered '$EveningTaskName' (Daily at 20:30 ET)" -ForegroundColor Green
    Write-Host "Scheduled tasks installation complete." -ForegroundColor Green
}

function Invoke-Remove {
    Write-Host "=== Removing TradeX PIT Scheduled Tasks ===" -ForegroundColor Cyan

    $removedCount = 0

    $morning = Get-ScheduledTask -TaskName $MorningTaskName -ErrorAction SilentlyContinue
    if ($morning) {
        Unregister-ScheduledTask -TaskName $MorningTaskName -Confirm:$false
        Write-Host "[SUCCESS] Unregistered '$MorningTaskName'." -ForegroundColor Green
        $removedCount++
    } else {
        Write-Host "Task '$MorningTaskName' was not registered." -ForegroundColor Yellow
    }

    $evening = Get-ScheduledTask -TaskName $EveningTaskName -ErrorAction SilentlyContinue
    if ($evening) {
        Unregister-ScheduledTask -TaskName $EveningTaskName -Confirm:$false
        Write-Host "[SUCCESS] Unregistered '$EveningTaskName'." -ForegroundColor Green
        $removedCount++
    } else {
        Write-Host "Task '$EveningTaskName' was not registered." -ForegroundColor Yellow
    }

    Write-Host "Scheduler rollback complete. Removed $removedCount task(s)." -ForegroundColor Green
}

switch ($Action) {
    "Validate" { Invoke-Validate }
    "Status"   { Invoke-Status }
    "Install"  { Invoke-Install }
    "Remove"   { Invoke-Remove }
}
