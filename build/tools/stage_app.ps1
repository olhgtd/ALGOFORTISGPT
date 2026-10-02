param(
    [string]$WebView2Version = "1.0.4258.31",
    [string]$ExpectedWebView2PackageSha256 = ""
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$stageDir = "$cleanRoot\build\stage"
$webDist = "$cleanRoot\dashboard\web\dist"

if (-not (Test-Path $webDist)) {
    throw "Dashboard production dist is missing. Run npm --prefix dashboard/web run build first."
}

Write-Host "Creating clean release stage: $stageDir"
if (Test-Path $stageDir) {
    Remove-Item -Recurse -Force $stageDir
}
New-Item -ItemType Directory -Force $stageDir | Out-Null

Write-Host "Restoring pinned WebView2 build/runtime inputs..."
$webViewArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "$toolsDir\restore_webview2.ps1",
    "-Version", $WebView2Version
)
if ($ExpectedWebView2PackageSha256) {
    $webViewArgs += @("-ExpectedPackageSha256", $ExpectedWebView2PackageSha256)
}
& powershell.exe @webViewArgs
if ($LASTEXITCODE -ne 0) {
    throw "WebView2 staging failed with code $LASTEXITCODE"
}

Write-Host "Packaging exact Python runtime..."
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\package_python.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Packaged Python staging failed with code $LASTEXITCODE"
}

foreach ($source in @(
    "$cleanRoot\START_ALGOFORTIS.pyw",
    "$cleanRoot\algofortis.ico",
    "$cleanRoot\algofortis_logo.png",
    "$cleanRoot\README.md"
)) {
    if (-not (Test-Path $source)) {
        throw "Required product file missing: $source"
    }
    Copy-Item $source "$stageDir\" -Force
}

foreach ($dirName in @("config", "data", "engine", "strategies")) {
    $sourceDir = Join-Path $cleanRoot $dirName
    if (-not (Test-Path $sourceDir)) {
        throw "Required product directory missing: $sourceDir"
    }
    Copy-Item -Recurse $sourceDir (Join-Path $stageDir $dirName)
}

$stageDashboard = "$stageDir\dashboard"
New-Item -ItemType Directory -Force $stageDashboard | Out-Null
foreach ($dashboardDir in @("backend", "runtime", "shared")) {
    $sourceDir = "$cleanRoot\dashboard\$dashboardDir"
    if (-not (Test-Path $sourceDir)) {
        throw "Required dashboard directory missing: $sourceDir"
    }
    Copy-Item -Recurse $sourceDir "$stageDashboard\$dashboardDir"
}
Copy-Item "$cleanRoot\dashboard\__init__.py" "$stageDashboard\" -Force
New-Item -ItemType Directory -Force "$stageDashboard\web\dist" | Out-Null
Copy-Item -Recurse "$webDist\*" "$stageDashboard\web\dist\"

Write-Host "Compiling unsigned launcher from clean staged WebView2 references..."
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\compile_launcher.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Launcher compilation failed with code $LASTEXITCODE"
}

Get-ChildItem -Path $stageDir -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $stageDir -Filter "*.pyc" -Recurse -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$requiredStageFiles = @(
    "$stageDir\AlgoFortis.exe",
    "$stageDir\Microsoft.Web.WebView2.Core.dll",
    "$stageDir\Microsoft.Web.WebView2.WinForms.dll",
    "$stageDir\WebView2Loader.dll",
    "$stageDir\runtime\python\python.exe",
    "$stageDashboard\web\dist\index.html"
)
foreach ($required in $requiredStageFiles) {
    if (-not (Test-Path $required)) {
        throw "Release stage incomplete: $required"
    }
}

$forbidden = Get-ChildItem -Path $stageDir -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "SentinelX" -or $_.Name -match "sentinelx" }
if ($forbidden) {
    $names = ($forbidden | ForEach-Object { $_.FullName }) -join "; "
    throw "Legacy-branded stage artifacts are forbidden: $names"
}

Write-Host "STAGE_APP=PASS"
Write-Host "STAGE_LIVE_STATE=READ_ONLY/DISARMED"
