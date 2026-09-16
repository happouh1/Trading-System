param(
    [Parameter(Mandatory = $true)][string]$Database,
    [Parameter(Mandatory = $true)][string]$SessionId,
    [string]$DecisionConfig = "config/webull.phase11h.offline.v1.yaml",
    [string]$Thresholds = "config/thresholds.phase1e.v1.yaml",
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
    & $Python -m trading_system.cli webull burn-in-decision-tick `
        --database $Database `
        --session-id $SessionId `
        --config $WebullConfig `
        --decision-config $DecisionConfig `
        --thresholds $Thresholds
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 11H burn-in decision cycle failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
