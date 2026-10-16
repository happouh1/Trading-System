param([switch]$SelfTest)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config\burn-in.phase12h.launcher.v1.json"
$Renderer = Join-Path $ProjectRoot "scripts\render-phase12h-dashboard.ps1"
$StatusJson = & $Python -m trading_system.cli paper scheduled-shadow-launcher-status `
    --config $Config --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Phase 12H launcher validation failed" }
$Status = $StatusJson | ConvertFrom-Json
if (-not $Status.launcher_ready) {
    throw "Phase 12H launcher prerequisites are incomplete: $($Status.missing_paths -join ', ')"
}
$RenderedJson = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Renderer `
    -AsOf ([DateTimeOffset]::UtcNow.ToString("o"))
if ($LASTEXITCODE -ne 0) { throw "Phase 12H dashboard rendering failed" }
$Rendered = $RenderedJson | ConvertFrom-Json
$OutputPath = $Rendered.artifact.output_path
if ($SelfTest) {
    [ordered]@{
        launcher_ready=$true
        dashboard_rendered=$true
        output_path=$OutputPath
        overall_status=$Rendered.artifact.overall_status
        network_used=$false
        credentials_loaded=$false
        broker_write_performed=$false
        scheduler_modified=$false
    } | ConvertTo-Json -Compress
} else {
    Start-Process -FilePath $OutputPath
}
