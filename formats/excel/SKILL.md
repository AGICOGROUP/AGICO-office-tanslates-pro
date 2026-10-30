---
name: office-translate-pro-excel
description: Use when translating Excel .xls or .xlsx workbooks, including engineering equipment lists and bilingual tables whose formulas, units and editable structure must survive.
---

# Excel pipeline

Top-level routing is complete. Do not run the root Office router again.
Follow the [shared workflow](../../references/translation-decisions.md) from the skill root.
Use `prepare --output-mode bilingual` only when paired translation rows are requested;
otherwise keep the normal monolingual cell layout.

## Translate the workbook, not only visible body cells

Use cell/column context and the matched `../../references/水泥专业名词中英对照.md`.
Translate every worksheet tab through the worklist, including hidden/empty sheets, and literal
dropdown choices consistently with cell labels. Names must be unique, no more than 31 characters
and free of Excel's forbidden characters. Native formula sheet qualifiers and defined names are
updated for supported local references; calculation logic and values remain unchanged. Report an
actual unsafe reference exception rather than silently leaving Chinese tabs.

Preserve numbers, units, signs, identifiers, number formats and meaningful line breaks. Keep square/
cubic exponents readable as `m²`, `m³`, `cm²`, `Nm³`. Do not proportionally assign an unrelated part of
a translated phrase to a source superscript run. Check the actual saved unit cells when rich-run
formatting creates a display risk. A unit spelling correction is not permission to change dimensions.

## Native preservation

Monolingual writing patches original OOXML cells, expanding only affected rows when needed. Keep
typed values, formula logic, merges, styles, charts, comments, drawings, relationships, media and
unknown parts. Formula-controlled lookup labels may need retention; disclose the affected labels.
Print ranges and filter databases are layout metadata, not a reason to freeze ordinary language.
Invisible blank objects stay preserved and must not block cell translation merely because they exist.
Meaningful unsupported object text is reported specifically, never silently discarded.

For bilingual paired rows, read [row-layout details](references/bilingual-row-layout.md).
Preserve original source rows/styles and blue translation rows; use supported reference rewriting.
Do not flatten a sheet or silently substitute monolingual output for an unsupported bilingual layout.

## Pictures and delivery

If images exist, read [image writeback](references/image-text-localization.md) and the linked shared
rule. Review each unique image once; reuse only inside the current job. A `localized` decision needs
an absolute `replacement_path`; final validation checks actual embedded hashes and occurrences.
Status alone does not prove image translation. Logo-only pictures retain their original bytes.

`.xls` converts once. External relationships stay intact without refresh. Finalize verifies coverage,
typed values, formula logic/references, merges, sheet order and untouched package parts, followed by
one bounded read-only Excel check when available. Missing Office/timeout follows the warning path;
confirmed opening failures or new formula errors require repair. Publish only the verified candidate.
Do not add routine PDF exports, repository tests or repeated full-sheet visual gates.
`scripts/excel_fast_pipeline.py` remains the compatibility/diagnostic adapter, not another user entry.
