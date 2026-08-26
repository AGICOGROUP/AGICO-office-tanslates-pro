param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = "Stop"

function Release-ComObject($Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

$sourceFull = [IO.Path]::GetFullPath($SourcePath)
$outputFull = [IO.Path]::GetFullPath($OutputPath)
if (-not [IO.File]::Exists($sourceFull)) { throw "source file not found: $sourceFull" }
if ([IO.Path]::GetExtension($sourceFull).ToLowerInvariant() -ne ".xls") { throw "source must be .xls" }
if ([IO.Path]::GetExtension($outputFull).ToLowerInvariant() -ne ".xlsx") { throw "output must be .xlsx" }
if ($sourceFull -eq $outputFull) { throw "source and output paths must differ" }
if ([IO.File]::Exists($outputFull)) { throw "output already exists: $outputFull" }

$excel = $null
$workbook = $null
$validated = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.AutomationSecurity = 3
    $excel.Visible = $false
    $excel.DisplayAlerts = $false

    # Open exactly once in ReadOnly mode; macros are disabled before this call.
    $workbook = $excel.Workbooks.Open($sourceFull, 0, $true)
    if ($workbook.HasVBProject) { throw "macro-enabled .xls files are not supported" }

    $outputDirectory = [IO.Path]::GetDirectoryName($outputFull)
    if (-not [IO.Directory]::Exists($outputDirectory)) {
        [void][IO.Directory]::CreateDirectory($outputDirectory)
    }
    $workbook.SaveAs($outputFull, 51)
    $workbook.Close($false)
    Release-ComObject $workbook
    $workbook = $null

    # One lightweight native reopen validates the converted package.
    $validated = $excel.Workbooks.Open($outputFull, 0, $true)
    $worksheetNames = @($validated.Worksheets | ForEach-Object { $_.Name })
    $validated.Close($false)

    [ordered]@{
        passed = $true
        source = $sourceFull
        output = $outputFull
        worksheets = $worksheetNames
        source_sha256 = (Get-FileHash -LiteralPath $sourceFull -Algorithm SHA256).Hash
        output_sha256 = (Get-FileHash -LiteralPath $outputFull -Algorithm SHA256).Hash
    } | ConvertTo-Json -Depth 4
}
finally {
    if ($null -ne $validated) {
        try { $validated.Close($false) } catch {}
        Release-ComObject $validated
    }
    if ($null -ne $workbook) {
        try { $workbook.Close($false) } catch {}
        Release-ComObject $workbook
    }
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
        Release-ComObject $excel
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
