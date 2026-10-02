$ErrorActionPreference = "Stop"

$toolsDir = $PSScriptRoot
$root = (Resolve-Path "$toolsDir\..\..").Path
$stage = Join-Path $root "build\stage"
$r1 = Join-Path $stage "Microsoft.Web.WebView2.Core.dll"
$r2 = Join-Path $stage "Microsoft.Web.WebView2.WinForms.dll"
$ico = Join-Path $root "algofortis.ico"
$cs = Join-Path $toolsDir "AlgoFortisLauncher.cs"
$out = Join-Path $stage "AlgoFortis.exe"

foreach ($required in @($r1, $r2, $ico, $cs)) {
    if (-not (Test-Path $required)) {
        throw "Launcher build input missing: $required"
    }
}

Write-Host "Compiling unsigned AlgoFortis.exe to $out (x64)..."
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    $resolved = Get-Command "csc.exe" -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "C# compiler not found."
    }
    $csc = $resolved.Source
}

$args = @(
    "/nologo",
    "/target:winexe",
    "/platform:x64",
    "/optimize+",
    "/win32icon:$ico",
    "/r:$r1",
    "/r:$r2",
    "/r:System.Windows.Forms.dll",
    "/r:System.Drawing.dll",
    "/out:$out",
    $cs
)
& $csc @args
if ($LASTEXITCODE -ne 0) {
    throw "AlgoFortis launcher compilation failed with code $LASTEXITCODE"
}
if (-not (Test-Path $out)) {
    throw "Launcher compiler reported success but output is missing: $out"
}

$signature = Get-AuthenticodeSignature -FilePath $out
if ($signature.Status -eq "Valid") {
    throw "Launcher unexpectedly arrived pre-signed. Signing authority belongs only to build_installer.ps1."
}

Write-Host "LAUNCHER_COMPILE=PASS"
Write-Host "LAUNCHER_SIGNING_STATE=UNSIGNED_EXPECTED"
Get-Item $out | Select-Object Name, Length
