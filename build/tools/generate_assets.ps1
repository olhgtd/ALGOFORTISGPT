param (
    [string]$TargetDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$SourceImage = ""
)

if ([string]::IsNullOrWhiteSpace($SourceImage)) {
    $SourceImage = Join-Path $TargetDir "assets\branding\AlgoFortis\AlgoFortis_User_Logo.png"
}

Add-Type -AssemblyName System.Drawing

if (-not (Test-Path $SourceImage)) {
    Write-Error "Source image not found at $SourceImage"
    exit 1
}

$srcBmp = [System.Drawing.Bitmap]::FromFile($SourceImage)
Write-Host "Loaded source image: $($srcBmp.Width)x$($srcBmp.Height)"

# 1. Save master app logo
$logoPng = Join-Path $TargetDir "algofortis_logo.png"
$srcBmp.Save($logoPng, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Host "Saved $logoPng"

# Also copy to dashboard/web/public/
$webPublic = Join-Path $TargetDir "dashboard\web\public"
if (-not (Test-Path $webPublic)) {
    New-Item -ItemType Directory -Path $webPublic -Force | Out-Null
}
$srcBmp.Save((Join-Path $webPublic "algofortis_logo.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$srcBmp.Save((Join-Path $webPublic "favicon.png"), [System.Drawing.Imaging.ImageFormat]::Png)

# Function to resize image high quality
function Resize-Bitmap {
    param (
        [System.Drawing.Bitmap]$img,
        [int]$width,
        [int]$height
    )
    $dest = New-Object System.Drawing.Bitmap($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($dest)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.DrawImage($img, 0, 0, $width, $height)
    $g.Dispose()
    return $dest
}

# Function to create multi-resolution ICO with PNG frames
function Create-MultiResIco {
    param (
        [System.Drawing.Bitmap]$masterBmp,
        [int[]]$sizes,
        [string]$outputPath
    )
    
    $pngStreams = @()
    foreach ($sz in $sizes) {
        $resized = Resize-Bitmap $masterBmp $sz $sz
        $ms = New-Object System.IO.MemoryStream
        $resized.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngStreams += @{
            Size = $sz
            Bytes = $ms.ToArray()
        }
        $ms.Dispose()
        $resized.Dispose()
    }
    
    $fs = New-Object System.IO.FileStream($outputPath, [System.IO.FileMode]::Create)
    $bw = New-Object System.IO.BinaryWriter($fs)
    
    # ICONHEADER: Reserved (2), Type (2 = 1 for icon), Count (2)
    $bw.Write([uint16]0)
    $bw.Write([uint16]1)
    $bw.Write([uint16]$pngStreams.Count)
    
    # Calculate offset after directory entries: 6 + 16 * count
    $offset = 6 + (16 * $pngStreams.Count)
    
    # Write ICONDIRENTRY for each
    foreach ($entry in $pngStreams) {
        $w = if ($entry.Size -ge 256) { [byte]0 } else { [byte]$entry.Size }
        $h = if ($entry.Size -ge 256) { [byte]0 } else { [byte]$entry.Size }
        $bw.Write($w) # bWidth
        $bw.Write($h) # bHeight
        $bw.Write([byte]0) # bColorCount
        $bw.Write([byte]0) # bReserved
        $bw.Write([uint16]1) # wPlanes
        $bw.Write([uint16]32) # wBitCount
        $bw.Write([uint32]$entry.Bytes.Length) # dwBytesInRes
        $bw.Write([uint32]$offset) # dwImageOffset
        
        $offset += $entry.Bytes.Length
    }
    
    # Write PNG payloads
    foreach ($entry in $pngStreams) {
        $bw.Write($entry.Bytes)
    }
    
    $bw.Flush()
    $bw.Close()
    $fs.Close()
    Write-Host "Successfully generated multi-res ICO: $outputPath with sizes $($sizes -join ', ')"
}

$sizes = @(16, 24, 32, 48, 64, 128, 256)
$icoTarget = Join-Path $TargetDir "algofortis.ico"
Create-MultiResIco $srcBmp $sizes $icoTarget

# Also copy to build/tools and build/stage
Copy-Item $icoTarget (Join-Path $TargetDir "build\tools\algofortis.ico") -Force
if (Test-Path (Join-Path $TargetDir "build\stage")) {
    Copy-Item $icoTarget (Join-Path $TargetDir "build\stage\algofortis.ico") -Force
    Copy-Item $logoPng (Join-Path $TargetDir "build\stage\algofortis_logo.png") -Force
}

$srcBmp.Dispose()
Write-Host "Asset generation complete."
