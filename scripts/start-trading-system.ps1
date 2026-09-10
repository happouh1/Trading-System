param(
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$configPath = Join-Path $projectRoot "config\desktop.phase9g.v1.yaml"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Write-Host "Trading System needs its Python environment." -ForegroundColor Red
    Write-Host "Expected: $pythonPath"
    if (-not $SelfTest) { Read-Host "Press Enter to close" | Out-Null }
    exit 1
}

if (-not $SelfTest) {
    $Host.UI.RawUI.WindowTitle = "Trading System"
    Clear-Host
}

& $pythonPath -m trading_system.cli desktop home `
    --config $configPath `
    --project-root $projectRoot
$result = $LASTEXITCODE

if (-not $SelfTest) {
    Write-Host ""
    Read-Host "Press Enter to close" | Out-Null
}
exit $result
