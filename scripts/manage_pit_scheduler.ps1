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
#   - Dedicated TaskPath: \TradeX\ to isolate TradeX tasks from root tasks.
#   - Dedicated TaskFolder: Created via Schedule.Service during Install if not present; preserved on Remove/rollback.
#   - Ownership marker: "Managed by scripts/manage_pit_scheduler.ps1" embedded in description.
#   - Safe Install: No overwrite flags. Verifies pre-existing tasks and fails closed.
#   - Atomic Install: Rolls back morning task if evening task fails during installation.
#   - Safe Remove: Verifies TaskPath and ownership marker before unregistering; refuses on conflict.
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

$TaskPath = "\TradeX\"
$MorningTaskName = "TradeX PIT Morning"
$EveningTaskName = "TradeX PIT Evening"
$ExpectedTimezone = "Eastern Standard Time"
$OwnershipMarker = "Managed by scripts/manage_pit_scheduler.ps1"
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

function Get-OwnedTask ($Name) {
    try {
        return (Get-ScheduledTask -TaskPath $TaskPath -TaskName $Name -ErrorAction Stop)
    } catch {
        return $null
    }
}

function Test-IsOwnedTask ($Task) {
    if (-not $Task) {
        return $false
    }
    $normalizedTaskPath = "\" + ($Task.TaskPath.Trim('\')) + "\"
    if ($normalizedTaskPath -ne $TaskPath) {
        return $false
    }
    if (-not $Task.Description -or -not ($Task.Description -like "*$OwnershipMarker*")) {
        return $false
    }
    return $true
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
    Write-Host "  Path:   $TaskPath"
    Write-Host "  Marker: $OwnershipMarker"
    Write-Host "  Task 1: $MorningTaskName"
    Write-Host "    Path:    $TaskPath"
    Write-Host "    Trigger: Daily at 09:00 ($ExpectedTimezone)"
    Write-Host "    Action:  $uv run python -m tradex.pit.ops run-slot --slot morning --universe-file $manifest"
    Write-Host "    Working Dir: $root"
    Write-Host "    Catch-up policy: Disabled (StartWhenAvailable = false)"
    Write-Host "  Task 2: $EveningTaskName"
    Write-Host "    Path:    $TaskPath"
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
    Write-Host "Owned Task Path: $TaskPath" -ForegroundColor Cyan

    $morning = Get-OwnedTask $MorningTaskName
    $evening = Get-OwnedTask $EveningTaskName

    if (-not $morning -and -not $evening) {
        Write-Host "Neither '$MorningTaskName' nor '$EveningTaskName' is currently registered under '$TaskPath'." -ForegroundColor Yellow
        Write-Host "Scheduler is INACTIVE (no OS tasks installed)." -ForegroundColor Yellow
        return $false
    }

    if ($morning) {
        $owned = Test-IsOwnedTask $morning
        $info = try { Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $MorningTaskName -ErrorAction Stop } catch { $null }
        Write-Host "Task: $MorningTaskName (Path: $TaskPath)" -ForegroundColor Green
        Write-Host "  State:        $($morning.State)"
        Write-Host "  Owned:        $owned"
        if ($info) {
            Write-Host "  Last Run:     $($info.LastRunTime)"
            Write-Host "  Last Result:  $($info.LastTaskResult)"
            Write-Host "  Next Run:     $($info.NextRunTime)"
        }
    } else {
        Write-Host "Task: $MorningTaskName is NOT registered under '$TaskPath'." -ForegroundColor Red
    }

    if ($evening) {
        $owned = Test-IsOwnedTask $evening
        $info = try { Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $EveningTaskName -ErrorAction Stop } catch { $null }
        Write-Host "Task: $EveningTaskName (Path: $TaskPath)" -ForegroundColor Green
        Write-Host "  State:        $($evening.State)"
        Write-Host "  Owned:        $owned"
        if ($info) {
            Write-Host "  Last Run:     $($info.LastRunTime)"
            Write-Host "  Last Result:  $($info.LastTaskResult)"
            Write-Host "  Next Run:     $($info.NextRunTime)"
        }
    } else {
        Write-Host "Task: $EveningTaskName is NOT registered under '$TaskPath'." -ForegroundColor Red
    }

    return $true
}

function Ensure-TradeXTaskFolder {
    try {
        $service = New-Object -ComObject "Schedule.Service"
        $service.Connect()
        $rootFolder = $service.GetFolder("\")

        $subfolders = $rootFolder.GetFolders(0)
        $folderExists = ($subfolders | Where-Object { $_.Name -ieq "TradeX" }) -ne $null

        if (-not $folderExists) {
            Write-Host "Creating Task Scheduler folder '\TradeX\'..." -ForegroundColor Yellow
            $created = $rootFolder.CreateFolder("TradeX")
            if (-not $created) {
                throw "Task Scheduler CreateFolder returned null or failed to create 'TradeX' folder."
            }
            Write-Host "[SUCCESS] Created Task Scheduler folder '\TradeX\'." -ForegroundColor Green
        } else {
            Write-Host "Task Scheduler folder '\TradeX\' already exists." -ForegroundColor Green
        }
    } catch {
        throw "Failed to ensure Task Scheduler folder '\TradeX\': $($_.Exception.Message)"
    }
}

function Invoke-Install {
    Write-Host "=== Installing TradeX PIT Scheduled Tasks ===" -ForegroundColor Cyan
    Write-Host "Owned Task Path: $TaskPath" -ForegroundColor Cyan

    # Pre-flight validation
    Invoke-Validate | Out-Null

    $root = Resolve-RepoRoot
    $uv = Resolve-UvPath
    $manifest = Resolve-ManifestFile $root

    # Ensure dedicated Task Scheduler folder exists before task registration
    Ensure-TradeXTaskFolder

    # Check for pre-existing tasks under $TaskPath (fail closed if exists or unowned)
    $existingMorning = Get-OwnedTask $MorningTaskName
    if ($existingMorning) {
        if (-not (Test-IsOwnedTask $existingMorning)) {
            throw "Conflict: Task '$MorningTaskName' already exists under '$TaskPath' but is NOT owned by this script (missing ownership marker '$OwnershipMarker'). Refusing to overwrite."
        }
        throw "Task '$MorningTaskName' is already installed under '$TaskPath'. Remove existing task first before re-installing."
    }

    $existingEvening = Get-OwnedTask $EveningTaskName
    if ($existingEvening) {
        if (-not (Test-IsOwnedTask $existingEvening)) {
            throw "Conflict: Task '$EveningTaskName' already exists under '$TaskPath' but is NOT owned by this script (missing ownership marker '$OwnershipMarker'). Refusing to overwrite."
        }
        throw "Task '$EveningTaskName' is already installed under '$TaskPath'. Remove existing task first before re-installing."
    }

    # Common task settings: catch-up disabled, 1h execution time limit, allow start on battery
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew

    $createdMorning = $false
    $createdEvening = $false

    try {
        # 1. Morning Task (09:00 ET)
        $morningAction = New-ScheduledTaskAction `
            -Execute $uv `
            -Argument "run python -m tradex.pit.ops run-slot --slot morning --universe-file `"$manifest`"" `
            -WorkingDirectory $root

        $morningTrigger = New-ScheduledTaskTrigger -Daily -At "09:00"

        Register-ScheduledTask `
            -TaskPath $TaskPath `
            -TaskName $MorningTaskName `
            -Action $morningAction `
            -Trigger $morningTrigger `
            -Settings $settings `
            -Description "TradeX prospective point-in-time slot capture (Morning: 09:00 America/New_York). $OwnershipMarker." | Out-Null

        $createdMorning = $true
        Write-Host "[SUCCESS] Registered '$MorningTaskName' under '$TaskPath' (Daily at 09:00 ET)" -ForegroundColor Green

        # 2. Evening Task (20:30 ET)
        $eveningAction = New-ScheduledTaskAction `
            -Execute $uv `
            -Argument "run python -m tradex.pit.ops run-slot --slot evening --universe-file `"$manifest`"" `
            -WorkingDirectory $root

        $eveningTrigger = New-ScheduledTaskTrigger -Daily -At "20:30"

        Register-ScheduledTask `
            -TaskPath $TaskPath `
            -TaskName $EveningTaskName `
            -Action $eveningAction `
            -Trigger $eveningTrigger `
            -Settings $settings `
            -Description "TradeX prospective point-in-time slot capture (Evening: 20:30 America/New_York). $OwnershipMarker." | Out-Null

        $createdEvening = $true
        Write-Host "[SUCCESS] Registered '$EveningTaskName' under '$TaskPath' (Daily at 20:30 ET)" -ForegroundColor Green
        Write-Host "Scheduled tasks installation complete." -ForegroundColor Green
    }
    catch {
        Write-Warning "Installation failed: $($_.Exception.Message). Rolling back partially created task(s)..."
        if ($createdMorning) {
            try {
                $task = Get-OwnedTask $MorningTaskName
                if ($task -and (Test-IsOwnedTask $task)) {
                    Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $MorningTaskName -Confirm:$false
                    Write-Host "[ROLLBACK] Successfully rolled back '$MorningTaskName'." -ForegroundColor Yellow
                }
            } catch {
                Write-Error "Failed to roll back '$MorningTaskName': $($_.Exception.Message)"
            }
        }
        if ($createdEvening) {
            try {
                $task = Get-OwnedTask $EveningTaskName
                if ($task -and (Test-IsOwnedTask $task)) {
                    Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $EveningTaskName -Confirm:$false
                    Write-Host "[ROLLBACK] Successfully rolled back '$EveningTaskName'." -ForegroundColor Yellow
                }
            } catch {
                Write-Error "Failed to roll back '$EveningTaskName': $($_.Exception.Message)"
            }
        }
        throw
    }
}

function Invoke-Remove {
    Write-Host "=== Removing TradeX PIT Scheduled Tasks ===" -ForegroundColor Cyan
    Write-Host "Owned Task Path: $TaskPath" -ForegroundColor Cyan

    $tasksToRemove = @($MorningTaskName, $EveningTaskName)
    $removedCount = 0

    foreach ($taskName in $tasksToRemove) {
        $task = Get-OwnedTask $taskName
        if ($task) {
            if (-not (Test-IsOwnedTask $task)) {
                throw "Refusing to remove '$taskName' under '$TaskPath': task does not contain required ownership marker '$OwnershipMarker'. Conflict detected."
            }
            Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $taskName -Confirm:$false
            Write-Host "[SUCCESS] Unregistered '$taskName' from '$TaskPath'." -ForegroundColor Green
            $removedCount++
        } else {
            Write-Host "Task '$taskName' was not registered under '$TaskPath'." -ForegroundColor Yellow
        }
    }

    Write-Host "Scheduler rollback complete. Removed $removedCount task(s)." -ForegroundColor Green
}

switch ($Action) {
    "Validate" { Invoke-Validate }
    "Status"   { Invoke-Status }
    "Install"  { Invoke-Install }
    "Remove"   { Invoke-Remove }
}
