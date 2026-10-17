param(
    [string]$Schedule = "config/burn-in.phase12h.schedule.v1.json",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$WorkerConfig = "config/webull.phase12i.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12h.decisions.v1.json",
    [string]$ThresholdsConfig = "config/thresholds.phase1e.v1.yaml",
    [string]$ShortOpportunityConfig = "config/webull.phase12i.short-opportunities.v1.json",
    [string]$LogNamespace = "phase12i",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run-phase12c-shadow-close.ps1"
$arguments = @{
    Schedule = $Schedule
    WebullConfig = $WebullConfig
    WorkerConfig = $WorkerConfig
    DecisionConfig = $DecisionConfig
    ThresholdsConfig = $ThresholdsConfig
    ShortOpportunityConfig = $ShortOpportunityConfig
    LogNamespace = $LogNamespace
    OfflineAsOf = "2026-10-16T20:05:00Z"
}
if (-not [string]::IsNullOrWhiteSpace($AsOf)) {
    $arguments["AsOf"] = $AsOf
}
if ($OfflineVerify) {
    $arguments["OfflineVerify"] = $true
}
Push-Location $ProjectRoot
try {
    & $Runner @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
