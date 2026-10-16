param(
    [string]$Output = ".operator-home/phase12h/task-snapshot.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputPath = if ([IO.Path]::IsPathRooted($Output)) {
    $Output
} else {
    Join-Path $ProjectRoot $Output
}
$TaskNames = @(
    "Trading System - Phase 12H Shadow Preflight",
    "Trading System - Phase 12H Shadow Start",
    "Trading System - Phase 12H Shadow Close",
    "Trading System - Phase 12H Shadow Audit"
)
$Tasks = foreach ($Name in $TaskNames) {
    $Task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    $Info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction Stop
    $Next = if ($Info.NextRunTime -eq [DateTime]::MinValue) {
        $null
    } else {
        $Info.NextRunTime.ToUniversalTime().ToString("o")
    }
    $Last = if ($Info.LastRunTime.Year -le 2000) {
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
$Parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $Parent -Force | Out-Null
$Snapshot = [ordered]@{
    captured_at = [DateTimeOffset]::UtcNow.ToString("o")
    tasks = @($Tasks)
}
$Temporary = "$OutputPath.tmp"
$Json = $Snapshot | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($Temporary, $Json, (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $Temporary -Destination $OutputPath -Force
Write-Output $OutputPath
