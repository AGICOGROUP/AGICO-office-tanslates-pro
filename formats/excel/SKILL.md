---
name: translate-excel-professionally
description: Use when translating monolingual or bilingual Excel workbooks (.xls or .xlsx), especially technical tables whose formulas, layout, images, and editable structure must be preserved.
---

# Professional Excel Translation

Translate through one resumable Excel-only pipeline. Change human-language text only, preserve the
source SHA-256, formulas, native editability, and layout, and always save a separate output.

Top-level routing is complete. Do not read another format adapter.
Do not run the root Office router again. **REQUIRED SUB-SKILL:** Use `spreadsheets:Spreadsheets`;
this adapter supersedes its baseline
and final-render requirements. Do not render a source baseline or add a visual delivery gate.

## Fast standard path

Use the workspace's bundled Python to run the commands below. The runner locates its bundled
Node, official artifact-tool package and PowerShell 7 automatically; explicit runtime options
remain available. Do not create a node_modules junction or install packages for each translation.

1. Run `python scripts/excel_fast_pipeline.py prepare ...` once. It runs the Excel-internal
   `route_excel_file.py`, validates `resolve_repo_glossary.py`, converts `.xls` once when required,
   then executes `inspect` and `prepare` through `excel_pipeline.mjs`.
2. Read only `<job-dir>/translation-worklist.json` and
   `<job-dir>/relevant-glossary.json`. Do not read `inventory.json`, the complete manifest, the full
   glossary, or pipeline references during an ordinary job.
3. Fill every pending worklist record with glossary-first professional terminology. Preserve every
   protected token. Use `translated` for translated text; use justified `retain` only when output
   equals source. Safe deduplication reuses exact text only when context and protected tokens match.
4. Run `python scripts/excel_fast_pipeline.py finalize ...` once. It merges the worklist, runs
   `validate_manifest.py`, then executes `apply`, `verify`, and `office-validate`. Deliver after it
   returns `next_stage: deliver`.

Use `references/pipeline-cli.md` only for troubleshooting. Read
`references/bilingual-row-layout.md` only for bilingual output. Read
`references/image-text-localization.md` only when the worklist contains images.

## Runner contract

- `.xlsx` is used directly after internal validation. `.xls` must have a valid CFB signature; the
  runner creates and natively reopens one immutable `.xlsx` working copy. The converter disables
  macros and rejects VBA. All macro-enabled Office files are rejected before mutation.
- Reject corrupt, encrypted, extension-mismatched, ambiguous, or repair-requiring containers.
- `prepare` performs one scan, creates `job-state.json`, groups identical images by SHA-256, and
  emits only pending decisions. It safely pre-fills reviewed English labels and retains pure
  dimensions, uppercase technical codes, identifiers, and model codes with reasons.
- Parameter rows such as `功率：45kW` translate the label once and reconstruct each original value.
- For monolingual output, `apply` changes text cells once, expands only affected row heights, and
  compresses only runs of at least three blank, formula-free, unmerged placeholder rows.
- `verify` checks formulas, typed values, merges, sheet order, coverage, protected tokens, and
  bilingual pairs. `office-validate` uses Microsoft Excel read-only, recalculates, confirms every
  worksheet and used range, and rejects only new error cells introduced in the output. The native
  check waits at most 60 seconds. Missing PowerShell, unavailable Excel or a timeout may finish
  with a disclosed warning only for the unchanged output that passed `verify`; this does not mean
  native validation passed. Workbook opening/check failures and new error cells still block.
- `finalize` resumes after the last completed gate in `job-state.json`, checking saved source,
  decision and output hashes before trusting completed stages. Legacy `.xls` jobs separately retain
  the original file identity. Changed files cannot inherit an earlier passing verification. Stage durations are written
  to `stage-timings.json`; do not recreate task-specific scripts.
- Ordinary translations use prepare, the compact worklist and finalize. Repository regression
  tests, full Skill audits, installation and glossary synchronization belong to development/setup,
  not each translation. After finalize returns deliver, provide the file immediately; do not add
  renders or repeat verification unless a concrete output issue or an explicit request warrants it.

## Quality boundary

- Preserve numbers, units, model codes, standards, URLs, identifiers, meaningful line breaks, and
  formulas. The source file remains untouched.
- Resolve each unique image to `reviewed`, `localized`, or `retain`; manual-review is not deliverable.
  `localized` requires an absolute `replacement_path` to an edited PNG/JPEG of the original format
  and dimensions. The runner records its hash, writes every matching image part, and verifies the
  output bytes and occurrence counts; setting a status alone does not localize an image.
  Image reason notes are optional and are not a separate approval or delivery gate.
- Charts, comments, external links, unsupported drawings, VBA, unsafe legacy conversion, repair
  requirements, or deterministic mismatches fail before delivery; they do not start a slower
  alternate or strict reconstruction path.
- Empty rectangles explicitly marked with no fill and no line, with no text or visible effects,
  are legacy placeholders regardless of size. Preserve these objects during translation; do not
  delete them or let their dimensions alone trigger `unsupported-drawing`. Office `creationId`
  metadata and inactive `hiddenFill`/`hiddenLine` paint caches do not make an object visible.
  Inspect their namespace and extension identity; unknown extensions remain subject to checks. Missing or inherited
  paint properties, visible effects, text and connectors remain subject to drawing checks.
  This exemption supports monolingual translation. Paired-row bilingual reconstruction still
  rejects decorative drawings with `drawing-anchor-rebuild` until their anchors can be retained;
  never silently discard objects to produce bilingual rows.
- Bilingual output defaults to paired blue translation rows and is limited to grid-safe workbooks.
  Formula mapping supports cell references and whole-row ranges and preserves quoted sheet names.
  Row-sensitive counting, lookup and positional functions are rejected during preparation because
  inserted translation rows alter their meaning. In monolingual output, source labels used as
  literal formula conditions are retained with a delivery warning to preserve calculation.
- Do not export PDF or use LibreOffice. Only when the user explicitly requests strict layout
  inspection, perform a separate visual review after `office-validate`.
- Fixed English translations are exact matches only; ambiguous equipment terminology stays pending.

Deliver immediately when `verify` passes and `office-validate` completes, the source hash is unchanged,
and no required translation is missing. Disclose any native-check warning returned by `finalize`;
do not report an unavailable check as successful or hide confirmed workbook damage.
