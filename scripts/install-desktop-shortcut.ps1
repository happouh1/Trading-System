param(
    [string]$ShortcutPath = (Join-Path ([Environment]::GetFolderPath("Desktop")) "Trading System.lnk")
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$launcherPath = Join-Path $projectRoot "scripts\start-trading-system.ps1"
$powerShellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
    throw "Trading System launcher is missing: $launcherPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $powerShellPath
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Open the Trading System operator home"
$shortcut.IconLocation = "$powerShellPath,0"
$shortcut.Save()

Write-Output "Created Trading System shortcut: $ShortcutPath"
