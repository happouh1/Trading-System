param(
    [Parameter(Mandatory = $true)][ValidateSet("BULLISH", "BEARISH", "RANGE")][string]$Regime,
    [string]$Database = "webull-sandbox.sqlite",
    [string]$SessionId = "burn-in-shadow-20260928-01",
    [string]$MarketDay = "2026-09-28",
    [string]$ObservedAt = "2026-09-28T20:05:00Z"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}

Push-Location $ProjectRoot
try {
    & (Join-Path $PSScriptRoot "export-webull-env.ps1")
    & $Python -m trading_system.cli webull burn-in-worker-tick `
        --database $Database `
        --session-id $SessionId `
        --config config/webull.sandbox.v1.yaml `
        --worker-config config/webull.phase12b.readonly.v1.json `
        --allow-network-read
    if ($LASTEXITCODE -ne 0) {
        throw "Post-close market-data cycle failed"
    }
    & $Python -m trading_system.cli webull burn-in-decision-tick `
        --database $Database `
        --session-id $SessionId `
        --config config/webull.sandbox.v1.yaml `
        --decision-config config/webull.phase12b.decisions.v1.json `
        --thresholds config/thresholds.phase1e.v1.yaml
    if ($LASTEXITCODE -ne 0) {
        throw "Post-close decision cycle failed"
    }
    & $Python -m trading_system.cli desktop burn-in-collect `
        --config config/desktop.phase12b.collector.v1.json `
        --database $Database `
        --session-id $SessionId `
        --market-day $MarketDay `
        --observed-at $ObservedAt `
        --regime $Regime `
        --symbols MSFT,SPY `
        --timeframes 1H,4H,DAILY,WEEKLY `
        --strategies BREAKOUT,RECLAIM `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Post-close immutable evidence collection failed"
    }
}
finally {
    Pop-Location
}
