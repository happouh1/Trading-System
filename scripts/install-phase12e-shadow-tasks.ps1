param(
    [string]$PreflightTaskName = "Trading System - Phase 12E Shadow Preflight",
    [string]$StartTaskName = "Trading System - Phase 12E Shadow Start",
    [string]$CloseTaskName = "Trading System - Phase 12E Shadow Close",
    [string]$AuditTaskName = "Trading System - Phase 12E Shadow Audit"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PreflightRunner = Join-Path $PSScriptRoot "run-phase12e-shadow-preflight.ps1"
$StartRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-start.ps1"
$CloseRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-close.ps1"
$AuditRunner = Join-Path $PSScriptRoot "run-phase12d-shadow-audit.ps1"
foreach ($runner in @($PreflightRunner, $StartRunner, $CloseRunner, $AuditRunner)) {
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Phase 12E runner was not found: $runner"
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

function Install-Phase12ETask {
    param(
        [string]$TaskName,
        [string]$Runner,
        [string]$At,
        [string]$RunnerArguments
    )
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`" $RunnerArguments"
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

$schedule = '-Schedule "config/burn-in.phase12e.schedule.v1.json"'
$shared = $schedule + ' -WebullConfig "config/webull.sandbox.v1.yaml"' +
    ' -WorkerConfig "config/webull.phase12e.readonly.v1.json"' +
    ' -DecisionConfig "config/webull.phase12e.decisions.v1.json"' +
    ' -ThresholdsConfig "config/thresholds.phase1e.v1.yaml"' +
    ' -LogNamespace "phase12e"'
$audit = '-AuditConfig "config/burn-in.phase12e.audit.v1.json" -LogNamespace "phase12e"'

try {
    Install-Phase12ETask -TaskName $PreflightTaskName -Runner $PreflightRunner `
        -At "09:25" -RunnerArguments $schedule
    Install-Phase12ETask -TaskName $StartTaskName -Runner $StartRunner `
        -At "09:30" -RunnerArguments $shared
    Install-Phase12ETask -TaskName $CloseTaskName -Runner $CloseRunner `
        -At "16:05" -RunnerArguments $shared
    Install-Phase12ETask -TaskName $AuditTaskName -Runner $AuditRunner `
        -At "19:10" -RunnerArguments $audit
}
catch {
    throw "Phase 12E scheduled-task registration failed: $($_.Exception.Message)"
}

foreach ($superseded in @(
    "Trading System - Phase 12C Shadow Start",
    "Trading System - Phase 12C Shadow Close",
    "Trading System - Phase 12D Shadow Audit"
)) {
    if (Get-ScheduledTask -TaskName $superseded -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName $superseded -ErrorAction Stop | Out-Null
    }
}

Write-Output "Installed: $PreflightTaskName (weekdays at 09:25 America/New_York)"
Write-Output "Installed: $StartTaskName (weekdays at 09:30 America/New_York)"
Write-Output "Installed: $CloseTaskName (weekdays at 16:05 America/New_York)"
Write-Output "Installed: $AuditTaskName (weekdays at 19:10 America/New_York)"
Write-Output "Wake-to-run and battery-safe execution are enabled."
Write-Output "Superseded Phase 12C/12D tasks were retained but disabled."
Write-Output "The frozen XNYS manifest covers 2026-10-08 through 2026-11-04."
