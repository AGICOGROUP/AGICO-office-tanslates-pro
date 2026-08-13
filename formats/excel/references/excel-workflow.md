# Excel professional translation workflow

## Preflight

1. Hash and preserve the original.
2. Route by signature with `scripts/route_excel_file.py`.
3. For `.xls`, inspect for legacy VBA, convert a working copy with an Excel-compatible converter to `.xlsx` or macro-safe `.xlsm`, and compare the converted baseline visually and structurally before translation.
4. For `.xlsm`, require a macro-safe engine and retain `vbaProject.bin`; stop if unavailable.
5. Render every visible sheet and every configured print area.

Inventory sheet order and visibility, used ranges, formulas, defined names, tables, merged cells, dimensions, styles, number formats, validations, comments, hyperlinks, filters, freeze panes, charts, shapes, images, external links, macros, print areas, headers, footers, and page setup.

## Translation

- Extract editable human-language text from cells, comments, notes, shapes, chart labels, headers, footers, and image labels.
- Exclude formulas, names, macro code, model numbers, identifiers, URLs, and protected tokens.
- Resolve the repository glossary before model wording: exact phrase, longest valid term, then contextual professional translation.
- Keep one manifest item per source object; do not deduplicate repeated text.
- Validate the manifest before mutation.
- Modify only text-bearing objects. Keep formulas as formulas and numeric/date cells typed.
- For bilingual output, read and apply `bilingual-row-layout.md`; it is the default layout unless the user specifies another arrangement.

## Fit and verification

Keep original row heights and column widths by default. Use concise English, wrapping, and bounded font reduction before any local dimension change; record every approved fit adjustment.

After export, compare formulas, sheet structure, names, merges, dimensions, styles, validations, filters, panes, links, charts, images, macros, print settings, and page setup. Scan for formula errors and unexpected Chinese. For bilingual output, also reject missing or split source/translation row pairs, duplicated numeric data in translation rows, and source-language text in translation rows. Render every final sheet and print area; reject clipping, overlap, merged-cell damage, chart collisions, missing image labels, or unreviewed hidden content.
