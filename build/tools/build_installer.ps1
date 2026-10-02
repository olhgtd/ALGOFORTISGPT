param(
    [string]$OutputBaseFilename = "AlgoFortis-Setup",
    [switch]$RequireSignature,
    [string]$ExpectedPublisherSubject = ""
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
    if ($cmd) {
        return $cmd.Source
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) {
            return $cand
        }
    }
    return $null
}

function Find-SignTool {
    $cmd = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

function Invoke-AuthenticodeSign {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Label
    )

    $certConfigured = $env:SIGNTOOL_CERT_PATH -and (Test-Path $env:SIGNTOOL_CERT_PATH)
    if (-not $certConfigured) {
        if ($RequireSignature) {
            throw "$Label signing required but SIGNTOOL_CERT_PATH is not configured."
        }
        Write-Warning "$Label is UNSIGNED (development/qualification build only)."
        return $false
    }

    $signTool = Find-SignTool
    if (-not $signTool) {
        throw "signtool.exe is required when a signing certificate is configured."
    }
    if ($RequireSignature -and -not $env:SIGNTOOL_TIMESTAMP_URL) {
        throw "SIGNED RELEASE requires SIGNTOOL_TIMESTAMP_URL."
    }

    $args = @("sign", "/fd", "SHA256", "/f", $env:SIGNTOOL_CERT_PATH)
    if ($env:SIGNTOOL_CERT_PASSWORD) {
        $args += @("/p", $env:SIGNTOOL_CERT_PASSWORD)
    }
    if ($env:SIGNTOOL_TIMESTAMP_URL) {
        $args += @("/tr", $env:SIGNTOOL_TIMESTAMP_URL, "/td", "SHA256")
    }
    $args += $Path

    & $signTool @args
    if ($LASTEXITCODE -ne 0) {
        throw "$Label Authenticode signing failed with exit code $LASTEXITCODE."
    }

    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status -ne "Valid") {
        throw "$Label Authenticode verification failed: $($signature.Status) $($signature.StatusMessage)"
    }
    if ($ExpectedPublisherSubject) {
        $subject = [string]$signature.SignerCertificate.Subject
        if ($subject -notlike "*$ExpectedPublisherSubject*") {
            throw "$Label signer subject '$subject' does not match expected publisher '$ExpectedPublisherSubject'."
        }
    }

    Write-Host "$Label Authenticode signature VERIFIED."
    return $true
}

$isccPath = Find-ISCC
if (-not $isccPath) {
    throw "Inno Setup compiler (ISCC.exe) not found in PATH or standard install locations."
}

$buildKind = if ($RequireSignature) { "SIGNED RELEASE" } else { "DEVELOPMENT / QUALIFICATION" }
Write-Host "=== BUILDING ALGOFORTIS $buildKind INSTALLER ==="

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
if (-not (Test-Path $launcherPath)) {
    throw "Expected staged launcher not found: $launcherPath"
}
$launcherSigned = Invoke-AuthenticodeSign -Path $launcherPath -Label "AlgoFortis.exe"

Write-Host "Compiling installer via ISCC: $OutputBaseFilename.exe"
& $isccPath "/F$OutputBaseFilename" "$toolsDir\algofortis_installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with code $LASTEXITCODE"
}

$setupExePath = Join-Path $installerDir "$OutputBaseFilename.exe"
if (-not (Test-Path $setupExePath)) {
    throw "Expected installer was not created: $setupExePath"
}
$installerSigned = Invoke-AuthenticodeSign -Path $setupExePath -Label "$OutputBaseFilename.exe"

if ($RequireSignature -and (-not $launcherSigned -or -not $installerSigned)) {
    throw "SIGNED RELEASE cannot continue without valid launcher and installer signatures."
}

$hash = Get-FileHash -Algorithm SHA256 -Path $setupExePath
$artifact = Get-Item $setupExePath
$manifest = [ordered]@{
    schema = "AlgoFortisReleaseArtifactEvidence/v1"
    artifact = $artifact.Name
    size_bytes = $artifact.Length
    sha256 = $hash.Hash.ToLowerInvariant()
    launcher_authenticode_verified = [bool]$launcherSigned
    installer_authenticode_verified = [bool]$installerSigned
    require_signature = [bool]$RequireSignature
    expected_publisher_subject = $ExpectedPublisherSubject
}
$manifestPath = "$setupExePath.evidence.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $manifestPath

Write-Host "Artifact evidence: $manifestPath"
if ($RequireSignature) {
    Write-Host "=== ALGOFORTIS SIGNED RELEASE PACKAGE: VERIFIED ==="
} else {
    Write-Host "=== ALGOFORTIS DEVELOPMENT / QUALIFICATION PACKAGE: BUILT (NOT RELEASE-QUALIFIED) ==="
}
