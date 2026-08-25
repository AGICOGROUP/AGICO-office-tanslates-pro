# Bilingual Excel paired-row layout

Use this layout when the user requests bilingual Excel output and does not specify another arrangement.

## Automatic fast-path boundary

Use the automatic blue-row rebuild only for a verified plain cell grid. Styles, formulas,
horizontal merges, row/column dimensions, and sheet order are supported. Before rebuilding,
classify the original OOXML package. Route the job to the existing strict workflow without
creating a partial output when it contains VBA, Excel table objects, charts, comments,
external links, unsupported drawings, vertical merges, or any image whose preservation and
text-localization status is uncertain.

The fast path is deliberately narrow: failing the safety check is not a translation failure.
It means the workbook needs feature-aware processing and full verification.

## Structure

- Create one source row followed immediately by one translation row for every row in the printed table, including structural blank rows.
- Keep the source row as the authoritative data row. Put translated human-language text in the corresponding cells of the translation row.
- Do not duplicate numeric values, quantities, prices, weights, power, dimensions, dates, or formulas in the translation row.
- Leave non-language cells blank in the translation row. Translate labels, descriptions, units, notes, headers, and metadata.
- Keep model codes, URLs, tags, and other protected identifiers in the source row. Store identifiers with leading zeros as text.
- Recreate each horizontal merged range in both the source row and the translation row.
- Route vertical or cross-row merges to strict processing.

## Blue translation row

| Property | Required value |
|---|---|
| Fill | `#EAF2F8` |
| Font color | `#1F4E78` |
| Font style | italic |
| Font family | Arial, unless the source requires another compatible font |
| Alignment | Vertically centered; follow the source column's horizontal alignment |
| Text | Wrapped and fully visible |
| Borders | Same cell-border geometry as the paired source row |

Use about 24 pt row height for ordinary translation rows and 28-32 pt for long text. Increase only enough to prevent clipping.

## Formulas and protected data

- Keep formulas only in source rows and remap references to the expanded paired-row geometry.
- Make totals reference the intended source-data rows; blank translation rows must not change calculated results.
- Recalculate in Excel-compatible software and prove original calculated values and totals remain unchanged.
- Preserve protected identifiers, especially equipment codes with leading zeros.
- If legacy `.xls` files use mojibake or drawing rectangles as borders, restore readable source text and rebuild stable cell borders before removing legacy shapes.

## Print and verification

- Fit wide technical tables to one page wide when readable, normally in landscape.
- Repeat the complete paired title/header block on later pages.
- Insert page breaks only between complete source-row/translation-row pairs.
- Preserve or bilingualize worksheet headers and footers when they contain visible source-language text.
- Render every printed page and verify blue bands, merged cells, identifiers, totals, and notes are legible.
- Require exactly one translation row under every source row, zero duplicated non-language values, zero formula errors, zero broken merges, zero clipped text, and zero unexpected source-language text in translation rows.
