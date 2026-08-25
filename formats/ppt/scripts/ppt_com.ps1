param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("inspect", "extract", "apply", "apply-overlays", "convert", "verify", "render", "export-images", "inventory-nonstandard")]
    [string]$Command,

    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputPath,
    [string]$ManifestPath,
    [string]$SourcePath,
    [string]$TranslatedPath,
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

public sealed class PowerPointWindowGuard : IDisposable {
    private readonly HashSet<int> baselineProcessIds = new HashSet<int>();
    private volatile bool running;
    private Thread worker;

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

    public PowerPointWindowGuard() {
        foreach (Process process in Process.GetProcessesByName("POWERPNT")) {
            try { baselineProcessIds.Add(process.Id); }
            finally { process.Dispose(); }
        }
    }

    public void Start() {
        if (running) return;
        running = true;
        worker = new Thread(HideNewPowerPointWindows);
        worker.IsBackground = true;
        worker.Name = "PowerPointWindowGuard";
        worker.Start();
    }

    private void HideNewPowerPointWindows() {
        while (running) {
            foreach (Process process in Process.GetProcessesByName("POWERPNT")) {
                try {
                    if (!baselineProcessIds.Contains(process.Id)) HideWindowsForProcess(process.Id);
                }
                finally { process.Dispose(); }
            }
            Thread.Sleep(10);
        }
    }

    private static void HideWindowsForProcess(int targetProcessId) {
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            if (processId == (uint)targetProcessId) ShowWindowAsync(hWnd, 0);
            return true;
        }, IntPtr.Zero);
    }

    public void Stop() {
        running = false;
        if (worker != null && worker.IsAlive) worker.Join(1000);
    }

    public void Dispose() { Stop(); }
}
'@

function Resolve-ExistingPath {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Input file not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-OutputFile {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "OutputPath is required for command '$Command'."
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $directory = Split-Path -Parent $fullPath
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    return $fullPath
}

function Resolve-OutputDirectory {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "OutputDirectory is required for command '$Command'."
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
    return $fullPath
}

function Write-JsonUtf8 {
    param(
        [Parameter(Mandatory = $true)]$Data,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $json = $Data | ConvertTo-Json -Depth 40
    [System.IO.File]::WriteAllText(
        $Path,
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Release-ComObject {
    param($Object)
    if ($null -ne $Object -and [System.Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$TargetPath
    )

    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $targetFullPath = [System.IO.Path]::GetFullPath($TargetPath)
    if ([System.IO.Path]::GetPathRoot($baseFullPath) -ne [System.IO.Path]::GetPathRoot($targetFullPath)) {
        return $targetFullPath
    }
    $baseUri = [Uri]::new($baseFullPath)
    $targetUri = [Uri]::new($targetFullPath)
    return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString())
}

function Get-SlideTitle {
    param($Slide)
    $titleShape = $null
    try {
        $titleShape = $Slide.Shapes.Title
        if ($null -ne $titleShape -and $titleShape.HasTextFrame -eq -1 -and $titleShape.TextFrame.HasText -eq -1) {
            return [string]$titleShape.TextFrame.TextRange.Text
        }
    }
    catch {
        return ""
    }
    finally {
        Release-ComObject $titleShape
    }
    return ""
}

function Test-ShapeHasText {
    param($Shape)
    try {
        return ($Shape.HasTextFrame -eq -1 -and $Shape.TextFrame.HasText -eq -1)
    }
    catch {
        return $false
    }
}

function Test-ShapeHasTable {
    param($Shape)
    try {
        return ($Shape.HasTable -eq -1)
    }
    catch {
        return $false
    }
}

function Get-TableCellAnchors {
    param(
        $Shape,
        [switch]$IncludeText
    )

    $table = $null
    $anchors = @()
    $seenCells = @{}
    $invariantCulture = [System.Globalization.CultureInfo]::InvariantCulture
    try {
        $table = $Shape.Table
        for ($row = 1; $row -le $table.Rows.Count; $row++) {
            for ($column = 1; $column -le $table.Columns.Count; $column++) {
                $cell = $null
                $cellShape = $null
                try {
                    $cell = $table.Cell($row, $column)
                    $cellShape = $cell.Shape
                    $cellShapeId = [int]$cellShape.Id
                    $left = [double]$cellShape.Left
                    $top = [double]$cellShape.Top
                    $width = [double]$cellShape.Width
                    $height = [double]$cellShape.Height

                    if ($cellShapeId -gt 0) {
                        $cellKey = "id:$cellShapeId"
                    }
                    else {
                        # PowerPoint 2016 returns Id=0 for every table cell in
                        # this legacy .ppt fixture. Merged coordinates still
                        # expose the same cell geometry, so geometry is the
                        # only usable identity fallback when no ID is exposed.
                        $cellKey = "geometry:{0}|{1}|{2}|{3}" -f `
                            $left.ToString("R", $invariantCulture), `
                            $top.ToString("R", $invariantCulture), `
                            $width.ToString("R", $invariantCulture), `
                            $height.ToString("R", $invariantCulture)
                    }
                    if ($seenCells.ContainsKey($cellKey)) {
                        continue
                    }
                    $seenCells[$cellKey] = $true

                    $paragraphData = @()
                    $normalizedText = ""
                    if ($IncludeText) {
                        $textRange = $null
                        $paragraphs = $null
                        try {
                            $textRange = $cellShape.TextFrame.TextRange
                            $normalizedText = (
                                [string]$textRange.Text -replace "[\r\n\v]+$", ""
                            ).Trim()
                            $paragraphs = $textRange.Paragraphs()
                            for (
                                $paragraphIndex = 1
                                $paragraphIndex -le $paragraphs.Count
                                $paragraphIndex++
                            ) {
                                $paragraph = $null
                                try {
                                    $paragraph = $textRange.Paragraphs(
                                        $paragraphIndex,
                                        1
                                    )
                                    $sourceText = [string]$paragraph.Text
                                    $normalized = (
                                        $sourceText -replace "[\r\n\v]+$", ""
                                    ).Trim()
                                    if ([string]::IsNullOrWhiteSpace($normalized)) {
                                        continue
                                    }
                                    $paragraphData += [pscustomobject]@{
                                        Index = $paragraphIndex
                                        SourceText = $sourceText
                                        NormalizedText = $normalized
                                    }
                                }
                                finally {
                                    Release-ComObject $paragraph
                                }
                            }
                        }
                        finally {
                            Release-ComObject $paragraphs
                            Release-ComObject $textRange
                        }
                    }

                    $anchors += [pscustomobject]@{
                        Row = $row
                        Column = $column
                        CellShapeId = $cellShapeId
                        Key = $cellKey
                        Left = $left
                        Top = $top
                        Width = $width
                        Height = $height
                        NormalizedText = $normalizedText
                        Paragraphs = $paragraphData
                    }
                }
                finally {
                    Release-ComObject $cellShape
                    Release-ComObject $cell
                }
            }
        }
    }
    finally {
        Release-ComObject $table
    }

    return $anchors
}

function Get-TableNeighboringText {
    param(
        [object[]]$Anchors,
        $Current
    )

    $nonEmptyAnchors = @(
        $Anchors | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.NormalizedText)
        }
    )
    $headerRow = @(
        $nonEmptyAnchors |
            Group-Object Row |
            Where-Object Count -gt 1 |
            Sort-Object { [int]$_.Name } |
            Select-Object -First 1
    )
    $headerRowIndex = if ($headerRow.Count -eq 1) {
        [int]$headerRow[0].Name
    }
    else {
        1
    }

    $candidates = @()
    $candidates += @(
        $nonEmptyAnchors |
            Where-Object Row -eq $Current.Row |
            Sort-Object Column
    )
    $candidates += @(
        $nonEmptyAnchors |
            Where-Object {
                $_.Row -eq $headerRowIndex -and
                $_.Column -eq $Current.Column
            }
    )

    $neighboringText = @()
    $seenText = @{}
    foreach ($candidate in $candidates) {
        if ($candidate.Key -eq $Current.Key) {
            continue
        }
        $text = [string]$candidate.NormalizedText
        if (-not $seenText.ContainsKey($text)) {
            $seenText[$text] = $true
            $neighboringText += $text
        }
    }
    return $neighboringText
}

function Get-ShapeById {
    param(
        $Slide,
        [int]$ShapeId
    )
    for ($shapeIndex = 1; $shapeIndex -le $Slide.Shapes.Count; $shapeIndex++) {
        $candidate = $Slide.Shapes.Item($shapeIndex)
        if ([int]$candidate.Id -eq $ShapeId) {
            return $candidate
        }
        Release-ComObject $candidate
    }
    return $null
}

function Get-ShapeCollectionIndexMap {
    param($Slide)
    $map = @{}
    for ($shapeIndex = 1; $shapeIndex -le $Slide.Shapes.Count; $shapeIndex++) {
        $shape = $Slide.Shapes.Item($shapeIndex)
        try {
            $map[[int]$shape.Id] = $shapeIndex
        }
        finally {
            Release-ComObject $shape
        }
    }
    return $map
}

function Test-TextOverflow {
    param(
        $Shape,
        [string]$ItemId = "unknown"
    )
    try {
        $frame = $Shape.TextFrame2
        $availableHeight = [double]$Shape.Height - [double]$frame.MarginTop - [double]$frame.MarginBottom
        $availableWidth = [double]$Shape.Width - [double]$frame.MarginLeft - [double]$frame.MarginRight
        $boundHeight = [double]$frame.TextRange.BoundHeight
        $boundWidth = [double]$frame.TextRange.BoundWidth
        return (
            $availableHeight -le 0 -or
            $availableWidth -le 0 -or
            $boundHeight -gt ($availableHeight + 0.5) -or
            $boundWidth -gt ($availableWidth + 0.5)
        )
    }
    catch {
        Write-Warning (
            "QA: overflow measurement failed for '$ItemId'; " +
            "applying conservative fit: $($_.Exception.Message)"
        )
        return $true
    }
}

function Apply-LocalTextFit {
    param(
        $Shape,
        [int]$ParagraphIndex,
        [double]$OriginalFontSize,
        [string]$ItemId = "unknown"
    )
    if (-not (Test-TextOverflow $Shape $ItemId)) {
        return
    }

    try {
        $Shape.TextFrame2.WordWrap = -1
        $targetRange = $Shape.TextFrame2.TextRange.Paragraphs($ParagraphIndex, 1)
        $targetRange.Font.Spacing = -0.5
        if ($OriginalFontSize -gt 0) {
            $minimumSize = $OriginalFontSize * 0.85
            $currentSize = $OriginalFontSize
            while ((Test-TextOverflow $Shape $ItemId) -and ($currentSize - 0.5) -ge $minimumSize) {
                $currentSize -= 0.5
                $targetRange.Font.Size = $currentSize
            }
        }
    }
    catch {
        # TextFrame2 fitting is best-effort for legacy objects. Structural QA
        # and rendered-slide review remain the final gate.
    }
    finally {
        Release-ComObject $targetRange
    }
}

function Apply-LocalTableCellTextFit {
    param(
        $CellShape,
        [int]$ParagraphIndex,
        [double]$OriginalFontSize,
        [string]$ItemId
    )
    if (-not (Test-TextOverflow $CellShape $ItemId)) {
        return
    }

    $targetRange = $null
    try {
        # Preserve the cell's existing wrap setting and change only the
        # translated paragraph inside this cell.
        $targetRange = $CellShape.TextFrame2.TextRange.Paragraphs(
            $ParagraphIndex,
            1
        )
        $targetRange.Font.Spacing = -0.3
        if ($OriginalFontSize -gt 0) {
            $minimumSize = $OriginalFontSize * 0.8
            $currentSize = $OriginalFontSize
            while (
                (Test-TextOverflow $CellShape $ItemId) -and
                ($currentSize - 0.5) -ge $minimumSize
            ) {
                $currentSize -= 0.5
                $targetRange.Font.Size = $currentSize
            }
        }
    }
    catch {
        Write-Warning (
            "QA: table-cell fit failed for '$ItemId': $($_.Exception.Message)"
        )
    }
    finally {
        Release-ComObject $targetRange
    }

    if (Test-TextOverflow $CellShape $ItemId) {
        Write-Warning "QA: unresolved table-cell overflow for '$ItemId'."
    }
}

function Apply-ParagraphTranslation {
    param(
        $TextShape,
        $Item,
        [int]$ParagraphIndex,
        [switch]$TableCell,
        [switch]$DeferFit
    )
    if ([string]::IsNullOrWhiteSpace([string]$Item.translation)) {
        throw "Manifest item '$($Item.id)' has an empty translation."
    }

    $textRange = $null
    $paragraphs = $null
    $paragraph = $null
    try {
        $textRange = $TextShape.TextFrame.TextRange
        $paragraphs = $textRange.Paragraphs()
        if (
            $paragraphIndex -lt 1 -or
            $paragraphIndex -gt $paragraphs.Count
        ) {
            throw "Manifest item '$($Item.id)' references a missing paragraph."
        }
        $paragraph = $textRange.Paragraphs($ParagraphIndex, 1)
        $currentText = [string]$paragraph.Text
        $currentNormalized = (
            $currentText -replace "[\r\n\v]+$", ""
        ).Trim()
        $expectedNormalized = (
            [string]$Item.source_text -replace "[\r\n\v]+$", ""
        ).Trim()
        if ($currentNormalized -cne $expectedNormalized) {
            throw "Source text mismatch for '$($Item.id)'."
        }

        $originalFontSize = [double]$paragraph.Font.Size
        $terminator = [regex]::Match(
            $currentText,
            "[\r\n\v]+$"
        ).Value
        $translation = [string]$Item.translation
        $translation = $translation -replace "\r?\n", ([char]11)
        $contentLength = [int]$paragraph.Length - [int]$terminator.Length
        if ($contentLength -lt 1) {
            throw "Manifest item '$($Item.id)' has no replaceable paragraph content."
        }
        $contentRange = $null
        try {
            # Keep PowerPoint's existing paragraph marker. Replacing the full
            # paragraph creates duplicate markers and blank paragraphs.
            $contentRange = $paragraph.Characters(1, $contentLength)
            $contentRange.Text = $translation
        }
        finally {
            Release-ComObject $contentRange
        }

        if ($DeferFit) {
            return
        }
        if ($TableCell) {
            Apply-LocalTableCellTextFit `
                $TextShape `
                $ParagraphIndex `
                $originalFontSize `
                ([string]$Item.id)
        }
        else {
            Apply-LocalTextFit `
                $TextShape `
                $ParagraphIndex `
                $originalFontSize `
                ([string]$Item.id)
        }
    }
    finally {
        Release-ComObject $paragraph
        Release-ComObject $paragraphs
        Release-ComObject $textRange
    }
}

function Apply-TranslationManifest {
    param(
        $Presentation,
        [string]$Path
    )
    $manifestFullPath = Resolve-ExistingPath $Path
    $manifest = Get-Content -LiteralPath $manifestFullPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$manifest.schema_version -ne 2) {
        throw "Manifest schema_version must be 2: $manifestFullPath"
    }
    if ($null -eq $manifest.occurrences -or $null -eq $manifest.translation_units) {
        throw "Manifest requires occurrences and translation_units arrays: $manifestFullPath"
    }

    $unitsById = @{}
    foreach ($unit in @($manifest.translation_units)) {
        $unitId = [string]$unit.id
        if ([string]::IsNullOrWhiteSpace($unitId) -or $unitsById.ContainsKey($unitId)) {
            throw "Manifest contains an invalid or duplicate translation unit id '$unitId'."
        }
        if ([string]::IsNullOrWhiteSpace([string]$unit.translation)) {
            throw "Translation unit '$unitId' has an empty translation."
        }
        $unitsById[$unitId] = $unit
    }

    $manifestItems = @()
    foreach ($occurrence in @($manifest.occurrences)) {
        $unitId = [string]$occurrence.translation_unit_id
        if (-not $unitsById.ContainsKey($unitId)) {
            throw "Occurrence '$($occurrence.id)' references unknown translation unit '$unitId'."
        }
        $unit = $unitsById[$unitId]
        if ([string]$occurrence.source_text -cne [string]$unit.source_text) {
            throw "Occurrence '$($occurrence.id)' differs from translation unit '$unitId'."
        }
        $location = [ordered]@{
            slide = [int]$occurrence.slide_index
            shape_id = [int]$occurrence.shape_id
            paragraph = [int]$occurrence.paragraph_index
        }
        if ([string]$occurrence.kind -eq "ppt_table_cell") {
            $location.row = [int]$occurrence.row
            $location.column = [int]$occurrence.column
        }
        $manifestItems += [pscustomobject]@{
            id = [string]$occurrence.id
            kind = [string]$occurrence.kind
            source_text = [string]$occurrence.source_text
            translation = [string]$unit.translation
            location = [pscustomobject]$location
        }
    }

    $resolvedItems = @()
    foreach ($item in $manifestItems) {
        $kind = [string]$item.kind
        $location = $item.location
        switch ($kind) {
            "ppt_paragraph" {
                if ($null -eq $location) {
                    throw "Manifest item '$($item.id)' has no typed location."
                }
                $slideIndex = [int]$location.slide
                $shapeId = [int]$location.shape_id
                $paragraphIndex = [int]$location.paragraph
                $row = 0
                $column = 0
            }
            "ppt_table_cell" {
                if ($null -eq $location) {
                    throw "Manifest item '$($item.id)' has no typed location."
                }
                $slideIndex = [int]$location.slide
                $shapeId = [int]$location.shape_id
                $paragraphIndex = [int]$location.paragraph
                $row = [int]$location.row
                $column = [int]$location.column
            }
            default {
                throw "Unsupported manifest kind '$kind' for '$($item.id)'."
            }
        }
        if (
            $slideIndex -lt 1 -or
            $shapeId -lt 1 -or
            $paragraphIndex -lt 1 -or
            ($kind -eq "ppt_table_cell" -and ($row -lt 1 -or $column -lt 1))
        ) {
            throw "Manifest item '$($item.id)' has an invalid location."
        }
        $resolvedItems += [pscustomobject]@{
            Item = $item
            Kind = $kind
            Slide = $slideIndex
            ShapeId = $shapeId
            Row = $row
            Column = $column
            Paragraph = $paragraphIndex
            TargetKey = (
                "$slideIndex|$shapeId|$kind|$row|$column"
            )
        }
    }

    $groups = $resolvedItems | Group-Object TargetKey
    $shapeIndexesBySlide = @{}
    $slidesIndexed = 0
    $fitOperations = 0
    foreach ($group in $groups) {
        $items = @(
            $group.Group |
                Sort-Object -Property @{
                    Expression = "Paragraph"
                    Descending = $true
                }
        )
        $slideIndex = [int]$items[0].Slide
        $shapeId = [int]$items[0].ShapeId
        $kind = [string]$items[0].Kind
        if ($slideIndex -lt 1 -or $slideIndex -gt $Presentation.Slides.Count) {
            throw "Manifest references missing slide $slideIndex."
        }

        $slide = $Presentation.Slides.Item($slideIndex)
        $shape = $null
        $table = $null
        $cell = $null
        $cellShape = $null
        $originalShapeGeometry = $null
        $originalFontSize = 0.0
        try {
            if (-not $shapeIndexesBySlide.ContainsKey($slideIndex)) {
                $shapeIndexesBySlide[$slideIndex] = Get-ShapeCollectionIndexMap $slide
                $slidesIndexed++
            }
            $shapeIndexMap = $shapeIndexesBySlide[$slideIndex]
            if (-not $shapeIndexMap.ContainsKey($shapeId)) {
                throw "Manifest references missing shape $shapeId on slide $slideIndex."
            }
            $shape = $slide.Shapes.Item([int]$shapeIndexMap[$shapeId])

            if ($kind -eq "ppt_table_cell") {
                if (-not (Test-ShapeHasTable $shape)) {
                    throw (
                        "Shape $shapeId on slide $slideIndex no longer " +
                        "contains a native table."
                    )
                }
                $table = $shape.Table
                $row = [int]$items[0].Row
                $column = [int]$items[0].Column
                if (
                    $row -gt $table.Rows.Count -or
                    $column -gt $table.Columns.Count
                ) {
                    throw (
                        "Manifest item '$($items[0].Item.id)' references " +
                        "a missing table cell."
                    )
                }
                $cell = $table.Cell($row, $column)
                $cellShape = $cell.Shape
                if (-not (Test-ShapeHasText $cellShape)) {
                    throw (
                        "Table cell r$row`:c$column in shape $shapeId on " +
                        "slide $slideIndex no longer contains editable text."
                    )
                }
                $originalFontSize = [double]$cellShape.TextFrame.TextRange.Font.Size
            }
            elseif (-not (Test-ShapeHasText $shape)) {
                throw "Shape $shapeId on slide $slideIndex no longer contains editable text."
            }
            else {
                $originalShapeGeometry = [ordered]@{
                    Left = [double]$shape.Left
                    Top = [double]$shape.Top
                    Width = [double]$shape.Width
                    Height = [double]$shape.Height
                }
                $originalFontSize = [double]$shape.TextFrame.TextRange.Font.Size
            }

            foreach ($resolvedItem in $items) {
                $targetShape = if ($kind -eq "ppt_table_cell") {
                    $cellShape
                }
                else {
                    $shape
                }
                Apply-ParagraphTranslation `
                    $targetShape `
                    $resolvedItem.Item `
                    ([int]$resolvedItem.Paragraph) `
                    -TableCell:($kind -eq "ppt_table_cell") `
                    -DeferFit
            }
            if ($kind -eq "ppt_table_cell") {
                Apply-LocalTableCellTextFit `
                    $cellShape 1 $originalFontSize ([string]$items[0].Item.id)
            }
            else {
                Apply-LocalTextFit `
                    $shape 1 $originalFontSize ([string]$items[0].Item.id)
            }
            $fitOperations++
            if ($null -ne $originalShapeGeometry) {
                $shape.Left = $originalShapeGeometry.Left
                $shape.Top = $originalShapeGeometry.Top
                $shape.Width = $originalShapeGeometry.Width
                $shape.Height = $originalShapeGeometry.Height
            }
        }
        finally {
            Release-ComObject $cellShape
            Release-ComObject $cell
            Release-ComObject $table
            Release-ComObject $shape
            Release-ComObject $slide
        }
    }

    return [ordered]@{
        occurrences = @($manifest.occurrences).Count
        translation_units = @($manifest.translation_units).Count
        slides_indexed = $slidesIndexed
        target_shapes = @($groups).Count
        fit_operations = $fitOperations
    }
}

function Convert-RgbHexToOfficeColor {
    param([string]$Value, [string]$FieldName)
    if ([string]$Value -notmatch '^[0-9A-Fa-f]{6}$') {
        throw "Overlay $FieldName must contain exactly six hexadecimal digits."
    }
    $red = [Convert]::ToInt32($Value.Substring(0, 2), 16)
    $green = [Convert]::ToInt32($Value.Substring(2, 2), 16)
    $blue = [Convert]::ToInt32($Value.Substring(4, 2), 16)
    return [int]($red + (256 * $green) + (65536 * $blue))
}

function Get-TaggedOverlayShape {
    param($Slide, [string]$TagName, [string]$TagValue)
    for ($shapeIndex = 1; $shapeIndex -le $Slide.Shapes.Count; $shapeIndex++) {
        $candidate = $Slide.Shapes.Item($shapeIndex)
        try {
            if ([string]$candidate.Tags($TagName) -ceq $TagValue) {
                return $candidate
            }
        }
        catch {}
        Release-ComObject $candidate
    }
    return $null
}

function Apply-OverlayManifest {
    param($Presentation, [string]$Path)

    $manifestFullPath = Resolve-ExistingPath $Path
    $manifest = Get-Content -LiteralPath $manifestFullPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $manifest.overlays) {
        throw "Overlay manifest contains no overlays array: $manifestFullPath"
    }

    $legalLocations = @{}
    foreach ($record in @($manifest.legal_evidence)) {
        $legalLocations["$([int]$record.location.page_or_slide)/$([int]$record.location.host_shape_id)"] = $true
    }

    foreach ($item in @($manifest.overlays)) {
        $itemId = [string]$item.id
        if ([string]::IsNullOrWhiteSpace($itemId) -or [string]$item.kind -cne "office_overlay") {
            throw "Overlay entries require a non-empty id and kind 'office_overlay'."
        }
        $translation = [string]$item.translation
        if ([string]::IsNullOrWhiteSpace($translation)) {
            throw "Overlay '$itemId' has empty text."
        }

        $slideIndex = [int]$item.location.page_or_slide
        $hostShapeId = [int]$item.location.host_shape_id
        $regionId = [string]$item.location.region_id
        if ($slideIndex -lt 1 -or $slideIndex -gt $Presentation.Slides.Count -or
            $hostShapeId -lt 1 -or [string]::IsNullOrWhiteSpace($regionId)) {
            throw "Overlay '$itemId' has an invalid location."
        }
        if ($legalLocations.ContainsKey("$slideIndex/$hostShapeId")) {
            throw "Overlay '$itemId' targets legal-evidence and cannot be applied."
        }

        $x = [double]$item.region.x
        $y = [double]$item.region.y
        $widthRatio = [double]$item.region.w
        $heightRatio = [double]$item.region.h
        if ($x -lt 0 -or $y -lt 0 -or $widthRatio -le 0 -or $heightRatio -le 0 -or
            ($x + $widthRatio) -gt 1 -or ($y + $heightRatio) -gt 1) {
            throw "Overlay '$itemId' has a region outside its host."
        }

        $backgroundMode = "solid"
        if ($null -ne $item.background -and
            -not [string]::IsNullOrWhiteSpace([string]$item.background.mode)) {
            $backgroundMode = [string]$item.background.mode
        }
        if ($backgroundMode -notin @("solid", "transparent")) {
            throw "Overlay '$itemId' has unsupported background mode '$backgroundMode'."
        }

        $fillColor = Convert-RgbHexToOfficeColor ([string]$item.style.fill_rgb) "fill_rgb"
        $textColor = Convert-RgbHexToOfficeColor ([string]$item.style.text_rgb) "text_rgb"
        $fontName = [string]$item.style.font_name
        $fontSize = [double]$item.style.font_size_pt
        $alignment = switch ([string]$item.style.align) {
            "left" { 1 }
            "center" { 2 }
            "right" { 3 }
            default { throw "Overlay '$itemId' has an invalid alignment." }
        }
        if ([string]::IsNullOrWhiteSpace($fontName) -or $fontSize -le 0 -or
            $item.style.bold -isnot [bool]) {
            throw "Overlay '$itemId' has invalid font styling."
        }

        $slide = $Presentation.Slides.Item($slideIndex)
        $overlayShape = $null
        $hostShape = $null
        $textRange = $null
        try {
            # Resolve the overlay before the host: releasing candidates while
            # scanning PowerPoint's COM collection can invalidate another RCW
            # for the same shape.
            $overlayShape = Get-TaggedOverlayShape $slide "maltipal_translate_overlay" $itemId
            $hostShape = Get-ShapeById $slide $hostShapeId
            if ($null -eq $hostShape) {
                throw "Overlay '$itemId' references missing host shape $hostShapeId on slide $slideIndex."
            }

            $left = [double]$hostShape.Left + ($x * [double]$hostShape.Width)
            $top = [double]$hostShape.Top + ($y * [double]$hostShape.Height)
            $width = $widthRatio * [double]$hostShape.Width
            $height = $heightRatio * [double]$hostShape.Height
            if ($null -eq $overlayShape) {
                # 1 = msoShapeRectangle
                $overlayShape = $slide.Shapes.AddShape(1, $left, $top, $width, $height)
            }
            $overlayShape.LockAspectRatio = 0
            $overlayShape.Left = $left
            $overlayShape.Top = $top
            $overlayShape.Width = $width
            $overlayShape.Height = $height
            if ($backgroundMode -ne "solid") {
                $overlayShape.Fill.Visible = 0
            }
            else {
                $overlayShape.Fill.Visible = -1
                $overlayShape.Fill.Solid()
                $overlayShape.Fill.ForeColor.RGB = $fillColor
                $overlayShape.Fill.Transparency = 0
            }
            $overlayShape.Line.Visible = 0
            $overlayShape.TextFrame.MarginLeft = 0
            $overlayShape.TextFrame.MarginTop = 0
            $overlayShape.TextFrame.MarginRight = 0
            $overlayShape.TextFrame.MarginBottom = 0
            $overlayShape.TextFrame.TextRange.Text = $translation
            $textRange = $overlayShape.TextFrame.TextRange
            $textRange.Font.Name = $fontName
            $textRange.Font.Size = $fontSize
            $textRange.Font.Bold = if ([bool]$item.style.bold) { -1 } else { 0 }
            $textRange.Font.Color.RGB = $textColor
            $textRange.ParagraphFormat.Alignment = $alignment
            $overlayShape.Tags.Add("maltipal_translate_overlay", $itemId)
            $overlayShape.ZOrder(0)
        }
        finally {
            Release-ComObject $textRange
            Release-ComObject $hostShape
            Release-ComObject $overlayShape
            Release-ComObject $slide
        }
    }
}

function Get-InspectionReport {
    param($Presentation)

    $textShapeCount = 0
    $pictureCount = 0
    $shapeCount = 0
    $notesCount = 0
    $animationCount = 0
    $tableCount = 0
    $tableRowCount = 0
    $tableCellCount = 0
    $slides = @()

    for ($slideIndex = 1; $slideIndex -le $Presentation.Slides.Count; $slideIndex++) {
        $slide = $Presentation.Slides.Item($slideIndex)
        $slideTextShapes = 0
        $slidePictures = 0
        $slideShapes = @()
        $slideTables = @()
        try {
            for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
                $shape = $slide.Shapes.Item($shapeIndex)
                try {
                    $shapeCount++
                    $hasText = Test-ShapeHasText $shape
                    if ($hasText) {
                        $textShapeCount++
                        $slideTextShapes++
                    }
                    if ($shape.Type -eq 13 -or $shape.Type -eq 11) {
                        $pictureCount++
                        $slidePictures++
                    }
                    if (Test-ShapeHasTable $shape) {
                        $table = $null
                        try {
                            $table = $shape.Table
                            $rows = [int]$table.Rows.Count
                            $columns = [int]$table.Columns.Count
                            $cellAnchors = @(Get-TableCellAnchors $shape)
                            $cellCount = $cellAnchors.Count
                            $tableCount++
                            $tableRowCount += $rows
                            $tableCellCount += $cellCount
                            $slideTables += [ordered]@{
                                shape_id = [int]$shape.Id
                                rows = $rows
                                columns = $columns
                                left = [double]$shape.Left
                                top = [double]$shape.Top
                                width = [double]$shape.Width
                                height = [double]$shape.Height
                                cell_count = $cellCount
                            }
                        }
                        finally {
                            Release-ComObject $table
                        }
                    }
                    $slideShapes += [ordered]@{
                        id = [int]$shape.Id
                        name = [string]$shape.Name
                        type = [int]$shape.Type
                        z_order = [int]$shape.ZOrderPosition
                        left = [double]$shape.Left
                        top = [double]$shape.Top
                        width = [double]$shape.Width
                        height = [double]$shape.Height
                        has_text = [bool]$hasText
                    }
                }
                finally {
                    Release-ComObject $shape
                }
            }

            try {
                $notesPage = $slide.NotesPage
                for ($n = 1; $n -le $notesPage.Shapes.Count; $n++) {
                    $noteShape = $notesPage.Shapes.Item($n)
                    try {
                        if ((Test-ShapeHasText $noteShape) -and
                            -not [string]::IsNullOrWhiteSpace([string]$noteShape.TextFrame.TextRange.Text)) {
                            $notesCount++
                        }
                    }
                    finally {
                        Release-ComObject $noteShape
                    }
                }
            }
            catch {
                # Some legacy decks expose no notes page through COM.
            }
            finally {
                Release-ComObject $notesPage
            }

            try {
                $sequence = $slide.TimeLine.MainSequence
                $animationCount += [int]$sequence.Count
            }
            catch {
                # No animation sequence.
            }
            finally {
                Release-ComObject $sequence
            }

            $slides += [ordered]@{
                index = $slideIndex
                title = (Get-SlideTitle $slide)
                shapes = [int]$slide.Shapes.Count
                text_shapes = $slideTextShapes
                pictures = $slidePictures
                shape_inventory = $slideShapes
                table_inventory = $slideTables
            }
        }
        finally {
            Release-ComObject $slide
        }
    }

    return [ordered]@{
        source_file = [string]$Presentation.FullName
        slides = [int]$Presentation.Slides.Count
        slide_width = [double]$Presentation.PageSetup.SlideWidth
        slide_height = [double]$Presentation.PageSetup.SlideHeight
        shapes = $shapeCount
        text_shapes = $textShapeCount
        pictures = $pictureCount
        note_text_shapes = $notesCount
        animations = $animationCount
        tables = $tableCount
        table_rows = $tableRowCount
        table_cells = $tableCellCount
        slide_inventory = $slides
    }
}

function Get-VerificationObjectKey {
    param([int]$SlideIndex, [int[]]$GroupPath, [int]$ShapeId)
    $parts = @("slide:$SlideIndex")
    foreach ($groupId in @($GroupPath)) { $parts += "group:$groupId" }
    $parts += "shape:$ShapeId"
    return $parts -join "/"
}

function Add-VerificationShapeAuditRecord {
    param(
        $Shape,
        [int]$SlideIndex,
        [int[]]$GroupPath,
        [hashtable]$Untagged,
        [System.Collections.ArrayList]$Overlays
    )

    $textRange = $null
    try {
        $shapeId = [int]$Shape.Id
        $overlayTagValue = ""
        $patchTagValue = ""
        try { $overlayTagValue = [string]$Shape.Tags("maltipal_translate_overlay") }
        catch {}
        try { $patchTagValue = [string]$Shape.Tags("maltipal_translate_patch") }
        catch {}
        $tagValue = if (-not [string]::IsNullOrWhiteSpace($overlayTagValue)) {
            $overlayTagValue
        }
        else { $patchTagValue }
        $tagKind = if (-not [string]::IsNullOrWhiteSpace($overlayTagValue)) {
            "overlay"
        }
        elseif (-not [string]::IsNullOrWhiteSpace($patchTagValue)) {
            "patch"
        }
        else { "" }
        $record = [pscustomobject]@{
            Key = Get-VerificationObjectKey $SlideIndex $GroupPath $shapeId
            Slide = $SlideIndex
            Id = $shapeId
            Type = [int]$Shape.Type
            GroupPath = @($GroupPath)
            Left = [double]$Shape.Left
            Top = [double]$Shape.Top
            Width = [double]$Shape.Width
            Height = [double]$Shape.Height
            Tag = $tagValue
            Kind = $tagKind
            HasTextFrame = [int]$Shape.HasTextFrame
            HasText = 0
            Text = ""
        }
        if (-not [string]::IsNullOrWhiteSpace($tagValue)) {
            if ($tagKind -eq "overlay" -and $record.HasTextFrame -eq -1) {
                $record.HasText = [int]$Shape.TextFrame.HasText
                if ($record.HasText -eq -1) {
                    $textRange = $Shape.TextFrame.TextRange
                    $record.Text = [string]$textRange.Text
                }
            }
            [void]$Overlays.Add($record)
        }
        else {
            $Untagged[$record.Key] = $record
        }
    }
    finally { Release-ComObject $textRange }

    if ([int]$Shape.Type -ne 6) { return }
    $groupItems = $null
    try {
        $groupItems = $Shape.GroupItems
        $nextPath = @($GroupPath) + @([int]$Shape.Id)
        for ($childIndex = 1; $childIndex -le $groupItems.Count; $childIndex++) {
            $child = $groupItems.Item($childIndex)
            try {
                Add-VerificationShapeAuditRecord `
                    $child $SlideIndex $nextPath $Untagged $Overlays
            }
            finally { Release-ComObject $child }
        }
    }
    finally { Release-ComObject $groupItems }
}

function Get-VerificationShapeAudit {
    param($Presentation)

    $untagged = @{}
    $overlays = [System.Collections.ArrayList]::new()
    for ($slideIndex = 1; $slideIndex -le $Presentation.Slides.Count; $slideIndex++) {
        $slide = $Presentation.Slides.Item($slideIndex)
        try {
            for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
                $shape = $slide.Shapes.Item($shapeIndex)
                try {
                    Add-VerificationShapeAuditRecord `
                        $shape $slideIndex @() $untagged $overlays
                }
                finally { Release-ComObject $shape }
            }
        }
        finally { Release-ComObject $slide }
    }

    return [pscustomobject]@{
        Untagged = $untagged
        Overlays = @($overlays)
    }
}

function Compare-VerificationShapeAudits {
    param(
        $SourceAudit,
        $TranslatedAudit,
        [string[]]$ExpectedHostKeys = @()
    )

    $differences = @()
    $reportedHostGeometry = @{}
    foreach ($key in @($SourceAudit.Untagged.Keys)) {
        if (-not $TranslatedAudit.Untagged.ContainsKey($key)) {
            $differences += [ordered]@{
                property = "untagged_shape_removed"
                shape = $key
            }
            continue
        }
        $sourceShape = $SourceAudit.Untagged[$key]
        $translatedShape = $TranslatedAudit.Untagged[$key]
        if ([int]$sourceShape.Type -ne [int]$translatedShape.Type) {
            $differences += [ordered]@{
                property = "untagged_shape_type"
                shape = $key
                source = [int]$sourceShape.Type
                translated = [int]$translatedShape.Type
            }
        }
        if ([int]$sourceShape.Type -in @(7, 10, 11, 13)) {
            $hostGeometryChanged = $false
            foreach ($name in @("Left", "Top", "Width", "Height")) {
                if ([Math]::Abs([double]$sourceShape.$name - [double]$translatedShape.$name) -gt 0.01) {
                    $hostGeometryChanged = $true
                }
            }
            if ($hostGeometryChanged) {
                $differences += [ordered]@{
                    property = "host_shape_geometry"
                    shape = $key
                }
                $reportedHostGeometry[$key] = $true
            }
        }
    }
    foreach ($key in @($TranslatedAudit.Untagged.Keys)) {
        if (-not $SourceAudit.Untagged.ContainsKey($key)) {
            $differences += [ordered]@{
                property = "untagged_shape_added"
                shape = $key
            }
        }
    }

    # Host invariants are independent of whether the translated overlay still
    # exists. Manifest-declared hosts therefore remain protected even when a
    # tagged overlay was removed (an otherwise allowed tagged count change).
    $hostKeys = @{}
    foreach ($key in @($ExpectedHostKeys)) {
        if (-not [string]::IsNullOrWhiteSpace($key)) { $hostKeys[$key] = $true }
    }
    foreach ($audit in @($SourceAudit, $TranslatedAudit)) {
        foreach ($overlay in @($audit.Overlays)) {
            $tagMatch = [regex]::Match(
                [string]$overlay.Tag,
                '^ppt/slide:(\d+)/shape:(\d+)/region:([^/]+)$'
            )
            if ($tagMatch.Success) {
                $hostKeys[
                    "slide:$([int]$tagMatch.Groups[1].Value)/shape:$([int]$tagMatch.Groups[2].Value)"
                ] = $true
            }
        }
    }
    foreach ($hostKey in @($hostKeys.Keys)) {
        if (-not $SourceAudit.Untagged.ContainsKey($hostKey) -or
            -not $TranslatedAudit.Untagged.ContainsKey($hostKey)) {
            $differences += [ordered]@{
                property = "host_shape_missing"
                shape = $hostKey
            }
            continue
        }
        $sourceHostShape = $SourceAudit.Untagged[$hostKey]
        $translatedHostShape = $TranslatedAudit.Untagged[$hostKey]
        $hostGeometryChanged = $false
        foreach ($name in @("Left", "Top", "Width", "Height")) {
            if ([Math]::Abs([double]$sourceHostShape.$name - [double]$translatedHostShape.$name) -gt 0.01) {
                $hostGeometryChanged = $true
            }
        }
        if ($hostGeometryChanged -and -not $reportedHostGeometry.ContainsKey($hostKey)) {
            $differences += [ordered]@{
                property = "host_shape_geometry"
                shape = $hostKey
            }
            $reportedHostGeometry[$hostKey] = $true
        }
    }

    $seenTags = @{}
    foreach ($overlay in @($TranslatedAudit.Overlays)) {
        $tagKey = "$([string]$overlay.Kind)|$([string]$overlay.Tag)"
        if ($seenTags.ContainsKey($tagKey)) {
            $differences += [ordered]@{
                property = "$([string]$overlay.Kind)_duplicate_tag"
                overlay = $overlay.Tag
            }
        }
        $seenTags[$tagKey] = $true

        $match = [regex]::Match(
            [string]$overlay.Tag,
            '^ppt/slide:(\d+)/shape:(\d+)/region:([^/]+)$'
        )
        if (-not $match.Success) {
            $differences += [ordered]@{
                property = "overlay_invalid_tag"
                overlay = $overlay.Tag
            }
            continue
        }
        $hostSlide = [int]$match.Groups[1].Value
        $hostShapeId = [int]$match.Groups[2].Value
        $hostKey = "slide:$hostSlide/shape:$hostShapeId"
        if ($overlay.Slide -ne $hostSlide -or -not $TranslatedAudit.Untagged.ContainsKey($hostKey)) {
            $differences += [ordered]@{
                property = "overlay_missing_host"
                overlay = $overlay.Tag
                host = $hostKey
            }
            continue
        }

        if ([string]$overlay.Kind -eq "overlay") {
            if ([int]$overlay.HasTextFrame -ne -1) {
                $differences += [ordered]@{
                    property = "overlay_uneditable"
                    overlay = $overlay.Tag
                }
            }
            elseif ([int]$overlay.HasText -ne -1 -or [string]::IsNullOrWhiteSpace([string]$overlay.Text)) {
                $differences += [ordered]@{
                    property = "overlay_empty_text"
                    overlay = $overlay.Tag
                }
            }
        }
        elseif ([string]$overlay.Kind -eq "patch" -and [int]$overlay.Type -ne 13) {
            $differences += [ordered]@{
                property = "patch_invalid_type"
                overlay = $overlay.Tag
            }
        }

        $hostShape = $TranslatedAudit.Untagged[$hostKey]
        $tolerance = 0.13
        if ($overlay.Left -lt ($hostShape.Left - $tolerance) -or
            $overlay.Top -lt ($hostShape.Top - $tolerance) -or
            ($overlay.Left + $overlay.Width) -gt ($hostShape.Left + $hostShape.Width + $tolerance) -or
            ($overlay.Top + $overlay.Height) -gt ($hostShape.Top + $hostShape.Height + $tolerance)) {
            $differences += [ordered]@{
                property = "overlay_out_of_host"
                overlay = $overlay.Tag
                host = $hostKey
            }
        }
    }

    return $differences
}

function Add-NonstandardShapeInventory {
    param(
        $Shape,
        [int]$SlideIndex,
        [int[]]$GroupPath,
        [Nullable[int]]$HostGroupId,
        [System.Collections.ArrayList]$Audit,
        [System.Collections.ArrayList]$Nonstandard,
        [hashtable]$ScreeningByShape,
        [string]$PreviewDirectory,
        [string]$ProjectRoot
    )

    $shapeId = [int]$Shape.Id
    $shapeType = [int]$Shape.Type
    $insideGroup = @($GroupPath).Count -gt 0
    $parentGroupId = if ($insideGroup) { [int]$GroupPath[-1] } else { $null }
    $hasText = Test-ShapeHasText $Shape
    $hasTable = Test-ShapeHasTable $Shape
    $hasChart = $false
    try { $hasChart = ([int]$Shape.HasChart -eq -1) } catch { }

    $isPicture = $shapeType -eq 11 -or $shapeType -eq 13
    $isOle = $shapeType -eq 7 -or $shapeType -eq 10
    $isDiagram = $shapeType -eq 21 -or $shapeType -eq 24
    $isChart = $shapeType -eq 3 -or $hasChart
    $isUnsupportedText = ($insideGroup -and ($hasText -or $hasTable)) -or
        ($hasText -and $shapeType -notin @(1, 14, 17, 19))
    $isNonstandard = $isPicture -or $isOle -or $isDiagram -or $isChart -or $isUnsupportedText

    $keyParts = @("slide:$SlideIndex")
    foreach ($groupId in @($GroupPath)) { $keyParts += "group:$groupId" }
    $keyParts += "shape:$shapeId"
    $objectKey = $keyParts -join "/"

    $progId = $null
    $classification = "no_text_detected"
    $disposition = $null
    if ($isPicture) {
        if ($SlideIndex -eq 17 -and $shapeId -in @(19462, 19463) -and -not $insideGroup) {
            $classification = "legal_evidence"
            $disposition = "legal_evidence"
        }
        else {
            $classification = "picture_requires_screening"
            $screeningKey = "$SlideIndex/$shapeId"
            $screeningStatus = if ($ScreeningByShape.ContainsKey($screeningKey)) {
                $ScreeningByShape[$screeningKey]
            }
            else { "" }
            if ($SlideIndex -eq 8 -and $shapeId -eq 10247 -and -not $insideGroup) {
                $disposition = "safe_overlay"
            }
            elseif ($screeningStatus -eq "screened_no_visible_source_text" -and -not $insideGroup) {
                $disposition = "no_text_detected"
            }
            else { $disposition = "manual_review" }
        }
    }
    elseif ($isOle) {
        $ownerAvailable = $false
        $oleFormat = $null
        $ownerObject = $null
        try {
            $oleFormat = $Shape.OLEFormat
            $progId = [string]$oleFormat.ProgID
            try {
                $ownerObject = $oleFormat.Object
                $ownerAvailable = $null -ne $ownerObject
            }
            catch { $ownerAvailable = $false }
        }
        catch { $ownerAvailable = $false }
        finally {
            Release-ComObject $ownerObject
            Release-ComObject $oleFormat
        }
        $classification = if ($ownerAvailable) { "ole_owner_available" } else { "ole_owner_unavailable" }
        $disposition = "manual_review"
    }
    elseif ($isDiagram -or $isChart) {
        $classification = "diagram_unexposed"
        $disposition = "manual_review"
    }
    elseif ($isUnsupportedText) {
        $classification = "unsupported_text_object"
        $disposition = "manual_review"
    }
    elseif ($hasTable) { $classification = "supported_table" }
    elseif ($hasText) { $classification = "supported_text" }

    $previewPath = $null
    $previewSha256 = $null
    $previewBytes = $null
    $previewExportedUtc = $null
    if ($isNonstandard) {
        $groupSuffix = if ($insideGroup) {
            "-group-" + ((@($GroupPath) | ForEach-Object { [string]$_ }) -join "-")
        }
        else { "" }
        $previewFileName = "slide-{0:D2}{1}-shape-{2}.png" -f $SlideIndex, $groupSuffix, $shapeId
        $previewFullPath = Join-Path $PreviewDirectory $previewFileName
        if (Test-Path -LiteralPath $previewFullPath -PathType Leaf) {
            Remove-Item -LiteralPath $previewFullPath -Force
        }
        # 2 = ppShapeFormatPNG. Export refreshes a disposable preview only.
        $Shape.Export($previewFullPath, 2)
        $previewFile = Get-Item -LiteralPath $previewFullPath
        $previewPath = Get-RelativePath $ProjectRoot $previewFullPath
        $previewSha256 = (Get-FileHash -LiteralPath $previewFullPath -Algorithm SHA256).Hash
        $previewBytes = [long]$previewFile.Length
        $previewExportedUtc = $previewFile.LastWriteTimeUtc.ToString("o")
    }

    $record = [ordered]@{
        object_key = $objectKey
        slide_index = $SlideIndex
        shape_id = $shapeId
        name = [string]$Shape.Name
        type = $shapeType
        progid = $progId
        group_path = @($GroupPath)
        host_group_id = $HostGroupId
        parent_group_id = $parentGroupId
        geometry = [ordered]@{
            left = [double]$Shape.Left
            top = [double]$Shape.Top
            width = [double]$Shape.Width
            height = [double]$Shape.Height
        }
        preview_path = $previewPath
        preview_sha256 = $previewSha256
        preview_bytes = $previewBytes
        preview_exported_utc = $previewExportedUtc
        classification = $classification
        disposition = $disposition
    }
    [void]$Audit.Add($record)
    if ($isNonstandard) { [void]$Nonstandard.Add($record) }

    if ($shapeType -eq 6) {
        $groupItems = $null
        try {
            $groupItems = $Shape.GroupItems
            $nextPath = @($GroupPath) + @($shapeId)
            $nextHost = if ($null -eq $HostGroupId) { $shapeId } else { [int]$HostGroupId }
            for ($groupIndex = 1; $groupIndex -le $groupItems.Count; $groupIndex++) {
                $child = $groupItems.Item($groupIndex)
                try {
                    Add-NonstandardShapeInventory `
                        $child $SlideIndex $nextPath $nextHost $Audit $Nonstandard `
                        $ScreeningByShape $PreviewDirectory $ProjectRoot
                }
                finally { Release-ComObject $child }
            }
        }
        finally { Release-ComObject $groupItems }
    }
}

function Get-NonstandardInventory {
    param(
        $Presentation,
        [string]$SourceFile,
        [string]$PreviewDirectory,
        [string]$ProjectRoot,
        [string]$ScreeningManifestPath
    )

    $screeningByShape = @{}
    if (Test-Path -LiteralPath $ScreeningManifestPath -PathType Leaf) {
        $screeningManifest = Get-Content -LiteralPath $ScreeningManifestPath -Raw | ConvertFrom-Json
        foreach ($image in @($screeningManifest.images)) {
            $key = "$([int]$image.slide_index)/$([int]$image.shape_id)"
            $screeningByShape[$key] = [string]$image.status
        }
    }

    $audit = [System.Collections.ArrayList]::new()
    $nonstandard = [System.Collections.ArrayList]::new()
    for ($slideIndex = 1; $slideIndex -le $Presentation.Slides.Count; $slideIndex++) {
        $slide = $Presentation.Slides.Item($slideIndex)
        try {
            for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
                $shape = $slide.Shapes.Item($shapeIndex)
                try {
                    Add-NonstandardShapeInventory `
                        $shape $slideIndex @() $null $audit $nonstandard `
                        $screeningByShape $PreviewDirectory $ProjectRoot
                }
                finally { Release-ComObject $shape }
            }
        }
        finally { Release-ComObject $slide }
    }

    $classificationCounts = [ordered]@{}
    foreach ($record in $audit) {
        $name = [string]$record["classification"]
        if (-not $classificationCounts.Contains($name)) {
            $classificationCounts[$name] = 0
        }
        $classificationCounts[$name] = [int]$classificationCounts[$name] + 1
    }
    $dispositionCounts = [ordered]@{}
    foreach ($record in $nonstandard) {
        $name = [string]$record["disposition"]
        if (-not $dispositionCounts.Contains($name)) {
            $dispositionCounts[$name] = 0
        }
        $dispositionCounts[$name] = [int]$dispositionCounts[$name] + 1
    }

    return [ordered]@{
        source_file = $SourceFile
        format = "powerpoint"
        audit_count = [int]$audit.Count
        nonstandard_count = [int]$nonstandard.Count
        classification_counts = $classificationCounts
        disposition_counts = $dispositionCounts
        audit = $audit
        nonstandard = $nonstandard
    }
}

function Get-TranslationManifest {
    param(
        $Presentation,
        [string]$SourceFile
    )

    $items = @()
    for ($slideIndex = 1; $slideIndex -le $Presentation.Slides.Count; $slideIndex++) {
        $slide = $Presentation.Slides.Item($slideIndex)
        try {
            $slideTitle = (Get-SlideTitle $slide).Trim()
            $orderedShapes = @()
            for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
                $shapeForOrder = $slide.Shapes.Item($shapeIndex)
                try {
                    $orderedShapes += [pscustomobject]@{
                        CollectionIndex = $shapeIndex
                        ZOrder = [int]$shapeForOrder.ZOrderPosition
                    }
                }
                finally {
                    Release-ComObject $shapeForOrder
                }
            }
            $orderedShapes = $orderedShapes | Sort-Object ZOrder, CollectionIndex

            foreach ($shapeOrder in $orderedShapes) {
                $shape = $slide.Shapes.Item($shapeOrder.CollectionIndex)
                try {
                    if (Test-ShapeHasTable $shape) {
                        $shapeId = [int]$shape.Id
                        $cellAnchors = @(
                            Get-TableCellAnchors $shape -IncludeText
                        )
                        foreach ($anchor in $cellAnchors) {
                            $neighboringText = @(
                                Get-TableNeighboringText $cellAnchors $anchor
                            )
                            foreach ($paragraphData in $anchor.Paragraphs) {
                                $paragraphIndex = [int]$paragraphData.Index
                                $items += [ordered]@{
                                    id = (
                                        "ppt/slide:$slideIndex/shape:$shapeId/" +
                                        "table:r$($anchor.Row):c$($anchor.Column)/" +
                                        "paragraph:$paragraphIndex"
                                    )
                                    kind = "ppt_table_cell"
                                    source_text = [string]$paragraphData.SourceText
                                    source_text_normalized = (
                                        [string]$paragraphData.NormalizedText
                                    )
                                    translation = ""
                                    context = [ordered]@{
                                        document_section = $slideTitle
                                        neighboring_text = $neighboringText
                                        shape_name = [string]$shape.Name
                                        z_order = [int]$shape.ZOrderPosition
                                    }
                                    location = [ordered]@{
                                        slide = $slideIndex
                                        shape_id = $shapeId
                                        row = [int]$anchor.Row
                                        column = [int]$anchor.Column
                                        paragraph = $paragraphIndex
                                    }
                                    protected_tokens = @()
                                    slide_index = $slideIndex
                                    shape_id = $shapeId
                                    paragraph_index = $paragraphIndex
                                }
                            }
                        }
                        continue
                    }
                    if (-not (Test-ShapeHasText $shape)) {
                        continue
                    }
                    $textRange = $shape.TextFrame.TextRange
                    try {
                        $paragraphs = $textRange.Paragraphs()
                        try {
                            for ($paragraphIndex = 1; $paragraphIndex -le $paragraphs.Count; $paragraphIndex++) {
                                $paragraph = $textRange.Paragraphs($paragraphIndex, 1)
                                try {
                                    $sourceText = [string]$paragraph.Text
                                    $normalized = ($sourceText -replace "[\r\n\v]+$", "").Trim()
                                    if ([string]::IsNullOrWhiteSpace($normalized)) {
                                        continue
                                    }
                                    $shapeId = [int]$shape.Id
                                    $items += [ordered]@{
                                        id = "ppt/slide:$slideIndex/shape:$shapeId/paragraph:$paragraphIndex"
                                        kind = "ppt_paragraph"
                                        source_text = $sourceText
                                        source_text_normalized = $normalized
                                        translation = ""
                                        context = [ordered]@{
                                            document_section = $slideTitle
                                            neighboring_text = @()
                                            shape_name = [string]$shape.Name
                                            z_order = [int]$shape.ZOrderPosition
                                        }
                                        location = [ordered]@{
                                            slide = $slideIndex
                                            shape_id = $shapeId
                                            paragraph = $paragraphIndex
                                        }
                                        protected_tokens = @()
                                        slide_index = $slideIndex
                                        shape_id = $shapeId
                                        paragraph_index = $paragraphIndex
                                    }
                                }
                                finally {
                                    Release-ComObject $paragraph
                                }
                            }
                        }
                        finally {
                            Release-ComObject $paragraphs
                        }
                    }
                    finally {
                        Release-ComObject $textRange
                    }
                }
                finally {
                    Release-ComObject $shape
                }
            }
        }
        finally {
            Release-ComObject $slide
        }
    }

    return [ordered]@{
        source_file = $SourceFile
        source_language = "zh-CN"
        target_language = "en"
        format = "powerpoint"
        items = $items
    }
}

$inputFullPath = Resolve-ExistingPath $InputPath
$application = $null
$presentation = $null
$windowGuard = New-Object PowerPointWindowGuard
$windowGuard.Start()

try {
    $application = New-Object -ComObject PowerPoint.Application
    # ReadOnly=true, Untitled=false, WithWindow=false
    $presentation = $application.Presentations.Open($inputFullPath, -1, 0, 0)

    switch ($Command) {
        "inspect" {
            $outputFullPath = Resolve-OutputFile $OutputPath
            Write-JsonUtf8 (Get-InspectionReport $presentation) $outputFullPath
        }
        "extract" {
            $outputFullPath = Resolve-OutputFile $OutputPath
            $manifest = Get-TranslationManifest $presentation ([System.IO.Path]::GetFileName($inputFullPath))
            Write-JsonUtf8 $manifest $outputFullPath
        }
        "apply" {
            if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
                throw "ManifestPath is required for command 'apply'."
            }
            $outputFullPath = Resolve-OutputFile $OutputPath
            if ([string]::Equals($inputFullPath, $outputFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to overwrite the source presentation."
            }

            $presentation.Close()
            Release-ComObject $presentation
            $presentation = $null
            Copy-Item -LiteralPath $inputFullPath -Destination $outputFullPath -Force
            # ReadOnly=false, Untitled=false, WithWindow=false
            $presentation = $application.Presentations.Open($outputFullPath, 0, 0, 0)
            $applyReport = Apply-TranslationManifest $presentation $ManifestPath
            $combinedManifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $overlayCount = 0
            if ($null -ne $combinedManifest.overlays) {
                $overlayCount = @($combinedManifest.overlays).Count
            }
            if ($overlayCount -gt 0) {
                Apply-OverlayManifest $presentation $ManifestPath
            }
            $applyReport["image_overlays"] = $overlayCount
            $presentation.Save()
            $applyReport | ConvertTo-Json -Compress
        }
        "apply-overlays" {
            if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
                throw "ManifestPath is required for command 'apply-overlays'."
            }
            $outputFullPath = Resolve-OutputFile $OutputPath
            if ([string]::Equals($inputFullPath, $outputFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to overwrite the source presentation."
            }

            $presentation.Close()
            Release-ComObject $presentation
            $presentation = $null
            Copy-Item -LiteralPath $inputFullPath -Destination $outputFullPath -Force
            $presentation = $application.Presentations.Open($outputFullPath, 0, 0, 0)
            Apply-OverlayManifest $presentation $ManifestPath
            $presentation.Save()
        }
        "convert" {
            $outputFullPath = Resolve-OutputFile $OutputPath
            if ([string]::Equals($inputFullPath, $outputFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to overwrite the source presentation."
            }
            if ([System.IO.Path]::GetExtension($outputFullPath).ToLowerInvariant() -ne ".pptx") {
                throw "The convert command requires a .pptx OutputPath."
            }
            if (Test-Path -LiteralPath $outputFullPath) {
                Remove-Item -LiteralPath $outputFullPath -Force
            }
            # 24 = ppSaveAsOpenXMLPresentation
            $presentation.SaveAs($outputFullPath, 24)
        }
        "render" {
            $directory = Resolve-OutputDirectory $OutputDirectory
            $renderWidth = 1440
            $renderHeight = [int][Math]::Round(
                $renderWidth * [double]$presentation.PageSetup.SlideHeight /
                [double]$presentation.PageSetup.SlideWidth
            )
            for ($slideIndex = 1; $slideIndex -le $presentation.Slides.Count; $slideIndex++) {
                $slide = $presentation.Slides.Item($slideIndex)
                try {
                    $fileName = "slide-{0:D2}.png" -f $slideIndex
                    $slide.Export((Join-Path $directory $fileName), "PNG", $renderWidth, $renderHeight)
                }
                finally {
                    Release-ComObject $slide
                }
            }
        }
        "export-images" {
            $directory = Resolve-OutputDirectory $OutputDirectory
            $manifestOutput = Resolve-OutputFile $ManifestPath
            $images = @()
            for ($slideIndex = 1; $slideIndex -le $presentation.Slides.Count; $slideIndex++) {
                $slide = $presentation.Slides.Item($slideIndex)
                try {
                    for ($shapeIndex = 1; $shapeIndex -le $slide.Shapes.Count; $shapeIndex++) {
                        $shape = $slide.Shapes.Item($shapeIndex)
                        try {
                            if ($shape.Type -ne 13 -and $shape.Type -ne 11) {
                                continue
                            }
                            $fileName = "slide-{0:D2}-shape-{1}.png" -f $slideIndex, ([int]$shape.Id)
                            $filePath = Join-Path $directory $fileName
                            # 2 = ppShapeFormatPNG
                            $shape.Export($filePath, 2)
                            $images += [ordered]@{
                                slide_index = $slideIndex
                                shape_id = [int]$shape.Id
                                file = $fileName
                                left = [double]$shape.Left
                                top = [double]$shape.Top
                                width = [double]$shape.Width
                                height = [double]$shape.Height
                                contains_source_text = $null
                                regions = @()
                                status = "pending_screening"
                            }
                        }
                        finally {
                            Release-ComObject $shape
                        }
                    }
                }
                finally {
                    Release-ComObject $slide
                }
            }
            Write-JsonUtf8 ([ordered]@{
                source_file = [System.IO.Path]::GetFileName($inputFullPath)
                images = $images
            }) $manifestOutput
        }
        "inventory-nonstandard" {
            $outputFullPath = Resolve-OutputFile $OutputPath
            $directory = Resolve-OutputDirectory $OutputDirectory
            $projectRoot = Split-Path -Parent $PSScriptRoot
            $screeningManifestPath = Join-Path (Split-Path -Parent $outputFullPath) "image-manifest.json"
            $inventory = Get-NonstandardInventory `
                $presentation `
                ([System.IO.Path]::GetFileName($inputFullPath)) `
                $directory `
                $projectRoot `
                $screeningManifestPath
            Write-JsonUtf8 $inventory $outputFullPath
        }
        "verify" {
            if ([string]::IsNullOrWhiteSpace($TranslatedPath)) {
                throw "TranslatedPath is required for command 'verify'."
            }
            $translatedFullPath = Resolve-ExistingPath $TranslatedPath
            $reportOutput = Resolve-OutputFile $OutputPath
            $sourceReport = Get-InspectionReport $presentation
            $sourceShapeAudit = Get-VerificationShapeAudit $presentation

            $presentation.Close()
            Release-ComObject $presentation
            $presentation = $null
            $presentation = $application.Presentations.Open($translatedFullPath, -1, 0, 0)
            $translatedReport = Get-InspectionReport $presentation
            $translatedShapeAudit = Get-VerificationShapeAudit $presentation
            $translatedManifest = Get-TranslationManifest $presentation ([System.IO.Path]::GetFileName($translatedFullPath))

            $expectedOverlayHostKeys = @()
            if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
                $verificationManifestPath = Resolve-ExistingPath $ManifestPath
                $verificationManifest = Get-Content -LiteralPath $verificationManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                foreach ($overlayRecord in @($verificationManifest.overlays)) {
                    if ([string]$overlayRecord.kind -cne "office_overlay") {
                        continue
                    }
                    $expectedOverlayHostKeys += (
                        "slide:$([int]$overlayRecord.location.page_or_slide)/" +
                        "shape:$([int]$overlayRecord.location.host_shape_id)"
                    )
                }
            }
            $differences = @(
                Compare-VerificationShapeAudits `
                    $sourceShapeAudit `
                    $translatedShapeAudit `
                    $expectedOverlayHostKeys
            )
            foreach ($property in @("slides", "animations")) {
                if ($sourceReport[$property] -ne $translatedReport[$property]) {
                    $differences += [ordered]@{
                        property = $property
                        source = $sourceReport[$property]
                        translated = $translatedReport[$property]
                    }
                }
            }
            foreach ($property in @("slide_width", "slide_height")) {
                if ([Math]::Abs([double]$sourceReport[$property] - [double]$translatedReport[$property]) -gt 0.01) {
                    $differences += [ordered]@{
                        property = $property
                        source = $sourceReport[$property]
                        translated = $translatedReport[$property]
                    }
                }
            }

            $residue = @()
            foreach ($item in $translatedManifest.items) {
                if ([string]$item.source_text_normalized -match "[\u3400-\u9FFF]") {
                    $residue += [ordered]@{
                        id = $item.id
                        text = $item.source_text_normalized
                    }
                }
            }

            Write-JsonUtf8 ([ordered]@{
                source_file = [System.IO.Path]::GetFileName($inputFullPath)
                translated_file = [System.IO.Path]::GetFileName($translatedFullPath)
                passed = ($differences.Count -eq 0 -and $residue.Count -eq 0)
                structural_differences = $differences
                source_language_residue = $residue
                editable_text_paragraphs = @($translatedManifest.items).Count
                source_summary = [ordered]@{
                    slides = $sourceReport.slides
                    slide_width = $sourceReport.slide_width
                    slide_height = $sourceReport.slide_height
                    shapes = $sourceReport.shapes
                    text_shapes = $sourceReport.text_shapes
                    pictures = $sourceReport.pictures
                    animations = $sourceReport.animations
                }
                translated_summary = [ordered]@{
                    slides = $translatedReport.slides
                    slide_width = $translatedReport.slide_width
                    slide_height = $translatedReport.slide_height
                    shapes = $translatedReport.shapes
                    text_shapes = $translatedReport.text_shapes
                    pictures = $translatedReport.pictures
                    animations = $translatedReport.animations
                }
            }) $reportOutput
        }
        default {
            throw "Command '$Command' is not implemented yet."
        }
    }
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch {}
    }
    if ($null -ne $application) {
        try { $application.Quit() } catch {}
    }
    Release-ComObject $presentation
    Release-ComObject $application
    if ($null -ne $windowGuard) { $windowGuard.Stop() }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
