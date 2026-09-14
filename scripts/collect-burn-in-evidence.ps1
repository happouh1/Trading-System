param(
    [Parameter(Mandatory = $true)]
    [string]$SessionId,
    [Parameter(Mandatory = $true)]
    [ValidateSet("BEARISH", "BULLISH", "RANGE")]
    [string]$Regime,
    [Parameter(Mandatory = $true)]
    [string]$Symbols,
    [Parameter(Mandatory = $true)]
    [string]$Timeframes,
    [Parameter(Mandatory = $true)]
    [string]$Strategies,
    [Parameter(Mandatory = $true)]
    [string]$MarketDay,
    [Parameter(Mandatory = $true)]
    [string]$ObservedAt
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python environment is missing: $python"
}

& $python -m trading_system.cli desktop burn-in-collect `
    --config (Join-Path $projectRoot "config\desktop.phase11c.v1.yaml") `
    --database (Join-Path $projectRoot "webull-sandbox.sqlite") `
    --session-id $SessionId `
    --market-day $MarketDay `
    --observed-at $ObservedAt `
    --regime $Regime `
    --symbols $Symbols `
    --timeframes $Timeframes `
    --strategies $Strategies `
    --project-root $projectRoot

exit $LASTEXITCODE
