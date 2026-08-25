# Excel pipeline CLI

Run commands from `formats/excel/` with the Node.js runtime supplied by the Codex workspace.
Use `work/<source-stem>-<sha256-prefix>/` as the job directory.

## Commands

```powershell
node scripts/excel_pipeline.mjs inspect --input <source.xlsx> --job-dir <job-dir> --target-language <language> --output-mode <monolingual|bilingual>
node scripts/excel_pipeline.mjs prepare --job-dir <job-dir>
node scripts/excel_pipeline.mjs apply --input <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs verify --source <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs render --job-dir <job-dir> --output <translated.xlsx>
```

`prepare` exits with code `3` intentionally. This means `translation-manifest.json` is ready for
Codex/GPT to translate; it is not a failure. Fill every `translation_units[]` record, set `status`
to `translated` or justified `retain`, preserve every protected token, and validate the manifest.

## State and resume

`job-state.json` records source SHA-256, target language, output mode, completed stages, artifact
hashes, output paths, counts, and strict reasons. Stages are:

`preflight → inspect → prepare → translate → validate → apply → verify → render → deliver`

Resume at the first incomplete stage. A changed source hash, target language, or output mode starts
a fresh job. If an earlier artifact changes, invalidate that stage and every downstream stage.
Never mark a stage complete until its artifact is saved and hashed.

## Files

- `inventory.json`: sheets, editable occurrences, OOXML features, and unique image groups.
- `translation-manifest.json`: schema-v2 occurrences and safely reusable translation units.
- `verification.json`: deterministic pass/fail result and stable reason codes.
- `render-plan.json`: selected sheets, balanced/strict mode, image plan, and render reasons.
- `renders/preflight/` and `final-renders/`: required PNG previews.

## Strict escalation

Strict reasons include macro/VBA, unsafe legacy conversion, chart, comment, external link,
unsupported drawing, repair warning, formula/merge/protected-token change, uncertain image,
state-hash mismatch, and print-page verification required. A bilingual grid rejected by the safety
classifier must use the existing feature-aware strict workflow and must not leave a partial output.
