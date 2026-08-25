param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [Parameter(Mandatory = $true)][string]$SheetNamesPath,
    [Parameter(Mandatory = $false)][string]$PrintLayoutPath
)

$ErrorActionPreference = 'Stop'
$inputFull = [IO.Path]::GetFullPath($InputPath)
$outputFull = [IO.Path]::GetFullPath($OutputDirectory)
$sheetNamesFull = [IO.Path]::GetFullPath($SheetNamesPath)
if (-not (Test-Path -LiteralPath $inputFull -PathType Leaf)) { throw "Input not found: $inputFull" }
if (-not (Test-Path -LiteralPath $sheetNamesFull -PathType Leaf)) { throw "Sheet list not found: $sheetNamesFull" }
[IO.Directory]::CreateDirectory($outputFull) | Out-Null
$requested = Get-Content -LiteralPath $sheetNamesFull -Raw -Encoding UTF8 | ConvertFrom-Json
$layouts = $null
if ($PrintLayoutPath) {
    $layoutFull = [IO.Path]::GetFullPath($PrintLayoutPath)
    if (-not (Test-Path -LiteralPath $layoutFull -PathType Leaf)) { throw "Print layout not found: $layoutFull" }
    $layouts = Get-Content -LiteralPath $layoutFull -Raw -Encoding UTF8 | ConvertFrom-Json
}
$excel = $workbook = $null
$pdfs = [Collections.Generic.List[string]]::new()
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $workbook = $excel.Workbooks.Open($inputFull, 0, $true)
    $excel.CalculateFullRebuild()
    $names = @($workbook.Worksheets | ForEach-Object { $_.Name })
    $targets = @($requested | Where-Object { $null -ne $_ -and [string]$_ -ne '' } | ForEach-Object { [string]$_ })
    foreach ($name in $targets) {
        if ($name -notin $names) { throw "Worksheet not found: $name" }
        $sheet = $workbook.Worksheets.Item($name)
        if ($layouts -and $layouts.PSObject.Properties.Name -contains $name) {
            $layout = $layouts.$name
            $sheet.PageSetup.Zoom = $false
            $sheet.PageSetup.Orientation = if ($layout.orientation -eq 'landscape') { 2 } else { 1 }
            $sheet.PageSetup.FitToPagesWide = [int]$layout.fitToPagesWide
            $sheet.PageSetup.FitToPagesTall = if ([int]$layout.fitToPagesTall -eq 0) {
                $false
            } else {
                [int]$layout.fitToPagesTall
            }
        }
        $safe = $name -replace '[<>:"/\\|?*]', '_'
        $pdf = Join-Path $outputFull "$safe.pdf"
        $sheet.ExportAsFixedFormat(0, $pdf)
        if (-not (Test-Path -LiteralPath $pdf -PathType Leaf)) { throw "Excel did not create PDF: $pdf" }
        $pdfs.Add($pdf)
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet)
    }
    [pscustomobject]@{
        passed = $true
        application = 'Microsoft Excel'
        worksheets = $names
        rendered_sheets = $targets
        pdfs = @($pdfs)
    } | ConvertTo-Json -Depth 4 -Compress
}
finally {
    if ($workbook) { $workbook.Close($false) }
    if ($excel) { $excel.Quit() }
    foreach ($obj in @($workbook, $excel)) {
        if ($obj) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj) }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
