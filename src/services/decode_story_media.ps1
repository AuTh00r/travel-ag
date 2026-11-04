param(
    [Parameter(Mandatory = $true)][string]$MediaPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [Parameter(Mandatory = $true)][ValidateSet('VIDEO', 'IMAGE')][string]$MediaType
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$storageType = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$clipType = [Windows.Media.Editing.MediaClip, Windows.Media.Editing, ContentType = WindowsRuntime]
$compositionType = [Windows.Media.Editing.MediaComposition, Windows.Media.Editing, ContentType = WindowsRuntime]
$imageType = [Windows.Graphics.Imaging.ImageStream, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$decoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$precisionType = [Windows.Media.Editing.VideoFramePrecision, Windows.Media.Editing, ContentType = WindowsRuntime]
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
    $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Wait-Operation($Operation, [Type]$ResultType) {
    $task = $asTaskMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(30000)) { throw 'Decoder timeout.' }
    return $task.Result
}
$resolvedMedia = (Resolve-Path -LiteralPath $MediaPath).Path
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
$storageFile = Wait-Operation ($storageType::GetFileFromPathAsync($resolvedMedia)) $storageType
$frames = @()
if ($MediaType -eq 'IMAGE') {
    $stream = Wait-Operation ($storageFile.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType = WindowsRuntime])
    try {
        $decoder = Wait-Operation ($decoderType::CreateAsync($stream)) $decoderType
        if ($decoder.PixelWidth -eq 0 -or $decoder.PixelHeight -eq 0 -or
            $decoder.PixelWidth -gt 4096 -or $decoder.PixelHeight -gt 4096) { throw 'Invalid dimensions.' }
        # Read pixels as well as header: reject truncated/corrupt images.
        $pixelType = [Windows.Graphics.Imaging.PixelDataProvider, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
        $pixels = Wait-Operation ($decoder.GetPixelDataAsync()) $pixelType
        [void]$pixels.DetachPixelData()
        $frames += [ordered]@{file = [IO.Path]::GetFileName($resolvedMedia)}
    } finally { $stream.Dispose() }
} else {
    $clip = Wait-Operation ($clipType::CreateFromFileAsync($storageFile)) $clipType
    $duration = $clip.OriginalDuration.TotalSeconds
    $timingPath = Join-Path ([IO.Path]::GetDirectoryName($resolvedMedia)) 'video-timing.json'
    if (Test-Path -LiteralPath $timingPath) {
        $videoDuration = [double]((Get-Content -LiteralPath $timingPath -Raw | ConvertFrom-Json).duration)
        if ($videoDuration -le 0 -or $videoDuration -gt 90) { throw 'Invalid video timing.' }
        $duration = [Math]::Min($duration, $videoDuration)
    }
    $properties = $clip.GetVideoEncodingProperties()
    if ($duration -le 0 -or $duration -gt 90 -or $properties.Width -eq 0 -or
        $properties.Height -eq 0 -or $properties.Width -gt 4096 -or $properties.Height -gt 4096) { throw 'Invalid video.' }
    $fps = 30.0
    if ($properties.FrameRate.Numerator -gt 0 -and $properties.FrameRate.Denominator -gt 0) {
        $fps = [double]$properties.FrameRate.Numerator / $properties.FrameRate.Denominator
    }
    $last = $duration - [Math]::Min(1.0 / $fps, $duration / 2.0)
    $composition = [Activator]::CreateInstance($compositionType)
    $addClipMethod = [System.Collections.Generic.ICollection[Windows.Media.Editing.MediaClip]].GetMethod('Add')
    $addClipMethod.Invoke($composition.Clips, @($clip)) | Out-Null
    for ($index = 0; $index -lt 10; $index++) {
        $target = $index * $last / 9.0
        $filename = 'frame-{0:D3}.jpg' -f $index
        $thumbnail = Wait-Operation ($composition.GetThumbnailAsync(
            [TimeSpan]::FromSeconds($target), [int]$properties.Width, 0, $precisionType::NearestFrame)) $imageType
        $readStream = [IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($thumbnail)
        $writeStream = [IO.File]::Open((Join-Path $outputPath $filename), [IO.FileMode]::CreateNew)
        try { $readStream.CopyTo($writeStream) }
        finally { $writeStream.Dispose(); $readStream.Dispose(); $thumbnail.Dispose() }
        $frames += [ordered]@{file = $filename; target_seconds = $target}
    }
}
@{frames = $frames; audio_extracted = $false} | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $outputPath 'frames.json') -Encoding UTF8
