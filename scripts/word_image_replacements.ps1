param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][string]$PlanPath
)
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($DocumentPath, $false, $false)
    $replaced = @()
    foreach ($item in $plan) {
        if ($item.story_type -ne 1 -or $item.kind -ne 'inline') {
            throw "Unsupported Word image host for $($item.id): only main-story inline images are currently replaceable"
        }
        $shape = $doc.InlineShapes.Item([int]$item.index)
        $width = $shape.Width
        $height = $shape.Height
        $range = $shape.Range.Duplicate
        $shape.Delete()
        $newShape = $doc.InlineShapes.AddPicture([string]$item.replacement_path, $false, $true, $range)
        $newShape.LockAspectRatio = 0
        $newShape.Width = $width
        $newShape.Height = $height
        $newShape.AlternativeText = "GPT translated image: $($item.id)"
        $replaced += [pscustomobject]@{id=$item.id; width=$width; height=$height}
    }
    $doc.Save()
    $doc.Close($false)
    $doc = $null
    $replaced | ConvertTo-Json -Compress
}
finally {
    if ($null -ne $doc) { $doc.Close($false) }
    $word.Quit()
}
