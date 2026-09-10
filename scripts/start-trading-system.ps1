param(
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$configPath = Join-Path $projectRoot "config\desktop.phase9k.v1.yaml"

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

$rendered = & $pythonPath -m trading_system.cli desktop render-upgrade-plan `
    --config $configPath `
    --project-root $projectRoot
$result = $LASTEXITCODE

if ($result -eq 0) {
    $artifact = $rendered | ConvertFrom-Json
    Write-Host "Trading System operator home is ready."
    if (-not $SelfTest) {
        Start-Process -FilePath $artifact.output_path
    }
} else {
    Write-Host "Trading System needs attention before it can open." -ForegroundColor Red
    Write-Host $rendered
    if (-not $SelfTest) { Read-Host "Press Enter to close" | Out-Null }
}
exit $result
