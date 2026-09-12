param(
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$configPath = Join-Path $projectRoot "config\desktop.phase11a.v1.yaml"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Write-Host "Trading Workstation needs its Python environment." -ForegroundColor Red
    Write-Host "Expected: $pythonPath"
    if (-not $SelfTest) { Read-Host "Press Enter to close" | Out-Null }
    exit 1
}

$asOf = [DateTime]::UtcNow.ToString("o")
$rendered = & $pythonPath -m trading_system.desktop.workstation `
    --config $configPath `
    --project-root $projectRoot `
    --as-of $asOf
$result = $LASTEXITCODE

if ($result -eq 0) {
    $artifact = $rendered | ConvertFrom-Json
    Write-Host "Trading Workstation is ready in read-only sandbox mode."
    if (-not $SelfTest) {
        Start-Process -FilePath $artifact.output_path
    }
} else {
    Write-Host "Trading Workstation needs attention before it can open." -ForegroundColor Red
    Write-Host $rendered
    if (-not $SelfTest) { Read-Host "Press Enter to close" | Out-Null }
}
exit $result
