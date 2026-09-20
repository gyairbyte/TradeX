# launchers/windows/install_desktop_shortcuts.ps1
# Creates or updates the Start TradeX and Stop TradeX Windows desktop shortcuts.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File launchers\windows\install_desktop_shortcuts.ps1
#   powershell -ExecutionPolicy Bypass -File launchers\windows\install_desktop_shortcuts.ps1 -TargetDirectory "C:\custom\path"

[CmdletBinding()]
param (
    [Parameter()]
    [string]$ProjectRoot,

    [Parameter()]
    [string]$TargetDirectory
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRootPath {
    if ($ProjectRoot -and (Test-Path $ProjectRoot -PathType Container)) {
        return (Resolve-Path $ProjectRoot).Path
    }
    if ($env:TRADEX_HOME -and (Test-Path $env:TRADEX_HOME -PathType Container)) {
        return (Resolve-Path $env:TRADEX_HOME).Path
    }
    $ConfigPath = Join-Path $env:USERPROFILE ".tradex\config"
    if (Test-Path $ConfigPath) {
        $line = Get-Content $ConfigPath | Where-Object { $_ -match '^TRADEX_HOME=' } | Select-Object -First 1
        if ($line) {
            $p = ($line -replace '^TRADEX_HOME=', '').Trim().Trim('"').Trim("'")
            if ($p -and (Test-Path $p -PathType Container)) {
                return (Resolve-Path $p).Path
            }
        }
    }
    $ScriptDir = Split-Path -Parent $MyInvocation.PSCommandPath
    $Candidate = Resolve-Path (Join-Path $ScriptDir "..\..") -ErrorAction SilentlyContinue
    if ($Candidate -and (Test-Path (Join-Path $Candidate "pyproject.toml")) -and (Test-Path (Join-Path $Candidate "tradex"))) {
        return $Candidate.Path
    }
    throw "Could not resolve TradeX project root directory. Set -ProjectRoot or TRADEX_HOME."
}

$ResolvedRoot = Resolve-ProjectRootPath

# Target directory defaults to current user's Desktop
if (-not $TargetDirectory) {
    $TargetDirectory = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
}

if (-not (Test-Path $TargetDirectory)) {
    New-Item -ItemType Directory -Force -Path $TargetDirectory | Out-Null
}

$ResolvedTargetDir = (Resolve-Path $TargetDirectory).Path

$WinDir   = Join-Path $ResolvedRoot "launchers\windows"
$StartBat = Join-Path $WinDir "TradeX.bat"
$StartIco = Join-Path $WinDir "TradeX.ico"
$StopBat  = Join-Path $WinDir "TradeX-Stop.bat"
$StopIco  = Join-Path $WinDir "TradeX-Stop.ico"

# Validate required launcher assets exist
foreach ($file in @($StartBat, $StartIco, $StopBat, $StopIco)) {
    if (-not (Test-Path $file)) {
        throw "Required launcher asset not found: $file. Run 'python launchers/make_icon.py' if icons are missing."
    }
}

$WshShell = New-Object -ComObject WScript.Shell

# 1. Create/Update 'Start TradeX.lnk'
$StartLnkPath = Join-Path $ResolvedTargetDir "Start TradeX.lnk"
$StartShortcut = $WshShell.CreateShortcut($StartLnkPath)
$StartShortcut.TargetPath = (Resolve-Path $StartBat).Path
$StartShortcut.WorkingDirectory = $ResolvedRoot
$StartShortcut.IconLocation = "$((Resolve-Path $StartIco).Path),0"
$StartShortcut.Description = "Start TradeX Streamlit Dashboard"
$StartShortcut.Save()

# 2. Create/Update 'Stop TradeX.lnk'
$StopLnkPath = Join-Path $ResolvedTargetDir "Stop TradeX.lnk"
$StopShortcut = $WshShell.CreateShortcut($StopLnkPath)
$StopShortcut.TargetPath = (Resolve-Path $StopBat).Path
$StopShortcut.WorkingDirectory = $ResolvedRoot
$StopShortcut.IconLocation = "$((Resolve-Path $StopIco).Path),0"
$StopShortcut.Description = "Stop TradeX Streamlit Dashboard"
$StopShortcut.Save()

Write-Host "TradeX desktop shortcuts successfully installed in: $ResolvedTargetDir"
Write-Host "  Start: $StartLnkPath"
Write-Host "  Stop:  $StopLnkPath"
