---
name: translate-excel-professionally
description: Use when translating monolingual or bilingual Excel workbooks (.xls, .xlsx, or .xlsm), especially technical tables whose formulas, layout, images, macros, and editable structure must be preserved.
---

# Professional Excel Translation

Translate with Codex/GPT through one resumable pipeline. Mutate only human-language text, keep
formulas and native text editable, preserve the source hash, and always write a separate output.

Top-level routing is complete when this adapter starts. Do not run the root Office router again,
read another format adapter, or consider another format workflow. The container
route below is Excel-internal validation only.

**REQUIRED SUB-SKILL:** Use `spreadsheets:Spreadsheets` and its artifact-tool contract.
This adapter supersedes its baseline and final-render requirements: do not render a source baseline
and do not add a visual gate to the standard translation flow.

## Required inputs

Read these files completely before execution:

- `references/excel-workflow.md`
- `references/pipeline-cli.md`
- `references/manifest-schema.md`

Run `scripts/resolve_repo_glossary.py`; stop if the shared glossary is unavailable. After
`prepare`, read only `<job-dir>/relevant-glossary.json`; do not load the complete glossary. Read
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

1. `inspect` performs one scan and creates the inventory, OOXML risk/image report,
   and `job-state.json`.
2. `prepare` creates schema-v2 translation units plus a source-matched glossary subset and
   safely pre-fills verified English table labels, units, parameter labels, and identifier/model
   codes, then pauses only for the remaining translation units.
3. Fill every pending translation unit using glossary-first professional terminology, then run
   `python scripts/validate_manifest.py <job-dir>/translation-manifest.json` and run `apply` once.
   Safe deduplication reuses exact text only when context and protected tokens match.
   Parameter rows such as `功率：45kW` translate the label once and reconstruct each original
   technical value deterministically; do not send the unchanged values for repeated translation.
4. For monolingual output, `apply` estimates translated line length, increases only affected row
   heights, and compresses only runs of at least three completely blank, unmerged placeholder rows.
5. `verify` reopens source and output and checks formulas, typed values, merges, sheet order,
   occurrence coverage, protected tokens, and bilingual pairs.
6. `office-validate` opens source and output read-only in Microsoft Excel, performs a full
   recalculation, confirms every worksheet and used range is accessible, and rejects only formula
   or value error cells newly introduced in the output.

Resume from the first incomplete stage in `job-state.json`; do not recreate task-specific workbook
scripts. Full commands and exit codes are in `references/pipeline-cli.md`.

## Quality boundary

- Preserve numbers, units, model codes, standards, URLs, identifiers, meaningful line breaks,
  formulas, and source-file SHA-256.
- Group identical images by SHA-256 and review each unique byte sequence once. Deep-review only
  localized or uncertain groups.
- Standard jobs use deterministic checks plus one Excel open/recalculation pass. Do not render a
  source baseline or translated workbook. If the user explicitly requests strict layout inspection,
  perform a separate visual review after the standard pipeline; it is not a delivery gate by default.
- Complex and strict jobs add only their documented object, macro, or repair checks; they do not
  export PDF by default.
- Bilingual output defaults to the paired blue translation-row layout. The fast path is limited to
  verified grid-safe workbooks; complex objects enter strict processing before mutation.
- Charts, comments, external links, unsupported drawings, and uncertain images select the complex
  path. `.xlsm`, VBA, unsafe legacy conversion, file repair, or deterministic verification mismatch
  select the strict path.
- Ignore tiny empty legacy shape fragments used as borders. Escalate only drawings with text,
  media, charts, controls, or meaningful geometry.
- Fixed English translations are exact-match entries in `references/fixed-translations.en.json`.
  Add only reviewed, context-stable labels; leave ambiguous equipment terminology pending.

Deliver immediately after deterministic verification and `office-validate` pass, the output reopens
without repair, the source remains untouched, and no required translation is missing.
