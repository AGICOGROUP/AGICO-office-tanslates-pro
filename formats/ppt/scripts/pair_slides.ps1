param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$TranslatedPath,
    [Parameter(Mandatory)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$deck = $null
$translated = $null
$reopened = $null
try {
    $deck = $app.Presentations.Open($SourcePath, -1, 0, 0)
    $translated = $app.Presentations.Open($TranslatedPath, -1, 0, 0)
    $count = $deck.Slides.Count
    if ($count -ne $translated.Slides.Count) { throw 'Source and translation slide counts differ.' }
    if ($deck.PageSetup.SlideWidth -ne $translated.PageSetup.SlideWidth -or
        $deck.PageSetup.SlideHeight -ne $translated.PageSetup.SlideHeight) {
        throw 'Source and translation slide sizes differ.'
    }
    $translated.Close()
    $translated = $null
    if ($deck.Slides.InsertFromFile($TranslatedPath, $count) -ne $count) {
        throw 'PowerPoint imported an unexpected number of slides.'
    }
    $targetIds = @(for ($i = 1; $i -le $count; $i++) { $deck.Slides.Item($count + $i).SlideID })
    for ($i = 1; $i -le $count; $i++) {
        $deck.Slides.FindBySlideID($targetIds[$i - 1]).MoveTo(2 * $i)
    }
    $deck.SaveCopyAs($OutputPath, 24)
    $deck.Close()
    $deck = $null
    $reopened = $app.Presentations.Open($OutputPath, -1, 0, 0)
    if ($reopened.Slides.Count -ne 2 * $count) { throw 'Paired deck did not reopen with the expected slide count.' }
}
finally {
    if ($reopened) { $reopened.Close() }
    if ($translated) { $translated.Close() }
    if ($deck) { $deck.Close() }
}
