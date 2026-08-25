param(
    [Parameter(Mandatory = $true)][string]$InputPath
)

$ErrorActionPreference = 'Stop'
$inputFull = [IO.Path]::GetFullPath($InputPath)
if (-not (Test-Path -LiteralPath $inputFull -PathType Leaf)) { throw "Input not found: $inputFull" }
$excel = $workbook = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $workbook = $excel.Workbooks.Open($inputFull, 0, $true)
    $excel.CalculateFullRebuild()
    $names = @($workbook.Worksheets | ForEach-Object { $_.Name })
    $usedRanges = [ordered]@{}
    $formulaErrors = 0
    $valueErrors = 0
    foreach ($sheet in $workbook.Worksheets) {
        $usedRanges[$sheet.Name] = $sheet.UsedRange.Address()
        foreach ($spec in @(@(-4123, 16, 'formula'), @(2, 16, 'value'))) {
            try {
                $bad = $sheet.UsedRange.SpecialCells($spec[0], $spec[1])
                if ($spec[2] -eq 'formula') { $formulaErrors += $bad.Count } else { $valueErrors += $bad.Count }
                [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($bad)
            } catch {
                if ($_.Exception.HResult -ne -2146827284) { throw }
            }
        }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet)
    }
    if ($formulaErrors -gt 0 -or $valueErrors -gt 0) {
        throw "Excel error cells found: formulas=$formulaErrors values=$valueErrors"
    }
    [pscustomobject]@{
        passed = $true
        application = 'Microsoft Excel'
        worksheets = $names
        used_ranges = $usedRanges
        formula_error_count = $formulaErrors
        value_error_count = $valueErrors
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
