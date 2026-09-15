# Bilingual Excel paired-row layout

Use this layout when the user requests bilingual Excel output and does not specify another arrangement.

## Automatic fast-path boundary

Use the paired-row native OOXML writer only for a verified plain cell grid. Clone the original
source rows and derive translation styles from their original style records. Never reconstruct
the source grid through cross-workbook `copyFrom`: it can lose styles and shared-formula followers.
Preserve source fonts, fills, borders, alignment, number formats, protection and exact column widths.
Keep empty sheets empty. Preserve page settings, margins, headers/footers and untouched package parts;
remap existing print ranges, repeated title rows, freezes, hyperlinks and page breaks for the paired rows.

Before writing, classify the original OOXML package. VBA, tables, charts, comments, external links,
drawings, vertical merges, conditional formatting, filters and unsupported row-sensitive features
require feature-aware processing; report the concrete unsupported feature without creating a partial
output. Do not describe an unavailable fallback as a completed translation.

The fast path is deliberately narrow: failing the safety check is not a translation failure.
It means the workbook needs feature-aware processing and full verification.

## Structure

- Create one source row followed immediately by one translation row for every row in the printed table, including structural blank rows.
- Keep the source row as the authoritative data row. Put translated human-language text in the corresponding cells of the translation row.
- Do not duplicate numeric values, quantities, prices, weights, power, dimensions, dates, or formulas in the translation row.
- Leave non-language cells blank in the translation row. Translate labels, descriptions, units, notes, headers, and metadata.
- Keep model codes, URLs, tags, and other protected identifiers in the source row. Store identifiers with leading zeros as text.
- Preserve standalone engineering symbols and variable names such as `Ps`, `Kx`, `cosφ`, `tgφ`,
  `Pjs` and `Qjs`; do not expand them into explanatory sentences. Use concise, equivalent target
  labels in narrow headers. Do not remove a necessary technical distinction just to shorten a label.
- Recreate each horizontal merged range in both the source row and the translation row.
- Route vertical or cross-row merges to strict processing.

## Blue translation row

| Property | Required value |
|---|---|
| Fill | `#EAF2F8` |
| Font color | `#1F4E78` |
| Font style | italic |
| Font family | Arial; inherit the source font size, weight and emphasis |
| Alignment | Vertically centered; follow the source column's horizontal alignment |
| Text | Wrapped and fully visible |
| Borders | Same cell-border geometry as the paired source row |

Start at 24 pt and estimate wrapped height using translated text, the effective column/merged width
and font metrics, including words that must break inside narrow columns. Expand long rows as needed;
28-32 pt is not a maximum. Keep source row heights.
Do not shrink the font to fit. Report content exceeding Excel's maximum row height for wording or
column-width repair instead of silently clipping it.

## Formulas and protected data

- Keep formulas only in source rows and remap references to the expanded paired-row geometry.
- Expand every shared-formula follower before remapping; never replace a formula with its cached value.
- Make totals reference the intended source-data rows; blank translation rows must not change calculated results.
- Recalculate in Excel-compatible software and prove original calculated values and totals remain unchanged.
- Preserve protected identifiers, especially equipment codes with leading zeros.
- Retained identifiers and codes appear only in the source row, including identifiers stored as text.

## Print and verification

- Preserve original orientation, paper size and explicit scale/fit settings. If scaling is unspecified,
  fit to one page wide with unrestricted height so the rightmost columns are printed. If the source
  repeats header rows, repeat their complete paired block; remap existing manual page breaks between pairs.
- Native package verification must compare source styles and formula definitions as well as values,
  merged ranges and translation coverage. A check using the same lossy workbook importer as the writer
  is insufficient. Keep this within normal finalize; no extra model review or Office launch is needed.
- Recalculate once in Excel using the standard native validation step. Visual rendering is for a
  reported layout defect or development regression test, not an extra gate on every translation.
- Require one translation row per used source row, no duplicated retained codes/numeric values,
  intact formulas and source formatting, intact merges, and readable wrapped translations.
