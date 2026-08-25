# Excel pipeline CLI

Run commands from `formats/excel/` with the Node.js runtime supplied by the Codex workspace.
Use `work/<source-stem>-<sha256-prefix>/` as the job directory.

## Commands

```powershell
node scripts/excel_pipeline.mjs inspect --input <source.xlsx> --job-dir <job-dir> --target-language <language> --output-mode <monolingual|bilingual>
node scripts/excel_pipeline.mjs prepare --job-dir <job-dir>
node scripts/excel_pipeline.mjs apply --input <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs verify --source <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs office-validate --job-dir <job-dir> --output <translated.xlsx>
```

`inspect` never renders. `prepare` exits with code `3` intentionally. This means
`translation-manifest.json` and `relevant-glossary.json` are ready for Codex/GPT; it is not a
failure. Read only the matched glossary file. Fill every `translation_units[]` record, set `status`
to `translated` or justified `retain`, preserve every protected token, and validate the manifest.
`prepare` may already mark reviewed English fixed labels as `translated` and standalone identifiers
as `retain`; translate only records still marked `pending`.

## State and resume

`job-state.json` records source SHA-256, target language, output mode, completed stages, artifact
hashes, output paths, counts, and strict reasons. Stages are:

`preflight → inspect → prepare → translate → validate → apply → verify → office-validate → deliver`

Resume at the first incomplete stage. A changed source hash, target language, or output mode starts
a fresh job. If an earlier artifact changes, invalidate that stage and every downstream stage.
Never mark a stage complete until its artifact is saved and hashed.

## Files

- `inventory.json`: sheets, editable occurrences, OOXML features, and unique image groups.
- `translation-manifest.json`: schema-v2 occurrences and safely reusable translation units.
- `relevant-glossary.json`: only glossary rows matched to extracted source text.
- `fixed-translations.en.json`: reviewed exact English labels and units; never fuzzy-matched.
- `verification.json`: deterministic pass/fail result and stable reason codes.
- `office-validation.json`: Microsoft Excel open/recalculation result, worksheet names, used ranges,
  and formula/value error counts.

## Strict escalation

Complex reasons include chart, comment, external link, unsupported drawing, and uncertain image.
Empty tiny legacy shape fragments are decorative and do not trigger this escalation.
Strict reasons include macro/VBA, unsafe legacy conversion, repair warning,
formula/merge/protected-token change, and state-hash mismatch. A bilingual grid rejected by the safety
classifier must use the existing feature-aware strict workflow and must not leave a partial output.
