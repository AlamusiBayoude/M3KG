[CmdletBinding()]
param(
    [string]$TaskName = "M3KG Local Server",
    [string]$WatchdogTaskName = "M3KG Local Server Watchdog",
    [int]$Port = 8765,
    [string]$PythonExe = "D:\Program Files\Python311\python.exe"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$serverScript = Join-Path $PSScriptRoot "serve_website.py"
$runnerScript = Join-Path $PSScriptRoot "run_m3kg_server.ps1"
$watchdogScript = Join-Path $PSScriptRoot "watch_m3kg_server.ps1"
$webDir = Join-Path $projectRoot "web"
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
    throw "Server script not found: $serverScript"
}
if (-not (Test-Path -LiteralPath $runnerScript -PathType Leaf)) {
    throw "Server runner not found: $runnerScript"
}
if (-not (Test-Path -LiteralPath $watchdogScript -PathType Leaf)) {
    throw "Server watchdog not found: $watchdogScript"
}
if (-not (Test-Path -LiteralPath (Join-Path $webDir "index.html") -PathType Leaf)) {
    throw "Website entry point not found: $webDir\index.html"
}

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

# Remove only stale instances of this workspace's server before installing the task.
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

$arguments = @(
    "-NoProfile"
    "-WindowStyle Hidden"
    "-ExecutionPolicy Bypass"
    "-File `"$runnerScript`""
    "-Port $Port"
    "-PythonExe `"$PythonExe`""
) -join " "

$action = New-ScheduledTaskAction `
    -Execute $powershellExe `
    -Argument $arguments `
    -WorkingDirectory $projectRoot

$watchdogArguments = @(
    "-NoProfile"
    "-WindowStyle Hidden"
    "-ExecutionPolicy Bypass"
    "-File `"$watchdogScript`""
    "-TaskName `"$TaskName`""
    "-Port $Port"
) -join " "

$watchdogAction = New-ScheduledTaskAction `
    -Execute $powershellExe `
    -Argument $watchdogArguments `
    -WorkingDirectory $projectRoot

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$watchdogLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$watchdogIntervalTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$watchdogSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $logonTrigger `
    -Settings $settings `
    -Description "Keeps the local M3KG website available at http://127.0.0.1:$Port/." `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName $WatchdogTaskName `
    -Action $watchdogAction `
    -Trigger @($watchdogLogonTrigger, $watchdogIntervalTrigger) `
    -Settings $watchdogSettings `
    -Description "Checks the local M3KG website every five minutes and restarts its main task when needed." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName

$url = "http://127.0.0.1:$Port/"
$healthUrl = "http://127.0.0.1:$Port/api/stats"
$deadline = (Get-Date).AddMinutes(4)
$lastError = $null
do {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
        $healthResponse = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 10
        if ($response.StatusCode -eq 200 -and $healthResponse.StatusCode -eq 200) {
            $task = Get-ScheduledTask -TaskName $TaskName
            [PSCustomObject]@{
                TaskName = $TaskName
                WatchdogTaskName = $WatchdogTaskName
                State = $task.State
                Url = $url
                StatusCode = $response.StatusCode
                ApiStatusCode = $healthResponse.StatusCode
                AutoStart = "At user logon"
                RestartPolicy = "5-second process retry plus 5-minute independent health watchdog"
            } | Format-List
            exit 0
        }
    }
    catch {
        $lastError = $_.Exception.Message
    }
} while ((Get-Date) -lt $deadline)

throw "The scheduled task was installed, but $url did not become ready. Last error: $lastError"
