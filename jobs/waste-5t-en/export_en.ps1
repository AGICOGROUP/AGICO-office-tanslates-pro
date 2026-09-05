$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$src = 'E:office-translate-projobswaste-5t-en	ranslated-en.docx'
$pdf = 'E:\office-translate-pro\jobs\waste-5t-en\translated-en.pdf'
$word = $null
$doc = $null
for ($i = 1; $i -le 3; $i++) {
    try {
        $word = New-Object -ComObject Word.Application
        Write-Output "word started attempt $i"
        break
    } catch {
        Write-Output ("start failed: " + $_.Exception.Message)
        Start-Sleep -Seconds 5
    }
}
if (-not $word) { Write-Output 'WORD COM UNAVAILABLE'; exit 1 }
try {
    $doc = $word.Documents.Open($src, $false, $true)
    Write-Output 'opened'
    $doc.Repaginate()
    Write-Output ("pages: " + $doc.Content.Information(4))
    $doc.ExportAsFixedFormat($pdf, 17)
    Write-Output 'exported'
} catch {
    Write-Output ("ERROR: " + $_.Exception.Message + " @ line " + $_.InvocationInfo.ScriptLineNumber)
} finally {
    if ($doc) { try { $doc.Close($false) } catch {} }
    if ($word) { try { $word.Quit() } catch {} }
}
if (Test-Path $pdf) { Write-Output ("PDF OK " + (Get-Item $pdf).Length + " bytes") } else { Write-Output 'PDF MISSING' }
