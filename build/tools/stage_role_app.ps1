param(
    [Parameter(Mandatory=$true)][ValidateSet("OWNER","USER")][string]$Role,
    [string]$WebView2Version="1.0.4258.31",
    [string]$ExpectedWebView2PackageSha256=""
)
$ErrorActionPreference="Stop"
$toolsDir=$PSScriptRoot
$root=(Resolve-Path "$toolsDir\..\..").Path
$stage=Join-Path $root "build\stage"
$brandSource=if($Role -eq "OWNER"){
    Join-Path $root "assets\branding\AlgoFortis\AlgoFortis_Owner_Logo.png"
}else{
    Join-Path $root "assets\branding\AlgoFortis\AlgoFortis_User_Logo.png"
}
$args=@("-ExecutionPolicy","Bypass","-File","$toolsDir\stage_app.ps1","-WebView2Version",$WebView2Version)
if($ExpectedWebView2PackageSha256){$args+=@("-ExpectedWebView2PackageSha256",$ExpectedWebView2PackageSha256)}
& powershell.exe @args
if($LASTEXITCODE -ne 0){throw "Base stage failed with code $LASTEXITCODE"}
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\generate_brand_assets.ps1" -SourceImage $brandSource -OutputDir $stage
if($LASTEXITCODE -ne 0){throw "$Role brand staging failed"}
$dist=Join-Path $stage "dashboard\web\dist"
if(-not(Test-Path $dist)){throw "Built dashboard dist missing: $dist"}
Copy-Item $brandSource (Join-Path $dist "algofortis_logo.png") -Force
Copy-Item $brandSource (Join-Path $dist "favicon.png") -Force
& powershell.exe -ExecutionPolicy Bypass -File "$toolsDir\compile_role_launcher.ps1" -Role $Role
if($LASTEXITCODE -ne 0){throw "$Role role launcher compilation failed"}
$launcher=if($Role -eq "OWNER"){"AlgoFortisOwner.exe"}else{"AlgoFortisUser.exe"}
foreach($required in @((Join-Path $stage $launcher),(Join-Path $stage "algofortis_logo.png"),(Join-Path $stage "algofortis.ico"),(Join-Path $stage "runtime\python\python.exe"),(Join-Path $stage "dashboard\web\dist\index.html"))){if(-not(Test-Path $required)){throw "Role stage incomplete: $required"}}
Write-Host "ROLE_STAGE=PASS"
Write-Host "ROLE_STAGE_ROLE=$Role"
Write-Host "ROLE_STAGE_LAUNCHER=$launcher"
Write-Host "ROLE_STAGE_BRAND=$Role"
Write-Host "LIVE_STATE=READ_ONLY/DISARMED"
