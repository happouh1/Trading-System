param(
    [switch]$SkipWakeTimerConfiguration,
    [string]$DiagnosticLog = ""
)

$ErrorActionPreference = "Stop"
$installer = Join-Path $PSScriptRoot "install-phase12h-shadow-tasks.ps1"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $projectRoot ".operator-home\phase12i\logs"
$elevatedLog = Join-Path $logRoot "scheduler-install-elevated.log"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = New-Object System.Security.Principal.WindowsPrincipal($currentIdentity)
$isAdministrator = $currentPrincipal.IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)
$transcribing = $false
if ($isAdministrator -and -not [string]::IsNullOrWhiteSpace($DiagnosticLog)) {
    Start-Transcript -LiteralPath $DiagnosticLog -Force | Out-Null
    $transcribing = $true
}

if (-not $isAdministrator) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy Bypass",
        "-File `"$PSCommandPath`"",
        "-DiagnosticLog `"$elevatedLog`""
    )
    if ($SkipWakeTimerConfiguration) {
        $arguments += "-SkipWakeTimerConfiguration"
    }
    $arguments = $arguments -join " "
    try {
        Set-Content -LiteralPath $elevatedLog -Value "" -Encoding UTF8
        $elevated = Start-Process `
            -FilePath "powershell.exe" `
            -Verb RunAs `
            -ArgumentList $arguments `
            -Wait `
            -PassThru `
            -ErrorAction Stop
    }
    catch {
        throw "Administrator approval is required to install Phase 12I tasks."
    }
    if ($elevated.ExitCode -ne 0) {
        $details = Get-Content -LiteralPath $elevatedLog -ErrorAction SilentlyContinue |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        throw (
            "Elevated Phase 12I installation failed with exit code " +
            "$($elevated.ExitCode). " + ($details -join " | ")
        )
    }
}
else {
    & $installer `
        -CloseRunnerFile "run-phase12i-shadow-close.ps1" `
        -WorkerConfig "config/webull.phase12i.readonly.v1.json" `
        -DecisionConfig "config/webull.phase12h.decisions.v1.json" `
        -ShortOpportunityConfig "config/webull.phase12i.short-opportunities.v1.json" `
        -LogNamespace "phase12i" `
        -ConfigureWakeTimers:(-not $SkipWakeTimerConfiguration)
}

$closeTaskName = "Trading System - Phase 12H Shadow Close"
$closeTask = Get-ScheduledTask -TaskName $closeTaskName -ErrorAction Stop
$closeArguments = [string]$closeTask.Actions[0].Arguments
foreach ($required in @(
    "run-phase12i-shadow-close.ps1",
    "webull.phase12i.readonly.v1.json",
    "webull.phase12i.short-opportunities.v1.json",
    "phase12i"
)) {
    if (-not $closeArguments.Contains($required)) {
        throw "Phase 12I close-task verification failed; missing action argument: $required"
    }
}

if ($transcribing) {
    Stop-Transcript | Out-Null
}

Write-Output "Phase 12H task identities now run the Phase 12I expanded shadow overlay."
Write-Output "No additional or competing scheduled tasks were created."
