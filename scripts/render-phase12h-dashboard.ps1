param(
    [string]$Config = "config/burn-in.phase12h.dashboard.v1.json",
    [string]$AsOf,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotRoot = Join-Path $ProjectRoot ".operator-home\phase12h"
$SnapshotPath = Join-Path $SnapshotRoot "task-snapshot.json"
$OutputPath = Join-Path $SnapshotRoot "burn-in-operations.html"
$TaskNames = @(
    "Trading System - Phase 12H Shadow Preflight",
    "Trading System - Phase 12H Shadow Start",
    "Trading System - Phase 12H Shadow Close",
    "Trading System - Phase 12H Shadow Audit"
)
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $SnapshotRoot -Force | Out-Null
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}

$SnapshotWriter = Join-Path $PSScriptRoot "write-phase12h-task-snapshot.ps1"
try {
    & $SnapshotWriter -Output $SnapshotPath | Out-Null
}
catch {
    if (-not (Test-Path -LiteralPath $SnapshotPath -PathType Leaf)) {
        $Tasks = foreach ($Name in $TaskNames) {
            [ordered]@{
                name=$Name
                state="MISSING"
                next_run_at=$null
                last_run_at=$null
                last_result=$null
            }
        }
        $Snapshot = [ordered]@{
            captured_at=[DateTimeOffset]::UtcNow.ToString("o")
            tasks=@($Tasks)
        }
        $Temporary = "$SnapshotPath.tmp"
        $Json = $Snapshot | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText(
            $Temporary,
            $Json,
            (New-Object Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $Temporary -Destination $SnapshotPath -Force
    }
}

Push-Location $ProjectRoot
try {
    & $Python -m trading_system.cli paper scheduled-shadow-dashboard `
        --config $Config `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12H dashboard rendering failed with exit code $LASTEXITCODE"
    }
    if ($Open) { Start-Process -FilePath $OutputPath }
}
finally { Pop-Location }
