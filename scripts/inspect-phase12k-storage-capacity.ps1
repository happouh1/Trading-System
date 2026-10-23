param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$AsOf = ([DateTimeOffset]::UtcNow.ToString("o"))
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Phase 12K Python environment is missing: $python"
}

& $python -m trading_system.cli paper scheduled-shadow-storage-capacity `
    --config (Join-Path $ProjectRoot "config\burn-in.phase12k.storage-capacity.v1.json") `
    --as-of $AsOf `
    --project-root $ProjectRoot
exit $LASTEXITCODE
