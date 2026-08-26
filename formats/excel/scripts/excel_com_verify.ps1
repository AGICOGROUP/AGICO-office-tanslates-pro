param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$InputPath,
    [switch]$Bilingual
)

$ErrorActionPreference = 'Stop'
$sourceFull = [IO.Path]::GetFullPath($SourcePath)
$inputFull = [IO.Path]::GetFullPath($InputPath)
foreach ($candidate in @($sourceFull, $inputFull)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Input not found: $candidate" }
}

function Get-WorkbookReport {
    param($Excel, [string]$Path)
    $workbook = $null
    try {
        $workbook = $Excel.Workbooks.Open($Path, 0, $true)
        $Excel.CalculateFullRebuild()
        $names = @($workbook.Worksheets | ForEach-Object { $_.Name })
        $usedRanges = [ordered]@{}
        $formulaErrors = New-Object 'System.Collections.Generic.HashSet[string]'
        $valueErrors = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($sheet in $workbook.Worksheets) {
            $usedRanges[$sheet.Name] = $sheet.UsedRange.Address()
            foreach ($spec in @(@(-4123, 16, 'formula'), @(2, 16, 'value'))) {
                $bad = $null
                try {
                    $bad = $sheet.UsedRange.SpecialCells($spec[0], $spec[1])
                    foreach ($cell in $bad.Cells) {
                        $key = "{0}!{1}" -f $sheet.Name, $cell.Address($false, $false)
                        if ($spec[2] -eq 'formula') { [void]$formulaErrors.Add($key) }
                        else { [void]$valueErrors.Add($key) }
                        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($cell)
                    }
                } catch {
                    if ($_.Exception.HResult -ne -2146827284) { throw }
                } finally {
                    if ($bad) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($bad) }
                }
            }
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($sheet)
        }
        return [pscustomobject]@{
            worksheets = $names
            used_ranges = $usedRanges
            formula_errors = $formulaErrors
            value_errors = $valueErrors
        }
    } finally {
        if ($workbook) {
            $workbook.Close($false)
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
        }
    }
}

function Convert-SourceErrorKeysForBilingual {
    param($Keys)
    $mapped = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($key in $Keys) {
        if ($key -match '^(.*)!([A-Z]+)(\d+)$') {
            [void]$mapped.Add(("{0}!{1}{2}" -f $Matches[1], $Matches[2], ([int]$Matches[3] * 2 - 1)))
        } else {
            [void]$mapped.Add($key)
        }
    }
    return $mapped
}

$excel = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $source = Get-WorkbookReport $excel $sourceFull
    $output = Get-WorkbookReport $excel $inputFull
    $baselineFormulaErrors = if ($Bilingual) {
        Convert-SourceErrorKeysForBilingual $source.formula_errors
    } else { $source.formula_errors }
    $baselineValueErrors = if ($Bilingual) {
        Convert-SourceErrorKeysForBilingual $source.value_errors
    } else { $source.value_errors }
    $newFormulaErrors = @($output.formula_errors | Where-Object { -not $baselineFormulaErrors.Contains($_) })
    $newValueErrors = @($output.value_errors | Where-Object { -not $baselineValueErrors.Contains($_) })
    if ($newFormulaErrors.Count -gt 0 -or $newValueErrors.Count -gt 0) {
        throw "Output contains new Excel error cells: formulas=$($newFormulaErrors.Count) values=$($newValueErrors.Count)"
    }
    [pscustomobject]@{
        passed = $true
        application = 'Microsoft Excel'
        source = $sourceFull
        output = $inputFull
        worksheets = $output.worksheets
        used_ranges = $output.used_ranges
        source_formula_error_count = $source.formula_errors.Count
        output_formula_error_count = $output.formula_errors.Count
        new_formula_error_count = $newFormulaErrors.Count
        source_value_error_count = $source.value_errors.Count
        output_value_error_count = $output.value_errors.Count
        new_value_error_count = $newValueErrors.Count
    } | ConvertTo-Json -Depth 4 -Compress
} finally {
    if ($excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
