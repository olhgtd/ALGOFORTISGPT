$ErrorActionPreference = "Stop"
$toolsDir = $PSScriptRoot
$root = (Resolve-Path "$toolsDir\..\..").Path
$stage = Join-Path $root "build\stage"
$r1 = Join-Path $stage "Microsoft.Web.WebView2.Core.dll"
$r2 = Join-Path $stage "Microsoft.Web.WebView2.WinForms.dll"
$ico = Join-Path $root "algofortis.ico"
if (-not (Test-Path $ico)) {
    $ico = Join-Path $root "sentinelx.ico"
}
$cs = Join-Path $toolsDir "AlgoFortisLauncher.cs"
$out = Join-Path $stage "AlgoFortis.exe"

Write-Host "Compiling AlgoFortis.exe to $out (x64) ..."
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    $csc = "csc.exe"
}
& $csc /target:winexe /platform:x64 "/win32icon:$ico" "/r:$r1" "/r:$r2" /r:System.Windows.Forms.dll /r:System.Drawing.dll "/out:$out" "$cs"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Compilation SUCCESS: AlgoFortis.exe"
    
    # Optional Authenticode code signing if certificate environment variable is configured
    if ($env:SIGNTOOL_CERT_PATH -and (Test-Path $env:SIGNTOOL_CERT_PATH)) {
        Write-Host "Signing $out with Authenticode certificate..."
        $signtoolArgs = @("sign", "/fd", "SHA256", "/f", $env:SIGNTOOL_CERT_PATH)
        if ($env:SIGNTOOL_CERT_PASSWORD) {
            $signtoolArgs += @("/p", $env:SIGNTOOL_CERT_PASSWORD)
        }
        if ($env:SIGNTOOL_TIMESTAMP_URL) {
            $signtoolArgs += @("/tr", $env:SIGNTOOL_TIMESTAMP_URL, "/td", "SHA256")
        }
        $signtoolArgs += $out
        & signtool.exe @signtoolArgs
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Authenticode signing succeeded for AlgoFortis.exe"
        } else {
            Write-Warning "Authenticode signing failed with exit code $LASTEXITCODE"
        }
    }
    
    Get-Item $out | Select-Object Name, Length, LastWriteTime
} else {
    Write-Error "Compilation FAILED with exit code $LASTEXITCODE"
}
