param(
    [string]$Schedule = "config/burn-in.phase12h.schedule.v1.json",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$WorkerConfig = "config/webull.phase12i.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12h.decisions.v1.json",
    [string]$ThresholdsConfig = "config/thresholds.phase1e.v1.yaml",
    [string]$ShortOpportunityConfig = "config/webull.phase12i.short-opportunities.v1.json",
    [string]$LifecycleConfig = "config/burn-in.phase12l.lifecycle.v1.json",
    [string]$LogNamespace = "phase12l",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Runner = Join-Path $PSScriptRoot "run-phase12i-shadow-close.ps1"
if ([string]::IsNullOrWhiteSpace($AsOf)) { $AsOf = [DateTimeOffset]::UtcNow.ToString("o") }
$baseArguments = @{
    Schedule = $Schedule; WebullConfig = $WebullConfig; WorkerConfig = $WorkerConfig
    DecisionConfig = $DecisionConfig; ThresholdsConfig = $ThresholdsConfig
    ShortOpportunityConfig = $ShortOpportunityConfig; LogNamespace = $LogNamespace
    AsOf = $AsOf
}
if ($OfflineVerify) {
    $baseArguments["OfflineVerify"] = $true
    & $Runner @baseArguments
    exit $LASTEXITCODE
}

Push-Location $ProjectRoot
try {
    $targetJson = & $Python -m trading_system.cli paper scheduled-shadow-target `
        --schedule $Schedule --action POST_CLOSE --as-of $AsOf --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Phase 12L target resolution failed" }
    $target = $targetJson | ConvertFrom-Json
    if (-not $target.eligible) { Write-Output $targetJson; return }
    $startedAt = [DateTimeOffset]::UtcNow.ToString("o")
    & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
        --config $LifecycleConfig --session-id $target.session_id `
        --operation POST_CLOSE --state STARTED --stage COLLECTION `
        --observed-at $startedAt --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Phase 12L start event failed" }
    try {
        & $Runner @baseArguments
        if ($LASTEXITCODE -ne 0) { throw "Phase 12L post-close runner failed" }
        $completedAt = [DateTimeOffset]::UtcNow.ToString("o")
        & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
            --config $LifecycleConfig --session-id $target.session_id `
            --operation POST_CLOSE --state COMPLETED --stage COLLECTION `
            --observed-at $completedAt --project-root $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw "Phase 12L completion event failed" }
    }
    catch {
        $failedAt = [DateTimeOffset]::UtcNow.ToString("o")
        $details = @{ message = $_.Exception.Message } | ConvertTo-Json -Compress
        & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
            --config $LifecycleConfig --session-id $target.session_id `
            --operation POST_CLOSE --state FAILED --stage COLLECTION `
            --observed-at $failedAt --details-json $details --project-root $ProjectRoot
        throw
    }
}
finally { Pop-Location }
