param(
    [string]$Schedule = "config/burn-in.phase12c.schedule.v1.json",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$WorkerConfig = "config/webull.phase12c.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12c.decisions.v1.json",
    [string]$ThresholdsConfig = "config/thresholds.phase1e.v1.yaml",
    [string]$LogNamespace = "phase12c",
    [string]$OfflineAsOf = "2026-10-07T13:30:00Z",
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
$Log = Join-Path $LogRoot ("shadow-start-" + (Get-Date -Format "yyyyMMdd") + ".log")
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
        --action START `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C start-target resolution failed"
    }
    $target = $targetJson | ConvertFrom-Json
    if (-not $target.eligible) {
        "$(Get-Date -Format o) NO_ACTION $($target.reason)" | Add-Content -LiteralPath $Log
        Write-Output $targetJson
        return
    }
    $arguments = @(
        "-m", "trading_system.cli", "paper", "scheduled-shadow-start",
        "--schedule", $Schedule,
        "--as-of", $AsOf,
        "--project-root", $ProjectRoot
    )
    if ($OfflineVerify) {
        $arguments += @(
            "--database-override",
            ".operator-home/$LogNamespace/offline-start-verification.sqlite"
        )
    }
    & $Python @arguments 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C scheduled SHADOW start failed with exit code $LASTEXITCODE"
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
        return
    }
    & (Join-Path $PSScriptRoot "export-webull-env.ps1")
    & $Python -m trading_system.cli webull verify-account `
        --database webull-sandbox.sqlite `
        --session-id $target.session_id `
        --config $WebullConfig `
        --account-class INDIVIDUAL_MARGIN `
        --allow-network-read 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12C same-session Webull read-only verification failed"
    }
}
finally {
    Pop-Location
}
