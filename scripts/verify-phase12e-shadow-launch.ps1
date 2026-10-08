$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-start.ps1"
$CloseRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-close.ps1"
$AuditRunner = Join-Path $PSScriptRoot "run-phase12d-shadow-audit.ps1"
$PreflightRunner = Join-Path $PSScriptRoot "run-phase12e-shadow-preflight.ps1"
$shared = @{
    Schedule = "config/burn-in.phase12e.schedule.v1.json"
    WebullConfig = "config/webull.sandbox.v1.yaml"
    WorkerConfig = "config/webull.phase12e.readonly.v1.json"
    DecisionConfig = "config/webull.phase12e.decisions.v1.json"
    ThresholdsConfig = "config/thresholds.phase1e.v1.yaml"
    LogNamespace = "phase12e"
    OfflineVerify = $true
}

Push-Location $ProjectRoot
try {
    & $PreflightRunner -OfflineVerify
    & $StartRunner @shared -OfflineAsOf "2026-10-08T13:30:00Z"
    & $CloseRunner @shared -OfflineAsOf "2026-10-08T20:05:00Z"
    & $AuditRunner `
        -AuditConfig "config/burn-in.phase12e.audit.v1.json" `
        -LogNamespace "phase12e" `
        -OfflineAsOf "2026-10-08T23:10:00Z" `
        -OfflineVerify
    Write-Output "Phase 12E offline launch verification passed without broker writes."
}
finally {
    Pop-Location
}
