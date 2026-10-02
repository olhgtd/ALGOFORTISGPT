param(
    [string]$Version = "1.0.4258.31",
    [string]$ExpectedPackageSha256 = ""
)

$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$root = (Resolve-Path "$toolsDir\..\..").Path
$stage = Join-Path $root "build\stage"
$cache = Join-Path $root "build\cache\webview2"
New-Item -ItemType Directory -Force $stage | Out-Null
New-Item -ItemType Directory -Force $cache | Out-Null

$lowerVersion = $Version.ToLowerInvariant()
$package = Join-Path $cache "microsoft.web.webview2.$lowerVersion.nupkg"
$extract = Join-Path $cache "microsoft.web.webview2.$lowerVersion"
$url = "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$lowerVersion/microsoft.web.webview2.$lowerVersion.nupkg"

if (-not (Test-Path $package)) {
    Write-Host "Downloading pinned Microsoft.Web.WebView2 $Version..."
    Invoke-WebRequest -Uri $url -OutFile $package -UseBasicParsing
}

$actualSha = (Get-FileHash -Algorithm SHA256 -Path $package).Hash.ToLowerInvariant()
if ($ExpectedPackageSha256) {
    $expected = $ExpectedPackageSha256.Trim().ToLowerInvariant()
    if ($actualSha -ne $expected) {
        throw "WebView2 NuGet SHA-256 mismatch. Expected $expected; got $actualSha"
    }
}

if (Test-Path $extract) {
    Remove-Item -Recurse -Force $extract
}
New-Item -ItemType Directory -Force $extract | Out-Null

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($package, $extract)

$coreCandidates = @(
    (Join-Path $extract "lib\net462\Microsoft.Web.WebView2.Core.dll"),
    (Join-Path $extract "lib\net45\Microsoft.Web.WebView2.Core.dll")
)
$formsCandidates = @(
    (Join-Path $extract "lib\net462\Microsoft.Web.WebView2.WinForms.dll"),
    (Join-Path $extract "lib\net45\Microsoft.Web.WebView2.WinForms.dll")
)
$loaderCandidates = @(
    (Join-Path $extract "runtimes\win-x64\native\WebView2Loader.dll"),
    (Join-Path $extract "build\native\x64\WebView2Loader.dll")
)

function Resolve-FirstExisting([string[]]$Candidates, [string]$Label) {
    foreach ($candidate in $Candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "$Label not found in Microsoft.Web.WebView2 $Version package."
}

$core = Resolve-FirstExisting $coreCandidates "Microsoft.Web.WebView2.Core.dll"
$forms = Resolve-FirstExisting $formsCandidates "Microsoft.Web.WebView2.WinForms.dll"
$loader = Resolve-FirstExisting $loaderCandidates "WebView2Loader.dll"

Copy-Item $core (Join-Path $stage "Microsoft.Web.WebView2.Core.dll") -Force
Copy-Item $forms (Join-Path $stage "Microsoft.Web.WebView2.WinForms.dll") -Force
Copy-Item $loader (Join-Path $stage "WebView2Loader.dll") -Force

$evidenceDir = Join-Path $root "build\evidence"
New-Item -ItemType Directory -Force $evidenceDir | Out-Null
$evidence = [ordered]@{
    schema = "AlgoFortisWebView2Input/v1"
    package = "Microsoft.Web.WebView2"
    version = $Version
    package_sha256 = $actualSha
    source_url = $url
    expected_sha256_enforced = [bool]$ExpectedPackageSha256
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $evidenceDir "webview2-input.json")

Write-Host "WEBVIEW2_VERSION=$Version"
Write-Host "WEBVIEW2_PACKAGE_SHA256=$actualSha"
Write-Host "WEBVIEW2_STAGE=PASS"
