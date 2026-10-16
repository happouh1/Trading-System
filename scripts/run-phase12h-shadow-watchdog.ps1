param(
    [string]$Config = "config/burn-in.phase12h.watchdog.v1.json",
    [string]$AsOf
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$StatusRoot = Join-Path $ProjectRoot ".operator-home\phase12h"
$LogRoot = Join-Path $StatusRoot "logs"
$AlertRoot = Join-Path $StatusRoot "alerts"
$TaskSnapshotWriter = Join-Path $PSScriptRoot "write-phase12h-task-snapshot.ps1"
foreach ($path in @($StatusRoot, $LogRoot, $AlertRoot)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}
try {
    & $TaskSnapshotWriter | Out-Null
}
catch {
    $SnapshotError = Join-Path $LogRoot "task-snapshot-errors.log"
    "$(Get-Date -Format o) $($_.Exception.Message)" |
        Add-Content -LiteralPath $SnapshotError -Encoding UTF8
}

Push-Location $ProjectRoot
try {
    $StatusJson = & $Python -m trading_system.cli paper scheduled-shadow-watchdog-status `
        --config $Config `
        --as-of $AsOf `
        --project-root $ProjectRoot
    $ExitCode = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace(($StatusJson -join ""))) {
        throw "Phase 12H watchdog returned no status payload"
    }
    $StatusText = $StatusJson -join [Environment]::NewLine
    $Status = $StatusText | ConvertFrom-Json
    $Utf8 = New-Object Text.UTF8Encoding($false)
    $Log = Join-Path $LogRoot ("shadow-watchdog-" + (Get-Date -Format "yyyyMMdd") + ".log")
    [IO.File]::AppendAllText($Log, $StatusText + [Environment]::NewLine, $Utf8)
    $Latest = Join-Path $StatusRoot "latest-watchdog-status.json"
    $Temporary = "$Latest.tmp"
    [IO.File]::WriteAllText($Temporary, $StatusText, $Utf8)
    Move-Item -LiteralPath $Temporary -Destination $Latest -Force
    if ($Status.alert_required) {
        $Alert = Join-Path $AlertRoot (
            "alert-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json"
        )
        [IO.File]::WriteAllText($Alert, $StatusText, $Utf8)
    }
    Write-Output $StatusText
    if ($ExitCode -ne 0) {
        exit $ExitCode
    }
}
finally {
    Pop-Location
}
