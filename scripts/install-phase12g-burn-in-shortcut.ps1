param(
    [string]$ShortcutPath = (
        Join-Path ([Environment]::GetFolderPath("Desktop")) "Trading System.lnk"
    )
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config\burn-in.phase12g.launcher.v1.json"
$Launcher = Join-Path $ProjectRoot "scripts\start-phase12g-burn-in.ps1"
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$StatusJson = & $Python -m trading_system.cli paper scheduled-shadow-launcher-status `
    --config $Config `
    --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Phase 12G launcher validation failed with exit code $LASTEXITCODE"
}
$Status = $StatusJson | ConvertFrom-Json
if (-not $Status.launcher_ready) {
    throw "Phase 12G launcher prerequisites are incomplete: $($Status.missing_paths -join ', ')"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShell
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Refresh and open the read-only Trading System burn-in dashboard"
$Shortcut.IconLocation = "$PowerShell,0"
$Shortcut.Save()

Write-Output "Updated Trading System shortcut: $ShortcutPath"
