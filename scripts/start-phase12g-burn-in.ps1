param(
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config\burn-in.phase12g.launcher.v1.json"
$Renderer = Join-Path $ProjectRoot "scripts\render-phase12f-dashboard.ps1"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}

$StatusJson = & $Python -m trading_system.cli paper scheduled-shadow-launcher-status `
    --config $Config `
    --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Phase 12G launcher validation failed with exit code $LASTEXITCODE"
}
$Status = $StatusJson | ConvertFrom-Json
if (-not $Status.launcher_ready) {
    throw "Phase 12G launcher prerequisites are incomplete: $($Status.missing_paths -join ', ')"
}

$AsOf = [DateTimeOffset]::UtcNow.ToString("o")
$RenderedJson = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Renderer -AsOf $AsOf
if ($LASTEXITCODE -ne 0) {
    throw "Phase 12F dashboard rendering failed with exit code $LASTEXITCODE"
}
$Rendered = $RenderedJson | ConvertFrom-Json
$OutputPath = $Rendered.artifact.output_path
if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Rendered Phase 12F dashboard was not found: $OutputPath"
}

if ($SelfTest) {
    [ordered]@{
        launcher_ready = $true
        dashboard_rendered = $true
        output_path = $OutputPath
        overall_status = $Rendered.artifact.overall_status
        network_used = $false
        credentials_loaded = $false
        broker_write_performed = $false
        scheduler_modified = $false
    } | ConvertTo-Json -Compress
} else {
    Start-Process -FilePath $OutputPath
}
