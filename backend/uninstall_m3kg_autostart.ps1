[CmdletBinding()]
param(
    [string]$TaskName = "M3KG Local Server",
    [string]$WatchdogTaskName = "M3KG Local Server Watchdog",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$serverScript = Join-Path $PSScriptRoot "serve_website.py"
$runnerScript = Join-Path $PSScriptRoot "run_m3kg_server.ps1"

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$existingWatchdogTask = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
if ($existingWatchdogTask) {
    Stop-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false
}

Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine.Contains($serverScript) -and
        $_.CommandLine.Contains("--port $Port")
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and $_.CommandLine.Contains($runnerScript)
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Output "M3KG local auto-start has been removed."
