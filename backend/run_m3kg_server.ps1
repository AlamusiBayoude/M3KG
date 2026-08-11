[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$PythonExe = "D:\Program Files\Python311\python.exe"
)

$ErrorActionPreference = "Continue"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$serverScript = Join-Path $PSScriptRoot "serve_website.py"
$webDir = Join-Path $projectRoot "web"
$logDir = Join-Path $projectRoot "logs"
$logPath = Join-Path $logDir "m3kg_local_server.log"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$createdNew = $false
$mutexName = "Local\M3KGLocalServer_$Port"
$mutex = [System.Threading.Mutex]::new($true, $mutexName, [ref]$createdNew)
if (-not $createdNew) {
    Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] Another M3KG runner already owns $mutexName; exiting."
    $mutex.Dispose()
    exit 0
}

try {
    while ($true) {
        if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 2MB) {
            $previousLog = Join-Path $logDir "m3kg_local_server.previous.log"
            Move-Item -LiteralPath $logPath -Destination $previousLog -Force
        }

        Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] Starting M3KG server on port $Port."
        try {
            & $PythonExe `
                $serverScript `
                --host 127.0.0.1 `
                --port $Port `
                --web-dir $webDir 2>&1 |
                ForEach-Object {
                    Add-Content -LiteralPath $logPath -Value $_
                }
            $exitCode = $LASTEXITCODE
        }
        catch {
            $exitCode = 1
            Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] $($_.Exception.Message)"
        }

        Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format o)] Server exited with code $exitCode; retrying in 5 seconds."
        Start-Sleep -Seconds 5
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
