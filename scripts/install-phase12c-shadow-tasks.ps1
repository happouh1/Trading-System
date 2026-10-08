param(
    [string]$StartTaskName = "Trading System - Phase 12C Shadow Start",
    [string]$CloseTaskName = "Trading System - Phase 12C Shadow Close"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-start.ps1"
$CloseRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-close.ps1"
foreach ($runner in @($StartRunner, $CloseRunner)) {
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Phase 12C runner was not found: $runner"
    }
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
$days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

function Install-Phase12CTask {
    param(
        [string]$TaskName,
        [string]$Runner,
        [string]$At
    )
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`""
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $arguments `
        -WorkingDirectory $ProjectRoot `
        -ErrorAction Stop
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -WeeksInterval 1 `
        -DaysOfWeek $days `
        -At $At `
        -ErrorAction Stop
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force `
        -ErrorAction Stop | Out-Null
}

try {
    Install-Phase12CTask -TaskName $StartTaskName -Runner $StartRunner -At "09:30"
    Install-Phase12CTask -TaskName $CloseTaskName -Runner $CloseRunner -At "16:05"
}
catch {
    throw "Phase 12C scheduled-task registration failed: $($_.Exception.Message)"
}
Write-Output "Installed: $StartTaskName (weekdays at 09:30 America/New_York)"
Write-Output "Installed: $CloseTaskName (weekdays at 16:05 America/New_York)"
Write-Output "The frozen XNYS manifest skips holidays and dates outside 2026-10-07 through 2026-11-03."
