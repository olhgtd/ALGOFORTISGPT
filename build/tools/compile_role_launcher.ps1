param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("OWNER","USER")]
    [string]$Role
)
$ErrorActionPreference="Stop"
$toolsDir=$PSScriptRoot
$root=(Resolve-Path "$toolsDir\..\..").Path
$stage=Join-Path $root "build\stage"
$r1=Join-Path $stage "Microsoft.Web.WebView2.Core.dll"
$r2=Join-Path $stage "Microsoft.Web.WebView2.WinForms.dll"
$ico=Join-Path $stage "algofortis.ico"
$cs=Join-Path $toolsDir "AlgoFortisLauncher.cs"
if ($Role -eq "OWNER") { $outName="AlgoFortisOwner.exe"; $define="OWNER_APP" }
else { $outName="AlgoFortisUser.exe"; $define="USER_APP" }
$out=Join-Path $stage $outName
foreach($required in @($r1,$r2,$ico,$cs)){if(-not(Test-Path $required)){throw "Role launcher input missing: $required"}}
$csc="C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if(-not(Test-Path $csc)){ $resolved=Get-Command csc.exe -ErrorAction SilentlyContinue; if(-not $resolved){throw "C# compiler not found"}; $csc=$resolved.Source }
$args=@("/nologo","/target:winexe","/platform:x64","/optimize+","/define:$define","/win32icon:$ico","/r:$r1","/r:$r2","/r:System.Windows.Forms.dll","/r:System.Drawing.dll","/out:$out",$cs)
& $csc @args
if($LASTEXITCODE -ne 0){throw "$outName compilation failed with code $LASTEXITCODE"}
if(-not(Test-Path $out)){throw "$outName missing after compilation"}
if((Get-AuthenticodeSignature $out).Status -eq "Valid"){throw "$outName unexpectedly arrived pre-signed"}
Write-Host "ROLE_LAUNCHER_COMPILE=PASS"
Write-Host "ROLE=$Role"
Write-Host "LAUNCHER=$outName"
