---
name: translate-excel-professionally
description: Use when translating monolingual or bilingual Excel workbooks (.xls, .xlsx, or .xlsm), especially technical tables whose formulas, layout, images, macros, and editable structure must be preserved.
---

# Professional Excel Translation

Translate with Codex/GPT through one resumable pipeline. Mutate only human-language text, keep
formulas and native text editable, preserve the source hash, and always write a separate output.

**REQUIRED SUB-SKILL:** Use `spreadsheets:Spreadsheets` and its artifact-tool contract.

## Required inputs

Read these files completely before execution:

- `references/excel-workflow.md`
- `references/pipeline-cli.md`
- `references/manifest-schema.md`
- `../../references/水泥专业名词中英对照.md`

Run `scripts/resolve_repo_glossary.py`; stop if the shared glossary is unavailable. Read
`references/bilingual-row-layout.md` only for bilingual output. Read
`references/image-text-localization.md` only when inspection finds images.

## Container route

Run `python scripts/route_excel_file.py <source>` once.

- `.xlsx`: run the standard pipeline below.
- `.xls`: verify the CFB signature and VBA status, convert an immutable copy with an
  Excel-compatible converter, verify the conversion, then run the pipeline on the converted file.
- `.xlsm`: preserve VBA byte-for-byte with a macro-safe Excel engine. Treat it as strict; stop if
  that engine is unavailable.
- Reject corrupt, encrypted, extension-mismatched, or ambiguous containers.

## Single standard pipeline

Use `scripts/excel_pipeline.mjs` in this order:

1. `inspect` creates the inventory, OOXML risk/image report, baseline plan, and `job-state.json`.
2. `prepare` creates schema-v2 translation units and intentionally pauses for translation.
3. Fill every pending translation unit using glossary-first professional terminology, then run
   `python scripts/validate_manifest.py <job-dir>/translation-manifest.json` and run `apply` once.
   Safe deduplication reuses exact text only when context and protected tokens match.
4. `verify` reopens source and output and checks formulas, typed values, merges, sheet order,
   occurrence coverage, protected tokens, bilingual pairs, and formula errors.
5. `render` follows the conditional render plan and records any strict escalation.

Resume from the first incomplete stage in `job-state.json`; do not recreate task-specific workbook
scripts. Full commands and exit codes are in `references/pipeline-cli.md`.

## Quality boundary

- Preserve numbers, units, model codes, standards, URLs, identifiers, meaningful line breaks,
  formulas, and source-file SHA-256.
- Group identical images by SHA-256 and review each unique byte sequence once. Deep-review only
  localized or uncertain groups.
- Monolingual balanced jobs render changed/risk sheets after one preflight pass.
- Bilingual output defaults to the paired blue translation-row layout. The fast path is limited to
  verified grid-safe workbooks; complex objects enter strict processing before mutation.
- `.xlsm`, VBA, unsafe legacy conversion, tables/charts/comments/external links unsupported by the
  rebuild, uncertain images, file repair, or verification mismatch require strict processing.

Deliver only after verification passes, required renders exist, the output reopens without repair,
the source remains untouched, and no required translation is missing.
