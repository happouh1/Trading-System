$ErrorActionPreference = "Stop"

$variableNames = @(
    "WEBULL_ENVIRONMENT",
    "WEBULL_APP_KEY",
    "WEBULL_APP_SECRET",
    "WEBULL_ACCOUNT_ID"
)

$missing = @(
    $variableNames | Where-Object {
        [string]::IsNullOrWhiteSpace(
            [Environment]::GetEnvironmentVariable($_, "Process")
        )
    }
)

if ($missing.Count -ne 0) {
    throw "Missing process variables: $($missing -join ', ')"
}

foreach ($name in $variableNames) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $value, "User")
    [Environment]::SetEnvironmentVariable($name.Replace("_", "\_"), $null, "User")
}

foreach ($name in $variableNames) {
    $configured = -not [string]::IsNullOrWhiteSpace(
        [Environment]::GetEnvironmentVariable($name, "User")
    )
    Write-Output "$name configured: $configured"
}
