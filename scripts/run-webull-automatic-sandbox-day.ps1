param(
    [string]$Database = "webull-sandbox.sqlite",
    [string]$SessionId = "burn-in-webull-20260928-01",
    [string]$WebullConfig = "config/webull.sandbox.v1.yaml",
    [string]$AutomaticConfig = "config/webull.phase12a.automatic-sandbox.v1.json",
    [string]$ExitConfig = "config/webull.exits.phase3d.v1.yaml",
    [string]$ExitCapabilities = "config/webull.exit_capabilities.pending.v1.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$EnvScript = Join-Path $PSScriptRoot "export-webull-env.ps1"
$LogRoot = Join-Path $ProjectRoot ".operator-home\phase12a\logs"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project virtual-environment Python was not found: $Python"
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$Log = Join-Path $LogRoot ("automatic-sandbox-" + (Get-Date -Format "yyyyMMdd") + ".log")
$CapabilityPath = Join-Path $ProjectRoot $ExitCapabilities
$Capabilities = Get-Content -LiteralPath $CapabilityPath -Raw | ConvertFrom-Json
if (-not $Capabilities.approved -or -not $Capabilities.official_exit_transport_enabled) {
    "$(Get-Date -Format o) ARMED_BLOCKED EXIT_CAPABILITIES_UNAPPROVED" |
    Add-Content -LiteralPath $Log
    exit 0
}
if (Test-Path -LiteralPath $EnvScript -PathType Leaf) {
    & $EnvScript
}
$env:WEBULL_SANDBOX_SUBMISSION_ENABLED = "true"
$env:WEBULL_SANDBOX_EXIT_ENABLED = "true"

Push-Location $ProjectRoot
try {
    $localNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
        [DateTimeOffset]::UtcNow,
        "Eastern Standard Time"
    )
    if ($localNow.DayOfWeek -in @("Saturday", "Sunday")) {
        "$(Get-Date -Format o) NO_ACTION WEEKEND" | Add-Content -LiteralPath $Log
        exit 0
    }
    $open = $localNow.Date.AddHours(9).AddMinutes(30)
    $close = $localNow.Date.AddHours(20)
    while ($localNow -lt $open) {
        Start-Sleep -Seconds ([Math]::Min(30, [Math]::Max(1, ($open - $localNow).TotalSeconds)))
        $localNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
            [DateTimeOffset]::UtcNow,
            "Eastern Standard Time"
        )
    }
    if ($localNow -lt $open.AddMinutes(2)) {
        & $Python -m trading_system.cli webull automatic-submit-tick `
            --database $Database `
            --session-id $SessionId `
            --config $WebullConfig `
            --automatic-config $AutomaticConfig `
            --exit-config $ExitConfig `
            --exit-capabilities $ExitCapabilities `
            --account-class INDIVIDUAL_MARGIN `
            --enable-automatic-sandbox-submission 2>&1 | Tee-Object -FilePath $Log -Append
        if ($LASTEXITCODE -ne 0) {
            throw "Automatic Webull sandbox submission tick failed with exit code $LASTEXITCODE"
        }
    }
    while ($localNow -lt $close) {
        Start-Sleep -Seconds 30
        $localNow = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
            [DateTimeOffset]::UtcNow,
            "Eastern Standard Time"
        )
    }
}
finally {
    Remove-Item Env:WEBULL_SANDBOX_SUBMISSION_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:WEBULL_SANDBOX_EXIT_ENABLED -ErrorAction SilentlyContinue
    Pop-Location
}
