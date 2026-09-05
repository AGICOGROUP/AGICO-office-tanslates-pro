param(
    [Parameter(Mandatory=$true)][ValidateSet("convert", "validate")][string]$Action,
    [Parameter(Mandatory=$true)][string]$InputPath,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
# Emit UTF-8 regardless of the console codepage: the pipeline captures this output and
# decodes it as UTF-8; on CJK Windows installs the default GBK console encoding would
# otherwise raise UnicodeDecodeError in the Python reader thread.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.AutomationSecurity = 3
    $word.DisplayAlerts = 0
    if ($Action -eq "convert") {
        if (-not $OutputPath) { throw "OutputPath is required for conversion" }
        # Legacy .doc conversion is deliberately visible: hidden Word can stall on compatibility UI.
        $word.Visible = $true
        $document = $word.Documents.Open((Resolve-Path -LiteralPath $InputPath).Path, $false, $true)
        $document.SaveAs2([System.IO.Path]::GetFullPath($OutputPath), 16)
        [pscustomobject]@{ action = "convert"; output = [System.IO.Path]::GetFullPath($OutputPath) } | ConvertTo-Json -Compress
    } else {
        $word.Visible = $false
        $document = $word.Documents.Open((Resolve-Path -LiteralPath $InputPath).Path, $false, $true)
        $document.Repaginate()
        [pscustomobject]@{
            action = "validate"
            content_pages = $document.Content.Information(4)
            sections = $document.Sections.Count
            paragraphs = $document.Paragraphs.Count
            tables = $document.Tables.Count
            words = $document.Words.Count
        } | ConvertTo-Json -Compress
    }
} finally {
    # COM cleanup can fail spuriously (e.g. "RPC server unavailable" while Quit is still
    # draining) after the measurement has already succeeded — never fail the script for it.
    if ($document) { try { $document.Close($false) } catch {} }
    if ($word) {
        try { $word.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null } catch {}
    }
    try { [GC]::Collect(); [GC]::WaitForPendingFinalizers() } catch {}
}
