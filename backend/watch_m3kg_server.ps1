[CmdletBinding()]
param(
    [string]$TaskName = "M3KG Local Server",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $projectRoot "logs"
$logPath = Join-Path $logDir "m3kg_watchdog.log"
$healthUrl = "http://127.0.0.1:$Port/api/stats"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        exit 0
    }
}
catch {
    # A failed health request is handled by checking and starting the main task.
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] Main task '$TaskName' was not found."
    exit 1
}

if ($task.State -ne "Running") {
    Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] Health check failed; starting '$TaskName'."
    Start-ScheduledTask -TaskName $TaskName
}
