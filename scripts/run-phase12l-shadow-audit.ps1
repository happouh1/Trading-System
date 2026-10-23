param(
    [string]$AuditConfig = "config/burn-in.phase12h.audit.v1.json",
    [string]$LifecycleConfig = "config/burn-in.phase12l.lifecycle.v1.json",
    [string]$LogNamespace = "phase12l",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Runner = Join-Path $PSScriptRoot "run-phase12d-shadow-audit.ps1"
if ([string]::IsNullOrWhiteSpace($AsOf)) { $AsOf = [DateTimeOffset]::UtcNow.ToString("o") }
if ($OfflineVerify) {
    & $Runner -AuditConfig $AuditConfig -LogNamespace $LogNamespace `
        -OfflineAsOf $AsOf -OfflineVerify
    exit $LASTEXITCODE
}

Push-Location $ProjectRoot
try {
    $targetJson = & $Python -m trading_system.cli paper scheduled-shadow-audit-target `
        --audit-config $AuditConfig --as-of $AsOf --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Phase 12L audit target resolution failed" }
    $target = $targetJson | ConvertFrom-Json
    if (-not $target.eligible) { Write-Output $targetJson; return }
    & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
        --config $LifecycleConfig --session-id $target.session_id `
        --operation AUDIT --state STARTED --stage DAILY_AUDIT `
        --observed-at ([DateTimeOffset]::UtcNow.ToString("o")) --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Phase 12L audit start event failed" }
    try {
        & $Runner -AuditConfig $AuditConfig -LogNamespace $LogNamespace -AsOf $AsOf
        if ($LASTEXITCODE -ne 0) { throw "Phase 12L audit runner failed" }
        & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
            --config $LifecycleConfig --session-id $target.session_id `
            --operation AUDIT --state COMPLETED --stage DAILY_AUDIT `
            --observed-at ([DateTimeOffset]::UtcNow.ToString("o")) --project-root $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw "Phase 12L audit completion event failed" }
    }
    catch {
        $details = @{ message = $_.Exception.Message } | ConvertTo-Json -Compress
        & $Python -m trading_system.cli paper scheduled-shadow-operation-event `
            --config $LifecycleConfig --session-id $target.session_id `
            --operation AUDIT --state FAILED --stage DAILY_AUDIT `
            --observed-at ([DateTimeOffset]::UtcNow.ToString("o")) `
            --details-json $details --project-root $ProjectRoot
        throw
    }
}
finally { Pop-Location }
