param(
    [Parameter(Mandatory = $true)][string]$VideoPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [double]$IntervalSeconds = 1.5
)

# Local trial only. Run with Windows PowerShell 5.1; uses the installed OS decoder.
$ErrorActionPreference = 'Stop'
if ($IntervalSeconds -le 0) { throw 'Interval must be positive.' }
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$storageType = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$clipType = [Windows.Media.Editing.MediaClip, Windows.Media.Editing, ContentType = WindowsRuntime]
$compositionType = [Windows.Media.Editing.MediaComposition, Windows.Media.Editing, ContentType = WindowsRuntime]
$imageType = [Windows.Graphics.Imaging.ImageStream, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$precisionType = [Windows.Media.Editing.VideoFramePrecision, Windows.Media.Editing, ContentType = WindowsRuntime]
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
    $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

function Wait-Operation($Operation, [Type]$ResultType) {
    $task = $asTaskMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(30000)) { throw 'Decoder operation timed out.' }
    return $task.Result
}

$resolvedVideo = (Resolve-Path -LiteralPath $VideoPath).Path
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
[IO.Directory]::CreateDirectory($outputPath) | Out-Null
$storageFile = Wait-Operation ($storageType::GetFileFromPathAsync($resolvedVideo)) $storageType
$clip = Wait-Operation ($clipType::CreateFromFileAsync($storageFile)) $clipType
$composition = [Activator]::CreateInstance($compositionType)
$addClipMethod = [System.Collections.Generic.ICollection[Windows.Media.Editing.MediaClip]].GetMethod('Add')
$addClipMethod.Invoke($composition.Clips, @($clip)) | Out-Null
$durationSeconds = $clip.OriginalDuration.TotalSeconds
if ($durationSeconds -le 0 -or $durationSeconds -gt 90) {
    throw 'Trial supports video duration from 0 to 90 seconds.'
}
$properties = $clip.GetVideoEncodingProperties()
$frames = @()
for ($index = 0; ($index * $IntervalSeconds) -lt $durationSeconds; $index++) {
    $targetSeconds = $index * $IntervalSeconds
    $filename = 'frame-{0:D3}.jpg' -f $index
    $framePath = Join-Path $outputPath $filename
    if (Test-Path -LiteralPath $framePath) { throw 'Frame already exists; use a fresh output folder.' }
    $operation = $composition.GetThumbnailAsync(
        [TimeSpan]::FromSeconds($targetSeconds),
        [int]$properties.Width,
        0,
        $precisionType::NearestFrame
    )
    $thumbnail = Wait-Operation $operation $imageType
    $readStream = [IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($thumbnail)
    $writeStream = [IO.File]::Open($framePath, [IO.FileMode]::CreateNew)
    try { $readStream.CopyTo($writeStream) }
    finally {
        $writeStream.Dispose()
        $readStream.Dispose()
        $thumbnail.Dispose()
    }
    $frames += [ordered]@{file = $filename; target_seconds = $targetSeconds}
}
$manifest = [ordered]@{
    decoder = 'Windows.Media.Editing.MediaComposition'
    precision = 'NearestFrame'
    duration_seconds = $durationSeconds
    interval_seconds = $IntervalSeconds
    encoded_width = $properties.Width
    encoded_height = $properties.Height
    audio_extracted = $false
    frames = $frames
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outputPath 'frames.json') -Encoding UTF8
Write-Output ('Extracted {0} frames; duration={1}; interval={2}' -f $frames.Count, $durationSeconds, $IntervalSeconds)
