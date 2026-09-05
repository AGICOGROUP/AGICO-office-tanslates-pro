$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$src = 'E:\office-translate-pro\jobs\waste-5t-en\review-copy.docx'
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($src, $false, $true)
    Write-Output 'opened'
    $find = '[一-龥]'
    # Word wildcard search for CJK range
    $range = $doc.Content
    $range.Find.ClearFormatting()
    $range.Find.MatchWildcards = $true
    $range.Find.Text = $find
    $count = 0
    $found = $range.Find.Execute()
    while ($found -and $count -lt 40) {
        $t = $range.Text
        $start = $range.Start
        # get surrounding context
        $ctxStart = [Math]::Max(0, $start - 25)
        $ctx = $doc.Range($ctxStart, [Math]::Min($doc.Content.End, $start + $t.Length + 25)).Text
        $ctx = ($ctx -replace "`r", ' ').Substring(0, [Math]::Min(70, $ctx.Length))
        Write-Output ("CJK @" + $start + ": [" + $t + "]  ctx: " + $ctx)
        $count++
        $range.Find.ClearFormatting()
        $range.Find.MatchWildcards = $true
        $range.Find.Text = $find
        $found = $range.Find.Execute()
    }
    Write-Output ("total found: " + $count)
} catch {
    Write-Output ("ERROR: " + $_.Exception.Message)
} finally {
    if ($doc) { try { $doc.Close($false) } catch {} }
    if ($word) { try { $word.Quit() } catch {} }
}
