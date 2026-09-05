$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$src = 'E:\office-translate-pro\jobs\waste-5t-en\review-copy.docx'
$pdf = 'E:\office-translate-pro\jobs\waste-5t-en\translated-en.pdf'
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $opened = $false
    for ($i = 1; $i -le 6; $i++) {
        try {
            $doc = $word.Documents.Open($src, $false, $true)
            $opened = $true
            Write-Output "opened on attempt $i"
            break
        } catch {
            Write-Output ("open attempt " + $i + " failed: " + $_.Exception.Message)
            Start-Sleep -Seconds 3
        }
    }
    if ($opened) {
        $doc.Repaginate()
        Write-Output ("pages: " + $doc.Content.Information(4))
        $doc.ExportAsFixedFormat($pdf, 17)
        Write-Output 'exported'
    }
} finally {
    if ($doc) { try { $doc.Close($false) } catch {} }
    if ($word) { try { $word.Quit() } catch {} }
}
if (Test-Path $pdf) { Write-Output ("PDF OK " + (Get-Item $pdf).Length + " bytes") } else { Write-Output 'PDF MISSING' }
