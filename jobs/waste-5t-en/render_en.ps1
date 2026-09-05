$ErrorActionPreference = 'Stop'
$inPdf = 'E:\office-translate-pro\jobs\waste-5t-en\translated-en.pdf'
$outDir = 'E:\office-translate-pro\jobs\waste-5t-en\pages-en'

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]

$global:asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $asTaskGeneric = ($global:asTask.MakeGenericMethod($ResultType))
    $netTask = $asTaskGeneric.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
$global:asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
})[0]
function AwaitAction($WinRtAction) {
    $netTask = $global:asTaskAction.Invoke($null, @($WinRtAction))
    $netTask.Wait(-1) | Out-Null
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($inPdf)) ([Windows.Storage.StorageFile])
$pdf = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
Write-Output ("page count: " + $pdf.PageCount)
for ($i = 0; $i -lt $pdf.PageCount; $i++) {
    $page = $pdf.GetPage($i)
    $folder = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($outDir)) ([Windows.Storage.StorageFolder])
    $newFile = Await ($folder.CreateFileAsync(("en{0:d2}.png" -f ($i + 1)), [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])
    $stream = Await ($newFile.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
    $opts = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $opts.DestinationWidth = [uint32]1500
    AwaitAction ($page.RenderToStreamAsync($stream, $opts))
    $stream.Dispose()
    $page.Dispose()
}
Write-Output 'all done'
