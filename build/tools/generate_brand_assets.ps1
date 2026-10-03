param(
    [Parameter(Mandatory=$true)][string]$SourceImage,
    [Parameter(Mandatory=$true)][string]$OutputDir
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
if (-not (Test-Path $SourceImage)) { throw "Canonical AlgoFortis brand source missing: $SourceImage" }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

function Resize-Bitmap {
    param([System.Drawing.Bitmap]$Image, [int]$Size)
    $dest = New-Object System.Drawing.Bitmap($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($dest)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.DrawImage($Image, 0, 0, $Size, $Size)
    $g.Dispose()
    return $dest
}
function Write-MultiResIco {
    param([System.Drawing.Bitmap]$Master, [string]$Path)
    $frames = @()
    foreach ($size in @(16,24,32,48,64,128,256)) {
        $bmp = Resize-Bitmap $Master $size
        $ms = New-Object System.IO.MemoryStream
        $bmp.Save($ms,[System.Drawing.Imaging.ImageFormat]::Png)
        $frames += @{ Size=$size; Bytes=$ms.ToArray() }
        $ms.Dispose(); $bmp.Dispose()
    }
    $fs = New-Object System.IO.FileStream($Path,[System.IO.FileMode]::Create)
    $bw = New-Object System.IO.BinaryWriter($fs)
    try {
        $bw.Write([uint16]0); $bw.Write([uint16]1); $bw.Write([uint16]$frames.Count)
        $offset = 6 + (16 * $frames.Count)
        foreach ($frame in $frames) {
            $wh = if ($frame.Size -ge 256) { [byte]0 } else { [byte]$frame.Size }
            $bw.Write($wh); $bw.Write($wh); $bw.Write([byte]0); $bw.Write([byte]0)
            $bw.Write([uint16]1); $bw.Write([uint16]32)
            $bw.Write([uint32]$frame.Bytes.Length); $bw.Write([uint32]$offset)
            $offset += $frame.Bytes.Length
        }
        foreach ($frame in $frames) { $bw.Write($frame.Bytes) }
        $bw.Flush()
    } finally { $bw.Dispose(); $fs.Dispose() }
}
$master=[System.Drawing.Bitmap]::FromFile((Resolve-Path $SourceImage).Path)
try {
    $master.Save((Join-Path $OutputDir "algofortis_logo.png"),[System.Drawing.Imaging.ImageFormat]::Png)
    Write-MultiResIco $master (Join-Path $OutputDir "algofortis.ico")
} finally { $master.Dispose() }
Write-Host "CANONICAL_BRAND=PASS"
