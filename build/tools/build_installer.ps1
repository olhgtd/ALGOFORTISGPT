param(
    [string]$OutputBaseFilename = "AlgoFortis-Setup",
    [string]$AppVersion = "9.0.0",
    [switch]$RequireSignature,
    [string]$ExpectedPublisherSubject = "",
    [string]$Publisher = "",
    [string]$PublisherUrl = "",
    [string]$WebView2Version = "1.0.4258.31",
    [string]$ExpectedWebView2PackageSha256 = "",
    [string]$WebView2BootstrapperPath = "",
    [string]$ExpectedWebView2BootstrapperSha256 = ""
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$cleanRoot = (Resolve-Path "$toolsDir\..\..").Path
$installerDir = "$cleanRoot\build\installer"
$stageDir = "$cleanRoot\build\stage"
$evidenceDir = "$cleanRoot\build\evidence"
$dashboardLock = "$cleanRoot\requirements-dashboard.lock.txt"

function Find-ISCC {
    if ($env:ISCC_PATH -and (Test-Path $env:ISCC_PATH)) {
        return (Resolve-Path $env:ISCC_PATH).Path
    }
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
    $programFiles = [Environment]::GetFolderPath("ProgramFiles")
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"),
        (Join-Path $programFiles "Inno Setup 6\ISCC.exe")
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
        return ""
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

    $thumbprint = [string]$signature.SignerCertificate.Thumbprint
    if (-not $thumbprint) {
        throw "$Label Authenticode signer thumbprint is unavailable."
    }
    Write-Host "$Label Authenticode signature VERIFIED: $thumbprint"
    return $thumbprint
}

function Require-HexSha256 {
    param([string]$Value, [string]$Label)
    if ($Value -notmatch '^[0-9A-Fa-f]{64}$') {
        throw "$Label must be an exact 64-character SHA-256 value."
    }
}

if (-not (Test-Path $dashboardLock)) {
    throw "requirements-dashboard.lock.txt is required for release packaging."
}

$isccPath = Find-ISCC
if (-not $isccPath) {
    throw "Inno Setup compiler (ISCC.exe) not found in PATH or standard install locations."
}

$effectivePublisher = if ($Publisher) { $Publisher } else { "AlgoFortis" }
$effectivePublisherUrl = if ($PublisherUrl) { $PublisherUrl } else { "https://app.algofortis.com" }

$bootstrapperResolved = ""
$bootstrapperSha = ""
if ($WebView2BootstrapperPath) {
    if (-not (Test-Path $WebView2BootstrapperPath)) {
        throw "WebView2 bootstrapper not found: $WebView2BootstrapperPath"
    }
    $bootstrapperResolved = (Resolve-Path $WebView2BootstrapperPath).Path
    $bootstrapperSha = (Get-FileHash -Algorithm SHA256 -Path $bootstrapperResolved).Hash.ToLowerInvariant()
    if ($ExpectedWebView2BootstrapperSha256) {
        Require-HexSha256 $ExpectedWebView2BootstrapperSha256 "ExpectedWebView2BootstrapperSha256"
        if ($bootstrapperSha -ne $ExpectedWebView2BootstrapperSha256.ToLowerInvariant()) {
            throw "WebView2 bootstrapper SHA-256 mismatch."
        }
    }
}

if ($RequireSignature) {
    if (-not $ExpectedPublisherSubject -or -not $Publisher -or -not $PublisherUrl) {
        throw "SIGNED RELEASE requires explicit publisher identity, publisher URL, and certificate subject. OD-V2-23 production identity cannot be inferred."
    }
    if (-not ([Uri]::IsWellFormedUriString($PublisherUrl, [UriKind]::Absolute)) -or -not $PublisherUrl.StartsWith("https://")) {
        throw "SIGNED RELEASE PublisherUrl must be an absolute HTTPS URL."
    }
    if (-not $ExpectedWebView2PackageSha256) {
        throw "SIGNED RELEASE requires the pinned Microsoft.Web.WebView2 NuGet SHA-256."
    }
    Require-HexSha256 $ExpectedWebView2PackageSha256 "ExpectedWebView2PackageSha256"
    if (-not $bootstrapperResolved -or -not $ExpectedWebView2BootstrapperSha256) {
        throw "SIGNED RELEASE requires a WebView2 bootstrapper plus its pinned SHA-256."
    }
    Require-HexSha256 $ExpectedWebView2BootstrapperSha256 "ExpectedWebView2BootstrapperSha256"
}

$buildKind = if ($RequireSignature) { "SIGNED RELEASE" } else { "DEVELOPMENT / QUALIFICATION" }
Write-Host "=== BUILDING ALGOFORTIS $buildKind INSTALLER ==="

New-Item -ItemType Directory -Path $installerDir -Force | Out-Null
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
$targetExe = Join-Path $installerDir "$OutputBaseFilename.exe"
if (Test-Path $targetExe) {
    Remove-Item -Path $targetExe -Force
}

$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
if (-not $npm) {
    $npm = Get-Command "npm" -ErrorAction SilentlyContinue
}
if (-not $npm) {
    throw "npm is required to build the dashboard production assets."
}

Write-Host "Building dashboard production assets from package-lock..."
& $npm.Source "--prefix" "$cleanRoot\dashboard\web" "ci"
if ($LASTEXITCODE -ne 0) {
    throw "dashboard npm ci failed with code $LASTEXITCODE"
}
& $npm.Source "--prefix" "$cleanRoot\dashboard\web" "run" "build"
if ($LASTEXITCODE -ne 0) {
    throw "dashboard production build failed with code $LASTEXITCODE"
}

Write-Host "Staging application from clean inputs..."
$stageArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "$toolsDir\stage_app.ps1",
    "-WebView2Version", $WebView2Version
)
if ($ExpectedWebView2PackageSha256) {
    $stageArgs += @("-ExpectedWebView2PackageSha256", $ExpectedWebView2PackageSha256)
}
& powershell.exe @stageArgs
if ($LASTEXITCODE -ne 0) {
    throw "Staging failed with code $LASTEXITCODE"
}

$stagePython = Join-Path $stageDir "runtime\python\python.exe"
$stageEvidencePath = Join-Path $evidenceDir "stage-evidence.json"
& $stagePython "$toolsDir\stage_fingerprint.py" --stage $stageDir --output $stageEvidencePath
if ($LASTEXITCODE -ne 0) {
    throw "Pre-sign stage fingerprint failed with code $LASTEXITCODE"
}
$stageEvidence = Get-Content $stageEvidencePath -Raw | ConvertFrom-Json

$launcherPath = Join-Path $stageDir "AlgoFortis.exe"
if (-not (Test-Path $launcherPath)) {
    throw "Expected staged launcher not found: $launcherPath"
}
$launcherPreSignSha = (Get-FileHash -Algorithm SHA256 -Path $launcherPath).Hash.ToLowerInvariant()
$launcherSignerThumbprint = Invoke-AuthenticodeSign -Path $launcherPath -Label "AlgoFortis.exe"
$launcherSigned = [bool]$launcherSignerThumbprint
$launcherFinalSha = (Get-FileHash -Algorithm SHA256 -Path $launcherPath).Hash.ToLowerInvariant()

$isccArgs = @(
    "/F$OutputBaseFilename",
    ('/DMyAppVersion="{0}"' -f $AppVersion),
    ('/DMyAppPublisher="{0}"' -f $effectivePublisher),
    ('/DMyAppURL="{0}"' -f $effectivePublisherUrl)
)
if ($bootstrapperResolved) {
    $isccArgs += ('/DWebViewBootstrapperPath="{0}"' -f $bootstrapperResolved)
}
$isccArgs += "$toolsDir\algofortis_installer.iss"

Write-Host "Compiling installer via ISCC: $OutputBaseFilename.exe"
& $isccPath @isccArgs
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with code $LASTEXITCODE"
}

$setupExePath = Join-Path $installerDir "$OutputBaseFilename.exe"
if (-not (Test-Path $setupExePath)) {
    throw "Expected installer was not created: $setupExePath"
}
$installerSignerThumbprint = Invoke-AuthenticodeSign -Path $setupExePath -Label "$OutputBaseFilename.exe"
$installerSigned = [bool]$installerSignerThumbprint

if ($RequireSignature -and (-not $launcherSigned -or -not $installerSigned)) {
    throw "SIGNED RELEASE cannot continue without valid launcher and installer signatures."
}

$hash = Get-FileHash -Algorithm SHA256 -Path $setupExePath
$artifact = Get-Item $setupExePath
$webViewEvidencePath = Join-Path $evidenceDir "webview2-input.json"
$webViewEvidence = if (Test-Path $webViewEvidencePath) {
    Get-Content $webViewEvidencePath -Raw | ConvertFrom-Json
} else {
    $null
}

$manifest = [ordered]@{
    schema = "AlgoFortisReleaseArtifactEvidence/v1"
    artifact = $artifact.Name
    app_version = $AppVersion
    publisher = $effectivePublisher
    publisher_url = $effectivePublisherUrl
    size_bytes = $artifact.Length
    sha256 = $hash.Hash.ToLowerInvariant()
    pre_sign_stage_fingerprint = [string]$stageEvidence.reproducible_payload_fingerprint_sha256
    pre_sign_stage_all_files_fingerprint = [string]$stageEvidence.all_files_fingerprint_sha256
    launcher_pre_sign_sha256 = $launcherPreSignSha
    launcher_final_sha256 = $launcherFinalSha
    launcher_authenticode_verified = [bool]$launcherSigned
    launcher_signer_thumbprint = [string]$launcherSignerThumbprint
    installer_authenticode_verified = [bool]$installerSigned
    installer_signer_thumbprint = [string]$installerSignerThumbprint
    require_signature = [bool]$RequireSignature
    expected_publisher_subject = $ExpectedPublisherSubject
    dashboard_dependency_lock = "requirements-dashboard.lock.txt"
    webview2_package_version = [string]$webViewEvidence.version
    webview2_package_sha256 = [string]$webViewEvidence.package_sha256
    webview2_bootstrapper_sha256 = $bootstrapperSha
}
$manifestPath = "$setupExePath.evidence.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $manifestPath

Write-Host "Artifact evidence: $manifestPath"
Write-Host "REPRODUCIBLE_PAYLOAD_FINGERPRINT=$($stageEvidence.reproducible_payload_fingerprint_sha256)"
if ($RequireSignature) {
    Write-Host "=== ALGOFORTIS SIGNED RELEASE PACKAGE: VERIFIED ==="
} else {
    Write-Host "=== ALGOFORTIS DEVELOPMENT / QUALIFICATION PACKAGE: BUILT (NOT RELEASE-QUALIFIED) ==="
}
