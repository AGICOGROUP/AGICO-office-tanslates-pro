# Excel professional translation workflow

## 1. Route and preserve

Use `scripts/excel_fast_pipeline.py prepare` to hash and route the original, validate the glossary,
and convert `.xls` once. The converter disables macros, rejects VBA, saves a separate `.xlsx`, and
reopens it once. Reject `.xlsm` instead of attempting macro preservation.

## 2. Run the fixed pipeline

The fast runner invokes `scripts/excel_pipeline.mjs` in the fixed sequence `inspect`, `prepare`,
`apply`, `verify`, and `office-validate`. Store artifacts under `work/<source-stem>-<hash-prefix>/`.
`finalize` resumes from `job-state.json` without repeating completed gates.

`inspect` performs one non-rendering pass, inventories editable text and OOXML risks, and groups
images by SHA-256. `prepare` performs safe deduplication: repeated source text shares a translation unit
only when object kind, context, and protected tokens match. Unknown context stays separate.
For compact parameter rows whose suffix begins with a number or model code, extract the label as the
translation unit and retain the separator and technical suffix on each occurrence. Reconstruct the
full cell during `apply`; natural-language notes remain whole translation units.

For an English target, pre-fill exact reviewed matches from `fixed-translations.en.json`. For every
target language, retain standalone identifiers, uppercase technical codes, model codes, and pure
dimensions with explicit reasons. Send only remaining `pending` units to the model; do not broaden
fixed matches by fuzzy search.

At the translation pause, read only `translation-worklist.json` and `relevant-glossary.json`.
Do not read the inventory or complete manifest during the standard path.
Apply exact phrase, longest valid matched term, then professional contextual translation. Preserve numbers, units,
models, identifiers, URLs, standards, punctuation, and meaningful line breaks. Validate the
compact worklist before `finalize`; the runner merges and validates the schema-v2 manifest.

Resolve every unique image to `reviewed`, `localized`, or `retain` before `apply`. A remaining
`manual-review` record blocks writing; duplicate occurrences reuse the same SHA-256 decision.

Run `scripts/excel_fast_pipeline.py finalize` once. `apply` imports once, mutates text-bearing cells
only, and exports once. For bilingual output, apply
`bilingual-row-layout.md` only after the grid-safety classifier passes. Otherwise enter strict
processing before creating an output.
For monolingual output, estimate wrapped line count from final text and effective merged-cell width.
Increase only affected row heights, cap automatic height at 60 points, and compress to 8 points only
runs of three or more completely blank, formula-free, unmerged placeholder rows.

## 3. Final checks

- For every job, verify deterministic invariants and run one Microsoft Excel validation pass.
- Do not render a source baseline or translated workbook in the standard pipeline.
- Only when the user explicitly requests strict layout inspection, perform a separate visual review
  after `office-validate`; do not make it part of the default delivery gate.
- Images: read `image-text-localization.md`; review one record per unique SHA-256, not each
  occurrence.
- Unsupported complex or strict workbook features fail during inspection before mutation. Do not
  enter an expensive alternate rendering or reconstruction path.

Treat sub-2-point empty legacy shape fragments as decorative borders, not unsupported drawings.
Use Microsoft Excel COM to open source and output read-only, fully recalculate both, check
worksheet/used-range access, and compare formula/value error cells. Reject new error cells introduced
by translation; do not fail only because the source already contained the same error cells. Do not
export PDF or invoke LibreOffice. If Microsoft Excel is unavailable, stop and report the blocker.

Verification must reject changed formulas or typed values, broken merges, missing occurrences,
protected-token loss, incomplete bilingual pairs, or output-open failure. Excel-native validation
owns the source/output error-cell comparison so the same condition is not checked twice.
Record route, conversion, inspection, preparation, apply, verification, and Office validation
durations in `stage-timings.json`.

## 4. Delivery

Deliver one new workbook immediately after `verify` and `office-validate` pass. Report strict reasons
when present. The source hash must still match the value recorded at `inspect`.
