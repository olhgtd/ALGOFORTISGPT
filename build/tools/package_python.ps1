param(
    [string]$ExpectedPythonVersion = "3.13.14"
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$stagePython = "$cleanRoot\build\stage\runtime\python"

function Find-BasePython {
    if ($env:BASE_PYTHON -and (Test-Path $env:BASE_PYTHON)) {
        return (Resolve-Path $env:BASE_PYTHON).Path
    }
    $pyCmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return (Split-Path $pyCmd.Source -Parent)
    }
    return $null
}

$basePython = Find-BasePython
if (-not $basePython) {
    throw "Base CPython directory not found. Set BASE_PYTHON or put python.exe on PATH."
}
$basePythonExe = Join-Path $basePython "python.exe"
if (-not (Test-Path $basePythonExe)) {
    throw "python.exe not found under BASE_PYTHON: $basePython"
}

$actualVersion = (& $basePythonExe -c "import platform; print(platform.python_version())").Trim()
if ($actualVersion -ne $ExpectedPythonVersion) {
    throw "Release runtime requires CPython $ExpectedPythonVersion exactly; found $actualVersion at $basePython"
}
Write-Host "Using exact CPython $actualVersion from: $basePython"

if (Test-Path $stagePython) {
    Remove-Item -Recurse -Force $stagePython
}
New-Item -ItemType Directory -Force $stagePython | Out-Null

$requiredRootFiles = @(
    "python.exe",
    "pythonw.exe",
    "python3.dll",
    "python313.dll",
    "vcruntime140.dll"
)
foreach ($name in $requiredRootFiles) {
    $source = Join-Path $basePython $name
    if (-not (Test-Path $source)) {
        throw "Required CPython runtime file missing: $source"
    }
    Copy-Item $source $stagePython -Force
}
$vcruntimeExtra = Join-Path $basePython "vcruntime140_1.dll"
if (Test-Path $vcruntimeExtra) {
    Copy-Item $vcruntimeExtra $stagePython -Force
}

foreach ($dirName in @("DLLs", "Lib")) {
    $sourceDir = Join-Path $basePython $dirName
    if (-not (Test-Path $sourceDir)) {
        throw "Required CPython directory missing: $sourceDir"
    }
}
Copy-Item -Recurse (Join-Path $basePython "DLLs") $stagePython

New-Item -ItemType Directory -Force "$stagePython\Lib" | Out-Null
Get-ChildItem "$basePython\Lib" -Exclude "site-packages","__pycache__" | ForEach-Object {
    Copy-Item -Recurse $_.FullName "$stagePython\Lib"
}
New-Item -ItemType Directory -Force "$stagePython\Lib\site-packages" | Out-Null

$runtimeReqs = "$cleanRoot\requirements-runtime.lock.txt"
$dashboardReqs = "$cleanRoot\requirements-dashboard.lock.txt"
foreach ($req in @($runtimeReqs, $dashboardReqs)) {
    if (-not (Test-Path $req)) {
        throw "Locked dependency file missing: $req"
    }
}

Write-Host "Installing exact locked runtime closure into packaged Python..."
$pipArgs = @(
    "-m", "pip", "install",
    "--disable-pip-version-check",
    "--no-cache-dir",
    "--target", "$stagePython\Lib\site-packages",
    "-r", $runtimeReqs,
    "-r", $dashboardReqs
)
& $basePythonExe @pipArgs
if ($LASTEXITCODE -ne 0) {
    throw "Locked runtime dependency installation failed with code $LASTEXITCODE"
}

$verifyScript = @"
import os
import platform
import sys
assert platform.python_version() == "$ExpectedPythonVersion", platform.python_version()
assert os.path.normcase(os.path.normpath(sys.prefix)) == os.path.normcase(os.path.normpath(r"$stagePython")), (sys.prefix, r"$stagePython")
import openpyxl, pandas, google.protobuf, pyarrow, yaml, websockets, xlrd
import fastapi, starlette, uvicorn, fido2, cryptography
print("PACKAGED_PYTHON_VERSION=" + platform.python_version())
print("ALL_PACKAGED_RUNTIME_DEPENDENCIES_LOADED_SUCCESSFULLY")
"@
$verifyScriptPath = Join-Path $stagePython "verify-packaged-python.py"
$verifyScript | Set-Content -Encoding utf8 $verifyScriptPath
try {
    $result = & "$stagePython\python.exe" $verifyScriptPath
    $verifyExitCode = $LASTEXITCODE
    Write-Host $result
    $verificationMarker = "ALL_PACKAGED_RUNTIME_DEPENDENCIES_LOADED_SUCCESSFULLY"
    if ($verifyExitCode -ne 0 -or $result -notcontains $verificationMarker) {
        throw "Packaged Python verification failed"
    }
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $verifyScriptPath
}

Get-ChildItem -Path $stagePython -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $stagePython -Filter "*.pyc" -Recurse -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "PACKAGED_PYTHON=PASS"
