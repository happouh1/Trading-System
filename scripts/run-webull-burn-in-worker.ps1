param(
    [Parameter(Mandatory = $true)][string]$Database,
    [Parameter(Mandatory = $true)][string]$SessionId,
    [Parameter(Mandatory = $true)][string]$WorkerConfig,
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}

Push-Location $ProjectRoot
try {
    & $Python -m trading_system.cli webull burn-in-worker-tick `
        --database $Database `
        --session-id $SessionId `
        --config $WebullConfig `
        --worker-config $WorkerConfig `
        --allow-network-read
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 11G burn-in worker failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
