param(
    [string]$AsOf = [DateTimeOffset]::UtcNow.ToString("o"),
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config\burn-in.phase12j.research-dashboard.v1.json"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Phase 12J requires the project Python environment: $Python"
}
$ResultJson = & $Python -m trading_system.cli paper scheduled-shadow-research-dashboard `
    --config $Config --as-of $AsOf --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Phase 12J dashboard rendering failed" }
$Result = $ResultJson | ConvertFrom-Json
if ($Open) { Start-Process -FilePath $Result.artifact.output_path }
$ResultJson
