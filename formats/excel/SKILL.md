---
name: translate-excel-professionally
description: Use when translating Excel workbooks (.xls, .xlsx, or .xlsm), especially cement-industry equipment lists, quotations, schedules, and technical tables whose formulas, layout, images, macros, and editable structure must be preserved.
---

# Professional Excel Translation

Translate with Codex/GPT and mutate only human-language text-bearing objects. Keep formulas as formulas, native text editable, and workbook geometry stable.

**REQUIRED SUB-SKILL:** Use `spreadsheets:Spreadsheets` for `.xlsx` inspection, editing, rendering, and export. Follow its artifact-tool contract.

## Start from the original

Hash and preserve the source. Work from a copy and create a separate translated output. Read before acting:

- `references/excel-workflow.md`
- `../../references/水泥专业名词中英对照.md`, the repository-wide terminology source
- `references/manifest-schema.md`
- `references/image-text-localization.md`

Run `scripts/resolve_repo_glossary.py`; fail closed when the shared glossary is unavailable.

## Route the Excel container

Run `python scripts/route_excel_file.py <source>` and follow exactly one route:

| Route | Required handling |
|---|---|
| `.xls` | Confirm CFB signature, inspect for legacy VBA, convert an immutable working copy through an Excel-compatible converter to `.xlsx` or macro-safe `.xlsm`, verify the conversion baseline, then follow that route. |
| `.xlsx` | Confirm OOXML without VBA; use `spreadsheets:Spreadsheets` and the artifact tool. |
| `.xlsm` | Confirm the macro-enabled OOXML content type and inspect `vbaProject.bin` when present; use a macro-safe Excel engine and preserve VBA byte-for-byte. Stop if unavailable. |

Reject corrupt, encrypted, ambiguous, unsupported, or extension-mismatched files.

## Required workflow

1. Inventory and render every sheet and configured print area before editing.
2. Extract text from cells, comments, notes, text boxes, charts, headers, footers, and image labels in stable object order. Never overwrite formula cells.
3. Resolve terminology before model preference: exact glossary phrase, longest valid listed term, then professional contextual translation. Preserve numbers, units, model codes, standards, URLs, identifiers, and line breaks.
4. Build a complete manifest and run `python scripts/validate_manifest.py <manifest.json>`.
5. Translate editable text natively. Review every image with `references/image-text-localization.md`.
6. Keep row heights and column widths unchanged by default. Use concise English, wrapping, then bounded local font reduction; record any justified dimension change.
7. Export one new workbook in the routed format (`.xls` may deliver `.xlsx`; `.xlsm` remains `.xlsm`). Never overwrite the source.
8. Compare formulas, sheet structure, names, merges, dimensions, styles, validations, filters, panes, links, charts, media, macros, print areas, and page setup. Scan formula errors and unexpected Chinese.
9. Reopen and render every final sheet and print area. Reject clipping, overlap, chart-label collisions, merged-cell damage, hidden omissions, or unreviewed images.

## Delivery gate

Deliver only when the source is untouched, the output opens without repair warnings, the shared glossary governed every matching term, all expected text remains editable, every manifest item and image is resolved, formulas and VBA are unchanged, no unexpected source-language text remains, and complete rendered review finds no unapproved structural or visual change.
