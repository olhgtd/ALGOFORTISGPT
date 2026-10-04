$ErrorActionPreference = "Continue"

$installDir = "C:\Program Files\AlgoFortis"
$exeName = "AlgoFortis.exe"
$appName = "AlgoFortis"
if (-not (Test-Path "$installDir\$exeName")) {
    $installDir = "C:\Program Files\AlgoFortis"
    $exeName = "AlgoFortis.exe"
    $appName = "AlgoFortis"
}

$logFile = "$env:LOCALAPPDATA\$appName\logs\launcher.log"
if (Test-Path $logFile) { Clear-Content $logFile }

Write-Host "Starting $appName ($installDir\$exeName)..."
$proc = Start-Process -FilePath "$installDir\$exeName" -PassThru
Write-Host "Launched PID: $($proc.Id)"

Start-Sleep -Seconds 10

Write-Host "`n--- Launcher Log ---"
if (Test-Path $logFile) {
    Get-Content $logFile -Tail 40
} else {
    Write-Host "No log file found."
}

Write-Host "`n--- Backend Status ---"
& "$installDir\runtime\python\python.exe" -m dashboard.runtime.controller status --mode LOCAL_PRIVATE

Write-Host "`n--- Process Tree for $appName & WebView2 ---"
Get-Process | Where-Object { $_.ProcessName -match "msedgewebview2|$appName" } | Select-Object Id, ProcessName, MainWindowTitle

Write-Host "`nStopping test instance..."
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
& "$installDir\runtime\python\python.exe" -m dashboard.runtime.controller stop --mode LOCAL_PRIVATE
Start-Sleep -Seconds 2
Write-Host "Cleanup complete."
