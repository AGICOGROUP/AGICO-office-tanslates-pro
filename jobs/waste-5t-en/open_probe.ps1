$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$files = @(
    'E:\office-translate-pro\jobs\waste-5t-en\review-copy.docx',
    'E:\office-translate-pro\jobs\waste-5t-en\source-working.docx'
)
$word = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    foreach ($f in $files) {
        $doc = $null
        try {
            $doc = $word.Documents.Open($f, $false, $true)
            Write-Output ("OPEN-OK  : " + $f + "  pages=" + $doc.Content.Information(4))
            try { $doc.Close($false) } catch {}
            $doc = $null
        } catch {
            $msg = $_.Exception.Message
            if ($_.Exception.InnerException) { $msg += " | inner: " + $_.Exception.InnerException.Message }
            Write-Output ("OPEN-FAIL: " + $f + "  -> " + $msg)
        }
    }
} finally {
    if ($word) { try { $word.Quit() } catch {} }
}
