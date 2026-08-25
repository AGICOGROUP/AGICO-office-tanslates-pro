param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [ValidateSet('auto','word','excel','powerpoint')][string]$Application = 'auto'
)

$ErrorActionPreference = 'Stop'
$inputFull = [IO.Path]::GetFullPath($InputPath)
$outputFull = [IO.Path]::GetFullPath($OutputPdf)
if (-not (Test-Path -LiteralPath $inputFull -PathType Leaf)) { throw "Input not found: $inputFull" }
if ([IO.Path]::GetExtension($outputFull).ToLowerInvariant() -ne '.pdf') { throw 'OutputPdf must end in .pdf' }
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputFull)) | Out-Null

if ($Application -eq 'auto') {
    $ext = [IO.Path]::GetExtension($inputFull).ToLowerInvariant()
    if ($ext -in '.doc','.docx','.docm') { $Application = 'word' }
    elseif ($ext -in '.xls','.xlsx','.xlsm') { $Application = 'excel' }
    elseif ($ext -in '.ppt','.pptx','.pptm') { $Application = 'powerpoint' }
    else { throw "Unsupported Office extension: $ext" }
}

$app = $document = $workbook = $presentation = $null
try {
    if ($Application -eq 'word') {
        $app = New-Object -ComObject Word.Application
        $app.Visible = $false
        $app.DisplayAlerts = 0
        $document = $app.Documents.Open($inputFull, $false, $true)
        $document.ExportAsFixedFormat($outputFull, 17)
    }
    elseif ($Application -eq 'excel') {
        $app = New-Object -ComObject Excel.Application
        $app.Visible = $false
        $app.DisplayAlerts = $false
        $workbook = $app.Workbooks.Open($inputFull, 0, $true)
        $workbook.ExportAsFixedFormat(0, $outputFull)
    }
    else {
        $app = New-Object -ComObject PowerPoint.Application
        $presentation = $app.Presentations.Open($inputFull, $true, $false, $false)
        $presentation.SaveAs($outputFull, 32)
    }
}
finally {
    if ($document) { $document.Close($false) }
    if ($workbook) { $workbook.Close($false) }
    if ($presentation) { $presentation.Close() }
    if ($app) { $app.Quit() }
    foreach ($obj in @($document,$workbook,$presentation,$app)) {
        if ($obj) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj) }
    }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}

if (-not (Test-Path -LiteralPath $outputFull -PathType Leaf)) { throw "Office did not create PDF: $outputFull" }
Get-Item -LiteralPath $outputFull | Select-Object FullName, Length, LastWriteTime
