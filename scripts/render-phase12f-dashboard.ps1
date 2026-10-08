param(
    [string]$Config = "config/burn-in.phase12f.dashboard.v1.json",
    [string]$AsOf,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SnapshotRoot = Join-Path $ProjectRoot ".operator-home\phase12f"
$SnapshotPath = Join-Path $SnapshotRoot "task-snapshot.json"
$OutputPath = Join-Path $SnapshotRoot "burn-in-operations.html"
$TaskNames = @(
    "Trading System - Phase 12E Shadow Preflight",
    "Trading System - Phase 12E Shadow Start",
    "Trading System - Phase 12E Shadow Close",
    "Trading System - Phase 12E Shadow Audit"
)
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $SnapshotRoot -Force | Out-Null
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}

$Tasks = foreach ($Name in $TaskNames) {
    $Task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -eq $Task) {
        [ordered]@{
            name = $Name
            state = "MISSING"
            next_run_at = $null
            last_run_at = $null
            last_result = $null
        }
        continue
    }
    $Info = Get-ScheduledTaskInfo -TaskName $Name
    $Next = if ($Info.NextRunTime -eq [DateTime]::MinValue) {
        $null
    } else {
        $Info.NextRunTime.ToUniversalTime().ToString("o")
    }
    $Last = if ($Info.LastRunTime -eq [DateTime]::MinValue) {
        $null
    } else {
        $Info.LastRunTime.ToUniversalTime().ToString("o")
    }
    [ordered]@{
        name = $Name
        state = $Task.State.ToString().ToUpperInvariant()
        next_run_at = $Next
        last_run_at = $Last
        last_result = [int]$Info.LastTaskResult
    }
}
$Snapshot = [ordered]@{
    captured_at = [DateTimeOffset]::UtcNow.ToString("o")
    tasks = @($Tasks)
}
$Temporary = "$SnapshotPath.tmp"
$Json = $Snapshot | ConvertTo-Json -Depth 4
[IO.File]::WriteAllText($Temporary, $Json, (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $Temporary -Destination $SnapshotPath -Force

Push-Location $ProjectRoot
try {
    & $Python -m trading_system.cli paper scheduled-shadow-dashboard `
        --config $Config `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12F dashboard rendering failed with exit code $LASTEXITCODE"
    }
    if ($Open) {
        Start-Process -FilePath $OutputPath
    }
}
finally {
    Pop-Location
}
