param(
    [string]$TaskName = "Trading System - Phase 12D Shadow Audit"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run-phase12d-shadow-audit.ps1"
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) {
    throw "Phase 12D runner was not found: $Runner"
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $user `
    -LogonType Interactive `
    -RunLevel Limited `
    -ErrorAction Stop
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -ErrorAction Stop
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`""
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $ProjectRoot `
    -ErrorAction Stop
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday") `
    -At "19:10" `
    -ErrorAction Stop
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force `
    -ErrorAction Stop | Out-Null
Write-Output "Installed: $TaskName (weekdays at 19:10 America/New_York)"
Write-Output "The audit records evidence only; it never retries a session or calls Webull."
