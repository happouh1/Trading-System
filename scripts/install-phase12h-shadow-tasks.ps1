param(
    [string]$PreflightTaskName = "Trading System - Phase 12H Shadow Preflight",
    [string]$StartTaskName = "Trading System - Phase 12H Shadow Start",
    [string]$CloseTaskName = "Trading System - Phase 12H Shadow Close",
    [string]$AuditTaskName = "Trading System - Phase 12H Shadow Audit",
    [string]$WatchdogTaskName = "Trading System - Phase 12H Shadow Watchdog",
    [string]$CloseRunnerFile = "run-phase12c-shadow-close.ps1",
    [string]$WorkerConfig = "config/webull.phase12h.readonly.v1.json",
    [string]$DecisionConfig = "config/webull.phase12h.decisions.v1.json",
    [string]$ShortOpportunityConfig = "",
    [string]$LogNamespace = "phase12h",
    [bool]$ConfigureWakeTimers = $true
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$InstallLogDirectory = Join-Path $ProjectRoot ".operator-home\phase12h\logs"
$InstallLog = Join-Path $InstallLogDirectory "scheduler-install.log"

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = New-Object System.Security.Principal.WindowsPrincipal($currentIdentity)
$isAdministrator = $currentPrincipal.IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdministrator) {
    $forwardedArguments = @()
    foreach ($parameter in $PSBoundParameters.GetEnumerator()) {
        if ($parameter.Value -is [bool]) {
            $forwardedArguments += "-$($parameter.Key):`$$($parameter.Value.ToString().ToLowerInvariant())"
            continue
        }
        $escapedValue = $parameter.Value.ToString().Replace('"', '`"')
        $forwardedArguments += "-$($parameter.Key) `"$escapedValue`""
    }
    $quotedScript = '"' + $PSCommandPath + '"'
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy Bypass",
        "-File $quotedScript",
        ($forwardedArguments -join " ")
    ) -join " "
    try {
        $elevated = Start-Process `
            -FilePath "powershell.exe" `
            -Verb RunAs `
            -ArgumentList $arguments `
            -Wait `
            -PassThru `
            -ErrorAction Stop
    }
    catch {
        throw "Administrator approval is required to install Phase 12H tasks. " +
            "Run the installer again and choose Yes on the Windows UAC prompt."
    }
    if (Test-Path -LiteralPath $InstallLog -PathType Leaf) {
        Get-Content -LiteralPath $InstallLog -Tail 50
    }
    exit $elevated.ExitCode
}

New-Item -ItemType Directory -Path $InstallLogDirectory -Force | Out-Null
"$(Get-Date -Format o) BEGIN elevated Phase 12H scheduler installation" |
    Set-Content -LiteralPath $InstallLog -Encoding UTF8
trap {
    "$(Get-Date -Format o) FAILED $($_.Exception.Message)" |
        Add-Content -LiteralPath $InstallLog -Encoding UTF8
    exit 1
}

$PreflightRunner = Join-Path $PSScriptRoot "run-phase12e-shadow-preflight.ps1"
$StartRunner = Join-Path $PSScriptRoot "run-phase12c-shadow-start.ps1"
$CloseRunner = Join-Path $PSScriptRoot $CloseRunnerFile
$AuditRunner = Join-Path $PSScriptRoot "run-phase12d-shadow-audit.ps1"
$WatchdogRunner = Join-Path $PSScriptRoot "run-phase12h-shadow-watchdog.ps1"
$TaskSnapshotWriter = Join-Path $PSScriptRoot "write-phase12h-task-snapshot.ps1"
foreach ($runner in @(
    $PreflightRunner, $StartRunner, $CloseRunner, $AuditRunner, $WatchdogRunner,
    $TaskSnapshotWriter
)) {
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Phase 12H runner was not found: $runner"
    }
}

if ($ConfigureWakeTimers) {
    & powercfg.exe /SETACVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
    if ($LASTEXITCODE -ne 0) { throw "Failed to enable AC wake timers" }
    & powercfg.exe /SETDCVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
    if ($LASTEXITCODE -ne 0) { throw "Failed to enable battery wake timers" }
    & powercfg.exe /SETACTIVE SCHEME_CURRENT
    if ($LASTEXITCODE -ne 0) { throw "Failed to activate the wake-enabled power plan" }
}

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $user `
    -LogonType S4U `
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

function New-Phase12HAction {
    param([string]$Runner, [string]$RunnerArguments)
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Runner`" $RunnerArguments"
    New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $arguments `
        -WorkingDirectory $ProjectRoot `
        -ErrorAction Stop
}

function New-Phase12HTrigger {
    param([string]$At)
    New-ScheduledTaskTrigger `
        -Weekly `
        -WeeksInterval 1 `
        -DaysOfWeek $days `
        -At $At `
        -ErrorAction Stop
}

function Install-Phase12HTask {
    param(
        [string]$TaskName,
        [string]$Runner,
        [string[]]$At,
        [string]$RunnerArguments
    )
    $triggers = @($At | ForEach-Object { New-Phase12HTrigger -At $_ })
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action (New-Phase12HAction -Runner $Runner -RunnerArguments $RunnerArguments) `
        -Trigger $triggers `
        -Settings $settings `
        -Principal $principal `
        -Force `
        -ErrorAction Stop | Out-Null
    "$(Get-Date -Format o) REGISTERED $TaskName" |
        Add-Content -LiteralPath $InstallLog -Encoding UTF8
}

$schedule = '-Schedule "config/burn-in.phase12h.schedule.v1.json"'
$shared = $schedule + ' -WebullConfig "config/webull.sandbox.v1.yaml"' +
    ' -WorkerConfig "' + $WorkerConfig + '"' +
    ' -DecisionConfig "' + $DecisionConfig + '"' +
    ' -ThresholdsConfig "config/thresholds.phase1e.v1.yaml"' +
    ' -LogNamespace "' + $LogNamespace + '"'
$closeShared = $shared
if (-not [string]::IsNullOrWhiteSpace($ShortOpportunityConfig)) {
    $closeShared += ' -ShortOpportunityConfig "' + $ShortOpportunityConfig + '"'
}
$audit = '-AuditConfig "config/burn-in.phase12h.audit.v1.json" -LogNamespace "phase12h"'
$watchdog = '-Config "config/burn-in.phase12h.watchdog.v1.json"'

try {
    Install-Phase12HTask -TaskName $PreflightTaskName -Runner $PreflightRunner `
        -At @("09:25") -RunnerArguments $schedule
    Install-Phase12HTask -TaskName $StartTaskName -Runner $StartRunner `
        -At @("09:30") -RunnerArguments $shared
    Install-Phase12HTask -TaskName $CloseTaskName -Runner $CloseRunner `
        -At @("16:05") -RunnerArguments $closeShared
    Install-Phase12HTask -TaskName $AuditTaskName -Runner $AuditRunner `
        -At @("19:10") -RunnerArguments $audit
    Install-Phase12HTask -TaskName $WatchdogTaskName -Runner $WatchdogRunner `
        -At @("09:50", "16:20", "19:25") -RunnerArguments $watchdog
}
catch {
    throw "Phase 12H scheduled-task registration failed: $($_.Exception.Message)"
}

foreach ($name in @(
    $PreflightTaskName, $StartTaskName, $CloseTaskName, $AuditTaskName, $WatchdogTaskName
)) {
    $installed = Get-ScheduledTask -TaskName $name -ErrorAction Stop
    if ($installed.Principal.LogonType.ToString() -ne "S4U") {
        throw "Phase 12H task is not configured for logged-out execution: $name"
    }
    if (-not $installed.Settings.WakeToRun) {
        throw "Phase 12H task is not configured to wake the computer: $name"
    }
}

foreach ($superseded in @(
    "Trading System - Phase 12E Shadow Preflight",
    "Trading System - Phase 12E Shadow Start",
    "Trading System - Phase 12E Shadow Close",
    "Trading System - Phase 12E Shadow Audit"
)) {
    if (Get-ScheduledTask -TaskName $superseded -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName $superseded -ErrorAction Stop | Out-Null
    }
}

& $TaskSnapshotWriter | Out-Null

Write-Output "Installed five Phase 12H S4U tasks for logged-out execution."
Write-Output "Preflight 09:25; start 09:30; close 16:05; audit 19:10 America/New_York."
Write-Output "Watchdog checks run at 09:50, 16:20, and 19:25."
Write-Output "Wake timers and wake-to-run are enabled; shutdown cannot be recovered automatically."
Write-Output "Superseded Phase 12E tasks were retained but disabled."
"$(Get-Date -Format o) COMPLETE five verified S4U tasks installed" |
    Add-Content -LiteralPath $InstallLog -Encoding UTF8
