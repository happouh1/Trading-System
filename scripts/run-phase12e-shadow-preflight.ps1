param(
    [string]$Schedule = "config/burn-in.phase12e.schedule.v1.json",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Database = Join-Path $ProjectRoot "webull-sandbox.sqlite"
$LogRoot = Join-Path $ProjectRoot ".operator-home\phase12e\logs"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
if (-not $OfflineVerify -and -not (Test-Path -LiteralPath $Database -PathType Leaf)) {
    throw "Phase 12E evidence database was not found: $Database"
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$Log = Join-Path $LogRoot ("shadow-preflight-" + (Get-Date -Format "yyyyMMdd") + ".log")
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}
if ($OfflineVerify) {
    $AsOf = "2026-10-08T13:25:00Z"
}

Push-Location $ProjectRoot
try {
    $result = & $Python -m trading_system.cli paper scheduled-shadow-preflight `
        --schedule $Schedule `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12E frozen-input preflight failed"
    }
    $payload = $result | ConvertFrom-Json
    if (-not $payload.eligible) {
        "$(Get-Date -Format o) NO_ACTION $($payload.reason)" | Add-Content -LiteralPath $Log
    }
    else {
        "$(Get-Date -Format o) READY $($payload.session_id)" | Add-Content -LiteralPath $Log
    }
    Write-Output $result
}
finally {
    Pop-Location
}
