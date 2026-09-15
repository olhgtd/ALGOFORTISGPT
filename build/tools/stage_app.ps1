$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$stageDir = "$cleanRoot\build\stage"

Write-Host "Staging core product files to $stageDir..."

# Clean any legacy SentinelX artifacts in stage
Get-ChildItem -Path $stageDir -Filter "*SentinelX*" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $stageDir -Filter "*sentinelx*" -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Root launcher and metadata
Copy-Item "$cleanRoot\START_ALGOFORTIS.pyw" "$stageDir\" -Force
Copy-Item "$cleanRoot\algofortis.ico" "$stageDir\" -Force
Copy-Item "$cleanRoot\algofortis_logo.png" "$stageDir\" -Force
Copy-Item "$cleanRoot\README.md" "$stageDir\" -Force

# Compile latest native AlgoFortis.exe launcher
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\compile_launcher.ps1"

# Config
if (Test-Path "$stageDir\config") { Remove-Item -Recurse -Force "$stageDir\config" }
Copy-Item -Recurse "$cleanRoot\config" "$stageDir\config"

# Data assets
if (Test-Path "$stageDir\data") { Remove-Item -Recurse -Force "$stageDir\data" }
Copy-Item -Recurse "$cleanRoot\data" "$stageDir\data"

# Engine
if (Test-Path "$stageDir\engine") { Remove-Item -Recurse -Force "$stageDir\engine" }
Copy-Item -Recurse "$cleanRoot\engine" "$stageDir\engine"

# Strategies
if (Test-Path "$stageDir\strategies") { Remove-Item -Recurse -Force "$stageDir\strategies" }
Copy-Item -Recurse "$cleanRoot\strategies" "$stageDir\strategies"

# Dashboard
$stageDashboard = "$stageDir\dashboard"
if (Test-Path $stageDashboard) { Remove-Item -Recurse -Force $stageDashboard }
New-Item -ItemType Directory -Force $stageDashboard | Out-Null

Copy-Item "$cleanRoot\dashboard\__init__.py" "$stageDashboard\"
Copy-Item -Recurse "$cleanRoot\dashboard\backend" "$stageDashboard\backend"
Copy-Item -Recurse "$cleanRoot\dashboard\runtime" "$stageDashboard\runtime"
Copy-Item -Recurse "$cleanRoot\dashboard\shared" "$stageDashboard\shared"

# Web dist
New-Item -ItemType Directory -Force "$stageDashboard\web\dist" | Out-Null
Copy-Item -Recurse "$cleanRoot\dashboard\web\dist\*" "$stageDashboard\web\dist\"

# Clean any pycache in stage
Get-ChildItem -Path $stageDir -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path $stageDir -Filter "*.pyc" -Recurse -File | Remove-Item -Force

Write-Host "Staging complete. Verifying stage contents..."
Get-ChildItem $stageDir | Select-Object Name, Length, Mode
