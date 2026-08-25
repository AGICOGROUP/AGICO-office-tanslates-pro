# Excel professional translation workflow

## 1. Route and preserve

Hash the original and run `scripts/route_excel_file.py`. Never overwrite it. Convert `.xls` only
through a verified Excel-compatible working copy. Keep `.xlsm` on the strict macro-safe route.

## 2. Run the fixed pipeline

Run `scripts/excel_pipeline.mjs` in the fixed sequence `inspect`, `prepare`, `apply`, `verify`,
`render`. Store artifacts under `work/<source-stem>-<hash-prefix>/` and resume from
`job-state.json`; do not repeat completed stages whose artifact hashes still match.

`inspect` performs one non-rendering pass, inventories editable text and OOXML risks, and groups
images by SHA-256. `prepare` performs safe deduplication: repeated source text shares a translation unit
only when object kind, context, and protected tokens match. Unknown context stays separate.
For compact parameter rows whose suffix begins with a number or model code, extract the label as the
translation unit and retain the separator and technical suffix on each occurrence. Reconstruct the
full cell during `apply`; natural-language notes remain whole translation units.

For an English target, pre-fill exact reviewed matches from `fixed-translations.en.json`. Retain
standalone identifiers and model codes containing digits without model translation. Send only
remaining `pending` units to the model; do not broaden fixed matches by fuzzy search.

At the translation pause, read `relevant-glossary.json`, not the complete repository glossary.
Apply exact phrase, longest valid matched term, then professional contextual translation. Preserve numbers, units,
models, identifiers, URLs, standards, punctuation, and meaningful line breaks. Validate the
schema-v2 manifest before mutation.

`apply` imports once, mutates text-bearing cells only, and exports once. For bilingual output, apply
`bilingual-row-layout.md` only after the grid-safety classifier passes. Otherwise enter strict
processing before creating an output.
For monolingual output, estimate wrapped line count from final text and effective merged-cell width.
Increase only affected row heights, cap automatic height at 60 points, and compress to 8 points only
runs of three or more completely blank, formula-free, unmerged placeholder rows.

## 3. Conditional checks

- Fast: verify deterministic invariants and export changed used sheets only.
- Complex: add only sheets containing affected charts, comments, drawings, or image text.
- Bilingual: verify every source/translation pair and render all changed visible sheets.
- Images: read `image-text-localization.md`; review one record per unique SHA-256, not each
  occurrence.
- Strict: export every visible used sheet when macros, unsafe conversion, repair warnings, or
  deterministic invariant mismatches are present.

Treat sub-2-point empty legacy shape fragments as decorative borders, not unsupported drawings.
Before the single final export, apply landscape plus one-page-wide fitting only to changed sheets
whose used range is at least ten columns wide. Keep vertical pagination automatic.

Use Microsoft Excel COM for the single final open, full recalculation, and PDF export. Do not
install, discover, add, or fall back to LibreOffice. If Microsoft Excel is unavailable, stop and
ask before using another renderer.

Verification must reject changed formulas or typed values, broken merges, missing occurrences,
protected-token loss, incomplete bilingual pairs, formula errors, or output-open failure.

## 4. Delivery

Deliver one new workbook only after `verify` passes and Excel COM validation completes. Report strict reasons
when present. The source hash must still match the value recorded at `inspect`.
