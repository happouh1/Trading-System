param(
    [string]$Schedule = "config/burn-in.phase12c.schedule.v1.json",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$WorkerConfig = "config/webull.phase12c.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12c.decisions.v1.json",
    [string]$ThresholdsConfig = "config/thresholds.phase1e.v1.yaml",
    [string]$ShortOpportunityConfig,
    [string]$LogNamespace = "phase12c",
    [string]$OfflineAsOf = "2026-10-07T20:05:00Z",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogRoot = Join-Path $ProjectRoot ".operator-home\$LogNamespace\logs"
$AlertRoot = Join-Path $ProjectRoot ".operator-home\$LogNamespace\alerts"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
New-Item -ItemType Directory -Path $AlertRoot -Force | Out-Null
$Log = Join-Path $LogRoot ("shadow-close-" + (Get-Date -Format "yyyyMMdd") + ".log")
$Stage = "TARGET_RESOLUTION"
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
        if (-not [string]::IsNullOrWhiteSpace($ShortOpportunityConfig)) {
            & $Python -c (
                "from trading_system.webull.short_opportunities import " +
                "load_short_opportunity_config; " +
                "load_short_opportunity_config(r'" + $ShortOpportunityConfig + "')"
            )
            if ($LASTEXITCODE -ne 0) {
                throw "Phase 12I short-opportunity configuration verification failed"
            }
        }
        Write-Output $targetJson
        return
    }
    $Stage = "MARKET_DATA"
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
    $Stage = "DECISION_CYCLE"
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
    if (-not [string]::IsNullOrWhiteSpace($ShortOpportunityConfig)) {
        $Stage = "SHORT_OPPORTUNITY"
        & $Python -m trading_system.cli webull short-opportunity-tick `
            --database webull-sandbox.sqlite `
            --session-id $target.session_id `
            --config $WebullConfig `
            --short-config $ShortOpportunityConfig `
            --observed-at $AsOf 2>&1 | Tee-Object -FilePath $Log -Append
        if ($LASTEXITCODE -ne 0) {
            throw "Phase 12I short-opportunity cycle failed"
        }
        & $Python -m trading_system.cli webull short-opportunity-outcomes `
            --database webull-sandbox.sqlite `
            --config $WebullConfig `
            --short-config $ShortOpportunityConfig `
            --as-of $AsOf 2>&1 | Tee-Object -FilePath $Log -Append
        if ($LASTEXITCODE -ne 0) {
            throw "Phase 12I short-opportunity outcome cycle failed"
        }
    }
    $Stage = "COMPLETION_RECEIPT"
    & $Python -m trading_system.cli paper scheduled-shadow-complete `
        --schedule $Schedule `
        --as-of $AsOf `
        --project-root $ProjectRoot 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C immutable completion receipt failed"
    }
}
catch {
    $message = $_.Exception.Message
    "$(Get-Date -Format o) ERROR $Stage $message" | Add-Content -LiteralPath $Log
    $code = if ($Stage -eq "DECISION_CYCLE") {
        "DECISION_CYCLE_MISSING"
    } else {
        "POST_CLOSE_STAGE_FAILED"
    }
    $alert = [ordered]@{
        alert_code = $code
        stage = $Stage
        session_id = if ($null -eq $target) { $null } else { $target.session_id }
        observed_at = $AsOf
        message = $message
        broker_write_performed = $false
        live_trading_enabled = $false
        automatic_promotion_enabled = $false
    }
    $alertPath = Join-Path $AlertRoot (
        "alert-" + (Get-Date -Format "yyyyMMdd-HHmmssfff") + ".json"
    )
    $alert | ConvertTo-Json -Depth 6 -Compress | Set-Content -LiteralPath $alertPath
    throw
}
finally {
    Pop-Location
}
