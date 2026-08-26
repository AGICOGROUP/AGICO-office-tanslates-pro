param(
    [Parameter(Mandatory=$true)][ValidateSet("convert", "validate")][string]$Action,
    [Parameter(Mandatory=$true)][string]$InputPath,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
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
    if ($document) { $document.Close($false) }
    if ($word) { $word.Quit() }
}
