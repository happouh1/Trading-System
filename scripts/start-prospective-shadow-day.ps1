param(
    [string]$Database = "webull-sandbox.sqlite",
    [string]$SessionId = "burn-in-shadow-20260928-01",
    [string]$StartedAt = "2026-09-28T13:30:00Z",
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LaunchConfig = "config/burn-in.phase12b.launch.v1.json"
$RuntimeLock = "config/desktop.phase12b.runtime-lock.v1.json"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
if ($OfflineVerify) {
    New-Item -ItemType Directory -Path (Join-Path $ProjectRoot ".operator-home\phase12b") -Force |
        Out-Null
    $Database = ".operator-home/phase12b/offline-launch-verification.sqlite"
    $SessionId = "burn-in-shadow-offline-verification"
}

Push-Location $ProjectRoot
try {
    & $Python -m trading_system.cli paper start-prospective-shadow `
        --database $Database `
        --session-id $SessionId `
        --config $LaunchConfig `
        --runtime-lock $RuntimeLock `
        --started-at $StartedAt `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Prospective shadow session start failed with exit code $LASTEXITCODE"
    }
    if ($OfflineVerify) {
        & $Python -m trading_system.cli webull verify-burn-in-worker `
            --config config/webull.sandbox.v1.yaml `
            --worker-config config/webull.phase12b.readonly.v1.json
        if ($LASTEXITCODE -ne 0) {
            throw "Read-only worker configuration verification failed"
        }
        & $Python -m trading_system.cli webull verify-burn-in-decisions `
            --config config/webull.sandbox.v1.yaml `
            --decision-config config/webull.phase12b.decisions.v1.json `
            --thresholds config/thresholds.phase1e.v1.yaml
        if ($LASTEXITCODE -ne 0) {
            throw "Decision-worker configuration verification failed"
        }
        exit 0
    }

    & (Join-Path $PSScriptRoot "export-webull-env.ps1")
    & $Python -m trading_system.cli webull verify-account `
        --database $Database `
        --session-id $SessionId `
        --config config/webull.sandbox.v1.yaml `
        --account-class INDIVIDUAL_MARGIN `
        --allow-network-read
    if ($LASTEXITCODE -ne 0) {
        throw "Same-session Webull read-only verification failed"
    }
}
finally {
    Pop-Location
}
