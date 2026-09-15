$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$stagePython = "$cleanRoot\build\stage\runtime\python"

function Find-BasePython {
    if ($env:BASE_PYTHON -and (Test-Path $env:BASE_PYTHON)) {
        return $env:BASE_PYTHON
    }
    $pyCmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $cand = Split-Path $pyCmd.Source -Parent
        if (Test-Path "$cand\python313.dll") {
            return $cand
        }
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313",
        "$env:ProgramFiles\Python313",
        "C:\Python313",
        "C:\Users\Ragini Music\AppData\Local\Programs\Python\Python313"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path "$c\python.exe")) {
            return $c
        }
    }
    return $null
}

$basePython = Find-BasePython
if (-not $basePython) {
    Write-Error "Base Python 3.13 directory not found. Set BASE_PYTHON environment variable."
    exit 1
}
Write-Host "Using base Python from: $basePython"

Write-Host "Creating standalone Python directory: $stagePython"
if (Test-Path $stagePython) {
    Remove-Item -Recurse -Force $stagePython
}
New-Item -ItemType Directory -Force $stagePython | Out-Null

Write-Host "Copying base CPython binaries..."
Copy-Item "$basePython\python.exe" $stagePython
Copy-Item "$basePython\pythonw.exe" $stagePython
Copy-Item "$basePython\python3.dll" $stagePython
Copy-Item "$basePython\python313.dll" $stagePython
Copy-Item "$basePython\vcruntime140.dll" $stagePython
Copy-Item "$basePython\vcruntime140_1.dll" $stagePython

Write-Host "Copying DLLs..."
Copy-Item -Recurse "$basePython\DLLs" $stagePython

Write-Host "Copying Lib (stdlib only)..."
New-Item -ItemType Directory -Force "$stagePython\Lib" | Out-Null
Get-ChildItem "$basePython\Lib" -Exclude "site-packages" | ForEach-Object {
    Copy-Item -Recurse $_.FullName "$stagePython\Lib"
}
New-Item -ItemType Directory -Force "$stagePython\Lib\site-packages" | Out-Null

Write-Host "Installing locked runtime dependencies via uv..."
$pyExe = "$stagePython\python.exe"
$runtimeReqs = "$cleanRoot\requirements-runtime.lock.txt"
$dashboardReqs = "$cleanRoot\requirements-dashboard.in"

& uv pip install --python $pyExe -r $runtimeReqs -r $dashboardReqs --link-mode copy --no-cache

Write-Host "Verifying packaged Python isolation and imports..."
$verifyScript = @"
import sys
import os
print(f"Prefix: {sys.prefix}")
print(f"Executable: {sys.executable}")
assert os.path.normpath(sys.prefix) == os.path.normpath(r"$stagePython"), f"Prefix mismatch: {sys.prefix}"

import openpyxl
import pandas
import google.protobuf
import pyarrow
import yaml
import websockets
import xlrd
import fastapi
import starlette
import uvicorn
import fido2

print("ALL_PACKAGED_RUNTIME_DEPENDENCIES_LOADED_SUCCESSFULLY")
"@

$result = & $pyExe -c $verifyScript
Write-Host $result
if ($result -notmatch "ALL_PACKAGED_RUNTIME_DEPENDENCIES_LOADED_SUCCESSFULLY") {
    throw "Packaged Python verification failed!"
}

Write-Host "Packaged Python successfully built and validated."
