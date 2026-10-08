param(
    [string]$TaskName = "Trading System - Webull Sandbox Burn-In",
    [string]$SessionId = "burn-in-webull-20260928-01"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run-webull-automatic-sandbox-day.ps1"
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) {
    throw "Automatic sandbox runner was not found: $Runner"
}
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`" -SessionId `"$SessionId`""
try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $ProjectRoot -ErrorAction Stop
    $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "04:00" -ErrorAction Stop
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 16 -Minutes 15) -ErrorAction Stop
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited -ErrorAction Stop
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null
}
catch {
    throw "Scheduled-task registration failed. Open PowerShell as Administrator and run this installer again. $($_.Exception.Message)"
}
Write-Output "Installed scheduled task: $TaskName"
Write-Output "Schedule: Monday-Friday 04:00-20:00 America/New_York; order release only at 09:30-09:32."
