param(
    [string]$Schedule = "config/burn-in.phase12c.schedule.v1.json",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$WorkerConfig = "config/webull.phase12c.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12c.decisions.v1.json",
    [string]$ThresholdsConfig = "config/thresholds.phase1e.v1.yaml",
    [string]$LogNamespace = "phase12c",
    [string]$OfflineAsOf = "2026-10-07T20:05:00Z",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogRoot = Join-Path $ProjectRoot ".operator-home\$LogNamespace\logs"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$Log = Join-Path $LogRoot ("shadow-close-" + (Get-Date -Format "yyyyMMdd") + ".log")
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}
if ($OfflineVerify) {
    $AsOf = $OfflineAsOf
}

Push-Location $ProjectRoot
try {
    $targetJson = & $Python -m trading_system.cli paper scheduled-shadow-target `
        --schedule $Schedule `
        --action POST_CLOSE `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C post-close target resolution failed"
    }
    $target = $targetJson | ConvertFrom-Json
    if (-not $target.eligible) {
        "$(Get-Date -Format o) NO_ACTION $($target.reason)" | Add-Content -LiteralPath $Log
        Write-Output $targetJson
        return
    }
    if ($OfflineVerify) {
        & $Python -m trading_system.cli webull verify-burn-in-worker `
            --config $WebullConfig `
            --worker-config $WorkerConfig
        if ($LASTEXITCODE -ne 0) {
            throw "Phase 12C read-only worker configuration verification failed"
        }
        & $Python -m trading_system.cli webull verify-burn-in-decisions `
            --config $WebullConfig `
            --decision-config $DecisionConfig `
            --thresholds $ThresholdsConfig
        if ($LASTEXITCODE -ne 0) {
            throw "Phase 12C decision configuration verification failed"
        }
        Write-Output $targetJson
        return
    }
    & (Join-Path $PSScriptRoot "export-webull-env.ps1")
    & $Python -m trading_system.cli webull burn-in-worker-tick `
        --database webull-sandbox.sqlite `
        --session-id $target.session_id `
        --config $WebullConfig `
        --worker-config $WorkerConfig `
        --observed-at $AsOf `
        --allow-network-read 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C post-close market-data cycle failed"
    }
    & $Python -m trading_system.cli webull burn-in-decision-tick `
        --database webull-sandbox.sqlite `
        --session-id $target.session_id `
        --config $WebullConfig `
        --decision-config $DecisionConfig `
        --thresholds $ThresholdsConfig `
        --observed-at $AsOf 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C post-close decision cycle failed"
    }
    & $Python -m trading_system.cli paper scheduled-shadow-complete `
        --schedule $Schedule `
        --as-of $AsOf `
        --project-root $ProjectRoot 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C immutable completion receipt failed"
    }
}
finally {
    Pop-Location
}
