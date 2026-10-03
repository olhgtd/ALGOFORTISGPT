param(
    [string]$AppVersion="9.0.0",
    [switch]$RequireSignature,
    [string]$ExpectedPublisherSubject="",
    [string]$Publisher="",
    [string]$PublisherUrl="",
    [string]$WebView2Version="1.0.4258.31",
    [string]$ExpectedWebView2PackageSha256=""
)
$ErrorActionPreference="Stop"
$toolsDir=$PSScriptRoot
$root=(Resolve-Path "$toolsDir\..\..").Path
$installerDir=Join-Path $root "build\installer"
$stageDir=Join-Path $root "build\stage"
$brandMaster=Join-Path $root "assets\branding\AlgoFortis\AlgoFortis_Logo_Master.png"

function Find-ISCC {
    if($env:ISCC_PATH -and (Test-Path $env:ISCC_PATH)){return (Resolve-Path $env:ISCC_PATH).Path}
    $cmd=Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if($cmd){return $cmd.Source}
    foreach($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"),
        (Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "Inno Setup 6\ISCC.exe")
    )){if($candidate -and (Test-Path $candidate)){return $candidate}}
    return $null
}
function Find-SignTool {
    $cmd=Get-Command signtool.exe -ErrorAction SilentlyContinue
    if($cmd){return $cmd.Source}
    return $null
}
function Sign-Artifact {
    param([string]$Path,[string]$Label)
    if(-not $RequireSignature){Write-Warning "$Label is UNSIGNED (private qualification build)."; return ""}
    if(-not $env:SIGNTOOL_CERT_PATH -or -not(Test-Path $env:SIGNTOOL_CERT_PATH)){throw "$Label signing required but SIGNTOOL_CERT_PATH is not configured"}
    if(-not $env:SIGNTOOL_TIMESTAMP_URL){throw "SIGNED RELEASE requires SIGNTOOL_TIMESTAMP_URL"}
    $tool=Find-SignTool
    if(-not $tool){throw "signtool.exe is required"}
    $args=@("sign","/fd","SHA256","/f",$env:SIGNTOOL_CERT_PATH)
    if($env:SIGNTOOL_CERT_PASSWORD){$args+=@("/p",$env:SIGNTOOL_CERT_PASSWORD)}
    $args+=@("/tr",$env:SIGNTOOL_TIMESTAMP_URL,"/td","SHA256",$Path)
    & $tool @args
    if($LASTEXITCODE -ne 0){throw "$Label signing failed"}
    $sig=Get-AuthenticodeSignature $Path
    if($sig.Status -ne "Valid"){throw "$Label signature verification failed"}
    if($ExpectedPublisherSubject -and ([string]$sig.SignerCertificate.Subject -notlike "*$ExpectedPublisherSubject*")){throw "$Label signer subject mismatch"}
    return [string]$sig.SignerCertificate.Thumbprint
}

if(-not(Test-Path $brandMaster)){throw "Canonical fortress logo missing: $brandMaster"}
$iscc=Find-ISCC
if(-not $iscc){throw "Inno Setup compiler ISCC.exe not found"}
$effectivePublisher=if($Publisher){$Publisher}else{"AlgoFortis"}
$effectivePublisherUrl=if($PublisherUrl){$PublisherUrl}else{"https://example.invalid/algofortis"}
if($RequireSignature){
    if(-not $ExpectedPublisherSubject -or -not $Publisher -or -not $PublisherUrl){throw "SIGNED RELEASE requires explicit publisher identity, URL, and certificate subject"}
    if(-not $PublisherUrl.StartsWith("https://")){throw "SIGNED RELEASE PublisherUrl must use HTTPS"}
}
New-Item -ItemType Directory -Path $installerDir -Force | Out-Null

# The approved fortress master is authoritative for web logo + favicon during this build.
Copy-Item $brandMaster (Join-Path $root "dashboard\web\public\algofortis_logo.png") -Force
Copy-Item $brandMaster (Join-Path $root "dashboard\web\public\favicon.png") -Force
$npm=Get-Command npm.cmd -ErrorAction Stop
& $npm.Source "--prefix" "$root\dashboard\web" "ci"
if($LASTEXITCODE -ne 0){throw "dashboard npm ci failed"}
& $npm.Source "--prefix" "$root\dashboard\web" "run" "build"
if($LASTEXITCODE -ne 0){throw "dashboard build failed"}

$roles=@(
    @{Role="OWNER";AppName="AlgoFortis Owner";Launcher="AlgoFortisOwner.exe";Output="AlgoFortis-Owner-Setup";Subdir="Owner";AppId="{{EF3180F8-1F78-4E45-81A0-90F7337B207C}"},
    @{Role="USER";AppName="AlgoFortis User";Launcher="AlgoFortisUser.exe";Output="AlgoFortis-User-Setup";Subdir="User";AppId="{{412C7181-92E6-4315-A958-298F3ADF5BB3}"}
)
foreach($cfg in $roles){
    & powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\stage_role_app.ps1" -Role $cfg.Role -WebView2Version $WebView2Version -ExpectedWebView2PackageSha256 $ExpectedWebView2PackageSha256
    if($LASTEXITCODE -ne 0){throw "$($cfg.Role) staging failed"}
    $launcherPath=Join-Path $stageDir $cfg.Launcher
    $launcherThumb=Sign-Artifact $launcherPath $cfg.Launcher

    $args=@(
      "/F$($cfg.Output)",
      ('/DMyAppName="{0}"' -f $cfg.AppName),
      ('/DMyAppVersion="{0}"' -f $AppVersion),
      ('/DMyAppPublisher="{0}"' -f $effectivePublisher),
      ('/DMyAppURL="{0}"' -f $effectivePublisherUrl),
      ('/DMyAppId="{0}"' -f $cfg.AppId),
      ('/DMyAppExeName="{0}"' -f $cfg.Launcher),
      ('/DMyInstallSubdir="{0}"' -f $cfg.Subdir),
      ('/DMyOutputBaseFilename="{0}"' -f $cfg.Output),
      ('/DMyStageDir="{0}"' -f $stageDir),
      ('/DMySetupIconFile="{0}"' -f (Join-Path $stageDir "algofortis.ico")),
      "$toolsDir\algofortis_role_installer.iss"
    )
    & $iscc @args
    if($LASTEXITCODE -ne 0){throw "$($cfg.Role) installer compilation failed"}
    $setup=Join-Path $installerDir "$($cfg.Output).exe"
    if(-not(Test-Path $setup)){throw "Missing installer: $setup"}
    $installerThumb=Sign-Artifact $setup "$($cfg.Output).exe"
    [ordered]@{
      schema="AlgoFortisRoleInstallerEvidence/v1"
      app_role=$cfg.Role
      artifact=(Split-Path $setup -Leaf)
      app_version=$AppVersion
      sha256=(Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant()
      size_bytes=(Get-Item $setup).Length
      launcher=$cfg.Launcher
      launcher_sha256=(Get-FileHash $launcherPath -Algorithm SHA256).Hash.ToLowerInvariant()
      canonical_brand_source="assets/branding/AlgoFortis/AlgoFortis_Logo_Master.png"
      canonical_brand_sha256=(Get-FileHash $brandMaster -Algorithm SHA256).Hash.ToLowerInvariant()
      launcher_signer_thumbprint=[string]$launcherThumb
      installer_signer_thumbprint=[string]$installerThumb
      require_signature=[bool]$RequireSignature
      live_state="READ_ONLY/DISARMED"
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 "$setup.evidence.json"
    Write-Host "BUILT_ROLE_INSTALLER=$setup"
}
Write-Host "OWNER_USER_SPLIT=PASS"
Write-Host "CANONICAL_FORTRESS_BRAND=PASS"
Write-Host "LIVE_STATE=READ_ONLY/DISARMED"
