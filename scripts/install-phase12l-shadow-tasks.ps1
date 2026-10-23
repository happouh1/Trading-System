param([switch]$SkipWakeTimerConfiguration)

$ErrorActionPreference = "Stop"
$installer = Join-Path $PSScriptRoot "install-phase12h-shadow-tasks.ps1"
& $installer `
    -CloseRunnerFile "run-phase12l-shadow-close.ps1" `
    -AuditRunnerFile "run-phase12l-shadow-audit.ps1" `
    -WatchdogConfig "config/burn-in.phase12l.watchdog.v1.json" `
    -WorkerConfig "config/webull.phase12i.readonly.v1.json" `
    -DecisionConfig "config/webull.phase12h.decisions.v1.json" `
    -ShortOpportunityConfig "config/webull.phase12i.short-opportunities.v1.json" `
    -LogNamespace "phase12l" `
    -ConfigureWakeTimers:(-not $SkipWakeTimerConfiguration)
if ($LASTEXITCODE -ne 0) { throw "Phase 12L scheduled-task upgrade failed" }

$close = [string](Get-ScheduledTask -TaskName "Trading System - Phase 12H Shadow Close").Actions[0].Arguments
$audit = [string](Get-ScheduledTask -TaskName "Trading System - Phase 12H Shadow Audit").Actions[0].Arguments
$watchdog = [string](Get-ScheduledTask -TaskName "Trading System - Phase 12H Shadow Watchdog").Actions[0].Arguments
if (-not $close.Contains("run-phase12l-shadow-close.ps1")) { throw "Phase 12L close runner was not installed" }
if (-not $audit.Contains("run-phase12l-shadow-audit.ps1")) { throw "Phase 12L audit runner was not installed" }
if (-not $watchdog.Contains("burn-in.phase12l.watchdog.v1.json")) { throw "Phase 12L watchdog was not installed" }
Write-Output "Phase 12L lifecycle-aware close, audit, and watchdog actions are installed."
