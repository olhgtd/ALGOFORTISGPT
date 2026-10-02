param(
    [ValidateSet("QUALIFICATION", "PRODUCTION")]
    [string]$ReleaseEnvironment = "QUALIFICATION",
    [string]$OutputBaseFilename = "AlgoFortis-Setup-Qualification",
    [string]$AppVersion = "0.0.0-qualification",
    [string]$Publisher = "PENDING_EXTERNAL",
    [string]$CanonicalUrl = "PENDING_EXTERNAL"
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$installerDir = "$cleanRoot\build\installer"
$stageDir = "$cleanRoot\build\stage"

function Find-ISCC {
    if ($env:ISCC_PATH -and (Test-Path $env:ISCC_PATH)) {
        return $env:ISCC_PATH
    }
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"),
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) { return $cand }
    }
    return $null
}

function Assert-ProductionReleaseInputs {
    if ($Publisher -eq "PENDING_EXTERNAL" -or [string]::IsNullOrWhiteSpace($Publisher)) {
        throw "Production release requires finalized publisher identity."
    }
    if ($CanonicalUrl -eq "PENDING_EXTERNAL" -or [string]::IsNullOrWhiteSpace($CanonicalUrl)) {
        throw "Production release requires finalized canonical URL."
    }
    if ($CanonicalUrl -notmatch '^https://') {
        throw "Production release requires finalized canonical URL using HTTPS."
    }
    if ($AppVersion -eq "0.0.0-qualification") {
        throw "Production release requires an explicit SemVer release version."
    }
    if (-not $env:SIGNTOOL_CERT_PATH -or -not (Test-Path $env:SIGNTOOL_CERT_PATH)) {
        throw "Production release requires Authenticode signing credentials."
    }
    if (-not $env:SIGNTOOL_TIMESTAMP_URL) {
        throw "Production release requires Authenticode RFC3161 timestamp authority."
    }
}

function Invoke-AuthenticodeSignAndVerify([string]$Path) {
    if (-not (Get-Command "signtool.exe" -ErrorAction SilentlyContinue)) {
        throw "Production release requires Authenticode signtool.exe."
    }
    $args = @("sign", "/fd", "SHA256", "/f", $env:SIGNTOOL_CERT_PATH)
    if ($env:SIGNTOOL_CERT_PASSWORD) {
        $args += @("/p", $env:SIGNTOOL_CERT_PASSWORD)
    }
    $args += @("/tr", $env:SIGNTOOL_TIMESTAMP_URL, "/td", "SHA256", $Path)
    & signtool.exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed for $Path with exit code $LASTEXITCODE"
    }

    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status -ne "Valid") {
        throw "Production release requires Authenticode status Valid for $Path; got $($signature.Status)."
    }
    if (-not $signature.TimeStamperCertificate) {
        throw "Production release requires Authenticode RFC3161 timestamp for $Path."
    }
}

if ($ReleaseEnvironment -eq "PRODUCTION") {
    Assert-ProductionReleaseInputs
    Write-Host "=== BUILDING ALGOFORTIS PRODUCTION RELEASE PACKAGE ==="
} else {
    if ($Publisher -eq "PENDING_EXTERNAL") { $Publisher = "AlgoFortis Qualification Build" }
    if ($CanonicalUrl -eq "PENDING_EXTERNAL") { $CanonicalUrl = "https://qualification.invalid" }
    Write-Host "=== QUALIFICATION BUILD — NOT FOR PRODUCTION — READ_ONLY/DISARMED ==="
}

if (-not (Test-Path $installerDir)) {
    New-Item -ItemType Directory -Path $installerDir -Force | Out-Null
}
$targetExe = Join-Path $installerDir "$OutputBaseFilename.exe"
if (Test-Path $targetExe) {
    Remove-Item -Path $targetExe -Force
}

Write-Host "Staging application..."
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\stage_app.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Staging failed with code $LASTEXITCODE"
}

$launcherPath = Join-Path $stageDir "AlgoFortis.exe"
if ($ReleaseEnvironment -eq "PRODUCTION") {
    if (-not (Test-Path $launcherPath)) { throw "Staged AlgoFortis.exe is missing." }
    Invoke-AuthenticodeSignAndVerify $launcherPath
}

$isccPath = Find-ISCC
if (-not $isccPath) {
    throw "Inno Setup compiler (ISCC.exe) not found in PATH or standard Program Files locations."
}

$quote = '"'
$defines = @(
    ("/DMyAppVersion=" + $quote + $AppVersion + $quote),
    ("/DMyAppPublisher=" + $quote + $Publisher + $quote),
    ("/DMyAppURL=" + $quote + $CanonicalUrl + $quote),
    ("/DReleaseEnvironment=" + $quote + $ReleaseEnvironment + $quote)
)
Write-Host "Compiling $ReleaseEnvironment installer via ISCC..."
& $isccPath @defines "/F$OutputBaseFilename" "$toolsDir\algofortis_installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with code $LASTEXITCODE"
}
if (-not (Test-Path $targetExe)) {
    throw "Expected installer '$OutputBaseFilename.exe' was not created in $installerDir"
}

if ($ReleaseEnvironment -eq "PRODUCTION") {
    Invoke-AuthenticodeSignAndVerify $targetExe
    Write-Host "=== ALGOFORTIS PRODUCTION RELEASE PACKAGE: SIGNED AND VERIFIED ==="
} else {
    Write-Host "QUALIFICATION BUILD complete; production publisher/domain/signing gates remain external blockers."
    Write-Host "LIVE_STATE=READ_ONLY/DISARMED"
}
