$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$installerDir = "$cleanRoot\build\installer"

function Find-ISCC {
    if ($env:ISCC_PATH -and (Test-Path $env:ISCC_PATH)) {
        return $env:ISCC_PATH
    }
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "C:\Users\Ragini Music\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) {
            return $cand
        }
    }
    return $null
}

$isccPath = Find-ISCC

Write-Host "=== BUILDING ALGOFORTIS PRODUCTION INSTALLER ==="

# 1. Clean installer output directory
if (Test-Path $installerDir) {
    Write-Host "Cleaning installer directory $installerDir..."
    Get-ChildItem -Path $installerDir -Filter "*.exe" | Remove-Item -Force
} else {
    New-Item -ItemType Directory -Path $installerDir -Force | Out-Null
}

# 2. Stage core product
Write-Host "Staging application..."
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\stage_app.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Staging failed with code $LASTEXITCODE"
    exit 1
}

# 3. Compile Inno Setup package
Write-Host "Compiling AlgoFortis installer via ISCC..."
if (-not $isccPath) {
    Write-Error "Inno Setup compiler (ISCC.exe) not found in PATH or standard Program Files locations."
    exit 1
}
Write-Host "Using Inno Setup compiler: $isccPath"

& $isccPath "$toolsDir\algofortis_installer.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup compilation failed with code $LASTEXITCODE"
    exit 1
}

# 4. Verify output & apply optional Authenticode signature
$installers = @(Get-ChildItem -Path $installerDir -Filter "*.exe")
Write-Host "Installer directory contents:"
$installers | ForEach-Object { Write-Host "  - $($_.Name) ($($_.Length) bytes)" }

if ($installers.Count -ne 1 -or $installers[0].Name -ne "AlgoFortis-Setup.exe") {
    Write-Error "Expected exactly ONE installer 'AlgoFortis-Setup.exe', found $($installers.Count) items"
    exit 1
}

$setupExePath = $installers[0].FullName

# Optional Authenticode code signing if certificate environment variable is configured
if ($env:SIGNTOOL_CERT_PATH -and (Test-Path $env:SIGNTOOL_CERT_PATH)) {
    Write-Host "Signing $setupExePath with Authenticode certificate..."
    $signtoolArgs = @("sign", "/fd", "SHA256", "/f", $env:SIGNTOOL_CERT_PATH)
    if ($env:SIGNTOOL_CERT_PASSWORD) {
        $signtoolArgs += @("/p", $env:SIGNTOOL_CERT_PASSWORD)
    }
    if ($env:SIGNTOOL_TIMESTAMP_URL) {
        $signtoolArgs += @("/tr", $env:SIGNTOOL_TIMESTAMP_URL, "/td", "SHA256")
    }
    $signtoolArgs += $setupExePath
    & signtool.exe @signtoolArgs
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Authenticode signing succeeded for AlgoFortis-Setup.exe"
    } else {
        Write-Warning "Authenticode signing failed with exit code $LASTEXITCODE"
    }
}

Write-Host "=== ALGOFORTIS PRODUCTION INSTALLER BUILD: SUCCESS ==="
