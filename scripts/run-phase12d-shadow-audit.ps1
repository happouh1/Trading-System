param(
    [string]$AuditConfig = "config/burn-in.phase12d.audit.v1.json",
    [string]$LogNamespace = "phase12d",
    [string]$OfflineAsOf = "2026-10-07T23:10:00Z",
    [string]$AsOf,
    [switch]$OfflineVerify
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogRoot = Join-Path $ProjectRoot ".operator-home\$LogNamespace\logs"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$Log = Join-Path $LogRoot ("shadow-audit-" + (Get-Date -Format "yyyyMMdd") + ".log")
if ([string]::IsNullOrWhiteSpace($AsOf)) {
    $AsOf = [DateTimeOffset]::UtcNow.ToString("o")
}
if ($OfflineVerify) {
    $AsOf = $OfflineAsOf
}

Push-Location $ProjectRoot
try {
    $targetJson = & $Python -m trading_system.cli paper scheduled-shadow-audit-target `
        --audit-config $AuditConfig `
        --as-of $AsOf `
        --project-root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12D audit-target resolution failed"
    }
    $target = $targetJson | ConvertFrom-Json
    if (-not $target.eligible) {
        "$(Get-Date -Format o) NO_ACTION $($target.reason)" | Add-Content -LiteralPath $Log
        Write-Output $targetJson
        return
    }
    $arguments = @(
        "-m", "trading_system.cli", "paper", "scheduled-shadow-audit",
        "--audit-config", $AuditConfig,
        "--as-of", $AsOf,
        "--project-root", $ProjectRoot
    )
    if ($OfflineVerify) {
        $arguments += @(
            "--database-override",
            ".operator-home/$LogNamespace/offline-audit-verification.sqlite"
        )
    }
    & $Python @arguments 2>&1 | Tee-Object -FilePath $Log -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 12D immutable daily audit failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
