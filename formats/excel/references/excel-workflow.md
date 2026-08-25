# Excel professional translation workflow

## 1. Route and preserve

Hash the original and run `scripts/route_excel_file.py`. Never overwrite it. Convert `.xls` only
through a verified Excel-compatible working copy. Keep `.xlsm` on the strict macro-safe route.

## 2. Run the fixed pipeline

Run `scripts/excel_pipeline.mjs` in the fixed sequence `inspect`, `prepare`, `apply`, `verify`,
`render`. Store artifacts under `work/<source-stem>-<hash-prefix>/` and resume from
`job-state.json`; do not repeat completed stages whose artifact hashes still match.

`inspect` performs one preflight pass, inventories editable text and OOXML risks, and groups images
by SHA-256. `prepare` performs safe deduplication: repeated source text shares a translation unit
only when object kind, context, and protected tokens match. Unknown context stays separate.

At the translation pause, resolve the repository glossary before model wording: exact phrase,
longest valid listed term, then professional contextual translation. Preserve numbers, units,
models, identifiers, URLs, standards, punctuation, and meaningful line breaks. Validate the
schema-v2 manifest before mutation.

`apply` imports once, mutates text-bearing cells only, and exports once. For bilingual output, apply
`bilingual-row-layout.md` only after the grid-safety classifier passes. Otherwise enter strict
processing before creating an output.

## 3. Conditional checks

- Balanced monolingual: verify deterministic invariants and render only changed/risk sheets.
- Bilingual: verify every source/translation pair and render all changed visible sheets.
- Images: read `image-text-localization.md`; review one record per unique SHA-256, not each
  occurrence.
- Strict: use feature-aware checks and full relevant rendering when macros, unsafe conversion,
  tables, charts, comments, external links, unsupported drawings, uncertain images, repair
  warnings, or invariant mismatches are present.

Verification must reject changed formulas or typed values, broken merges, missing occurrences,
protected-token loss, incomplete bilingual pairs, formula errors, or output-open failure.

## 4. Delivery

Deliver one new workbook only after `verify` passes and `render` completes. Report strict reasons
when present. The source hash must still match the value recorded at `inspect`.
