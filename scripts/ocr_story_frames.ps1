param(
    [Parameter(Mandatory = $true)][string]$FrameDirectory,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$LanguageTag = 'ru-RU'
)

# Local research utility. Windows PowerShell 5.1, installed Windows OCR only.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$storageType = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$streamType = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$accessType = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$decoderType = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$bitmapType = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$ocrType = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$resultType = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
$lineType = [Windows.Media.Ocr.OcrLine, Windows.Foundation, ContentType = WindowsRuntime]
$wordType = [Windows.Media.Ocr.OcrWord, Windows.Foundation, ContentType = WindowsRuntime]
$languageType = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
    $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

function Wait-Operation($Operation, [Type]$ResultType) {
    $task = $asTaskMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(30000)) { throw 'OCR operation timed out.' }
    return $task.Result
}

function Get-VectorItems($Vector, [Type]$ItemType) {
    $collectionType = [System.Collections.Generic.IReadOnlyCollection``1].MakeGenericType($ItemType)
    $listType = [System.Collections.Generic.IReadOnlyList``1].MakeGenericType($ItemType)
    $count = $collectionType.GetProperty('Count').GetValue($Vector, $null)
    $itemProperty = $listType.GetProperty('Item')
    for ($itemIndex = 0; $itemIndex -lt $count; $itemIndex++) {
        $itemProperty.GetValue($Vector, @([int]$itemIndex))
    }
}

$language = [Activator]::CreateInstance($languageType, @($LanguageTag))
if (-not $ocrType::IsLanguageSupported($language)) { throw 'Requested OCR language is not installed.' }
$engine = $ocrType::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'Cannot create local OCR engine.' }
$directory = (Resolve-Path -LiteralPath $FrameDirectory).Path
$files = @(Get-ChildItem -LiteralPath $directory -Filter 'frame-*.jpg' -File | Sort-Object Name)
if ($files.Count -eq 0 -or $files.Count -gt 100) { throw 'Trial requires from 1 to 100 frame JPEG files.' }
if (Test-Path -LiteralPath $OutputPath) { throw 'OCR report already exists; choose a fresh output path.' }
$watch = [Diagnostics.Stopwatch]::StartNew()
$results = @()
foreach ($file in $files) {
    $fileWatch = [Diagnostics.Stopwatch]::StartNew()
    $storageFile = Wait-Operation ($storageType::GetFileFromPathAsync($file.FullName)) $storageType
    $stream = Wait-Operation ($storageFile.OpenAsync($accessType::Read)) $streamType
    $bitmap = $null
    try {
        $decoder = Wait-Operation ($decoderType::CreateAsync($stream)) $decoderType
        $bitmap = Wait-Operation ($decoder.GetSoftwareBitmapAsync()) $bitmapType
        if ($bitmap.PixelWidth -gt $ocrType::MaxImageDimension -or
            $bitmap.PixelHeight -gt $ocrType::MaxImageDimension) { throw 'Image exceeds local OCR limits.' }
        $result = Wait-Operation ($engine.RecognizeAsync($bitmap)) $resultType
        $lines = @()
        foreach ($line in @(Get-VectorItems $result.Lines $lineType)) {
            $words = @()
            foreach ($word in @(Get-VectorItems $line.Words $wordType)) {
                $rect = $word.BoundingRect
                $words += [ordered]@{
                    text = $word.Text
                    x = $rect.X; y = $rect.Y; width = $rect.Width; height = $rect.Height
                }
            }
            $lines += [ordered]@{text = $line.Text; words = $words}
        }
        $results += [ordered]@{
            file = $file.Name
            width = $bitmap.PixelWidth; height = $bitmap.PixelHeight
            text = $result.Text; lines = $lines
            elapsed_ms = $fileWatch.Elapsed.TotalMilliseconds
        }
    }
    finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        $stream.Dispose()
    }
}
$report = [ordered]@{
    engine = 'Windows.Media.Ocr.OcrEngine'
    language = $LanguageTag
    elapsed_seconds = $watch.Elapsed.TotalSeconds
    frame_count = $results.Count
    results = $results
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output ('OCR complete: {0} frames, {1:N3} seconds, language={2}' -f $results.Count, $watch.Elapsed.TotalSeconds, $LanguageTag)
