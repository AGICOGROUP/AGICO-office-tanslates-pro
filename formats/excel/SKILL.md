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

1. Run `python scripts/excel_fast_pipeline.py prepare ...` once. It runs the Excel-internal
   `route_excel_file.py`, validates `resolve_repo_glossary.py`, converts `.xls` once when required,
   then executes `inspect` and `prepare` through `excel_pipeline.mjs`.
2. Read only `<job-dir>/translation-worklist.json` and
   `<job-dir>/relevant-glossary.json`. Do not read `inventory.json`, the complete manifest, the full
   glossary, or pipeline references during an ordinary job.
3. Fill every pending worklist record with glossary-first professional terminology. Preserve every
   protected token. Use `translated` for translated text; use justified `retain` only when output
   equals source. Safe deduplication reuses exact text only when context and protected tokens match.
   For long worklists, read `translation-batches.json` and its listed files instead of repeating the
   complete worklist. Submit compact ID/translation JSON using `merge --job-dir <job> --responses
   <responses.json>` through `excel_fast_pipeline.py`. Resume with `batches`; use `--ids` for local
   corrections. Keep the same relevant glossary and image review. See `references/pipeline-cli.md`.
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
  worksheet and used range, and rejects only new error cells introduced in the output.
- `finalize` resumes after the last completed gate in `job-state.json`. Stage durations are written
  to `stage-timings.json`; do not recreate task-specific scripts.

## Quality boundary

- Preserve numbers, units, model codes, standards, URLs, identifiers, meaningful line breaks, and
  formulas. The source file remains untouched.
- Resolve each unique image to `reviewed`, `localized`, or `retain`; manual-review is not deliverable.
- Charts, comments, external links, unsupported drawings, VBA, unsafe legacy conversion, repair
  requirements, or deterministic mismatches fail before delivery; they do not start a slower
  alternate or strict reconstruction path.
- Bilingual output defaults to paired blue translation rows and is limited to grid-safe workbooks.
- Do not export PDF or use LibreOffice. Only when the user explicitly requests strict layout
  inspection, perform a separate visual review after `office-validate`.
- Fixed English translations are exact matches only; ambiguous equipment terminology stays pending.

Deliver immediately when `verify` and `office-validate` pass, the output reopens without repair,
the source hash is unchanged, and no required translation is missing.
