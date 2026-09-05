# Excel pipeline CLI

Run commands from `formats/excel/` with the Node.js runtime supplied by the Codex workspace.
Use `work/<source-stem>-<sha256-prefix>/` as the job directory.

## Standard commands

Prepare routing, optional legacy conversion, inspection, and the compact worklist in one command:

```powershell
python scripts/excel_fast_pipeline.py prepare --source <source.xls|xlsx> --job-dir <job-dir> --target-language <language> --output-mode <monolingual|bilingual> --node-path <node.exe> --node-modules <node_modules>
```

Fill only `<job-dir>/translation-worklist.json`, then finish all gates in one command:

```powershell
python scripts/excel_fast_pipeline.py finalize --job-dir <job-dir> --output <translated.xlsx> --node-path <node.exe> --node-modules <node_modules>
```

The runner writes compact JSON to stdout and stage durations to `stage-timings.json`. It suppresses
full inventory output. `finalize` resumes after a completed `apply` or `verify` gate.

## Manual recovery

Use the commands below only when diagnosing a runner failure:

```powershell
node scripts/excel_pipeline.mjs inspect --input <source.xlsx> --job-dir <job-dir> --target-language <language> --output-mode <monolingual|bilingual>
node scripts/excel_pipeline.mjs prepare --job-dir <job-dir>
node scripts/excel_pipeline.mjs apply --input <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs verify --source <source.xlsx> --job-dir <job-dir> --output <translated.xlsx>
node scripts/excel_pipeline.mjs office-validate --job-dir <job-dir> --output <translated.xlsx>
```

`inspect` never renders. Manual `prepare` exits with code `3` intentionally; the fast runner handles
this pause and returns success. Fill only pending records in `translation-worklist.json`; the runner
validates and merges them into `translation-manifest.json`.
`prepare` may already mark reviewed English fixed labels as `translated` and standalone identifiers
as `retain`; translate only records still marked `pending`.

## State and resume

`job-state.json` records source SHA-256, target language, output mode, completed stages, artifact
hashes, output paths, counts, and strict reasons. Stages are:

`preflight → inspect → prepare → translate → validate → apply → verify → office-validate → deliver`

`office-validate` advances directly to `deliver`. The standard pipeline does not render a source
baseline or translated workbook. Visual inspection is separate and runs only when the user explicitly
requests strict layout inspection.

Resume at the first incomplete stage. A changed source hash, target language, or output mode starts
a fresh job. If an earlier artifact changes, invalidate that stage and every downstream stage.
Never mark a stage complete until its artifact is saved and hashed.

## Files

- `inventory.json`: sheets, editable occurrences, OOXML features, and unique image groups.
- `translation-manifest.json`: schema-v2 occurrences and safely reusable translation units.
- `translation-worklist.json`: compact model-facing pending decisions; do not add extra IDs.
- `relevant-glossary.json`: only glossary rows matched to extracted source text.
- `fixed-translations.en.json`: reviewed exact English labels and units; never fuzzy-matched.
- `verification.json`: deterministic pass/fail result and stable reason codes.
- `office-validation.json`: Microsoft Excel source/output recalculation comparison, worksheet names,
  used ranges, and baseline/output/new error counts.
- `stage-timings.json`: cumulative milliseconds for each runner stage.

## Unsupported-feature boundary

Charts, comments, external links, unsupported drawings, uncertain images, macro/VBA content, unsafe
legacy conversion, and repair requirements fail before mutation. Empty tiny legacy shape fragments
remain decorative. Formula, merge, protected-token, and state-hash mismatches fail closed without
starting a second translation or full-workbook rendering pass.
# Compact batches and local retry

The fast runner's `prepare` also emits `translation-batches.json`. Its listed files contain pending
units with source context and protected tokens; completed/autofilled records are not retranslated.
Read the same relevant glossary. Default bounds are 80 units / 12,000 source characters, without
splitting a cell. Preserve terminology across ordered batches; inspect neighboring batches when needed.

```text
python scripts/excel_fast_pipeline.py batches --job-dir <job>
python scripts/excel_fast_pipeline.py merge --job-dir <job> --responses <responses.json>
python scripts/excel_fast_pipeline.py batches --job-dir <job> --ids <unit-id>
```

Response: `{"job_id":"<from batch>","translations":[{"id":"<unit-id>","translation":"..."}]}`.
For unchanged source text include `reason` explaining retention. Return only decisions, not source,
context or full manifests. Merge updates the existing worklist; finalize still owns manifest merging,
apply, verify and real Excel validation. Image decisions stay in the existing worklist's images array;
`image-worklist.json` is a read-only snapshot and text merges never approve images.

Valid items persist atomically; rejected items appear in `translation-merge-report.json` (exit 2).
Foreign job_id, unknown or duplicate IDs reject the complete response. Follow `translation-retry.json`
only when linked by the latest merge report; it contains failed IDs including completed-item corrections.
After interruption run batches, not prepare (which refuses to overwrite an existing manifest).
Export `--ids` to repair selected items; for completed items return the exported
`previous_translation` with the new translation, preventing accidental overwrites. Corrections reset
downstream state and require finalize again, including both verify and office-validate. Existing full
worklist submissions remain compatible. Never replace this flow with task-specific merge scripts.
