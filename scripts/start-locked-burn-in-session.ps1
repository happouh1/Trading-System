param(
    [Parameter(Mandatory = $true)][string]$SessionId,
    [Parameter(Mandatory = $true)][string]$StartedAt,
    [string]$Database = "webull-sandbox.sqlite",
    [string]$Config = "config/paper.phase11f.v1.yaml"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project Python was not found at $Python"
}
& $Python -m trading_system.cli paper start-burn-in `
    --database $Database `
    --session-id $SessionId `
    --config $Config `
    --started-at $StartedAt `
    --project-root $ProjectRoot
