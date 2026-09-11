# Excel pipeline CLI

Run commands from `formats/excel/` with the Node.js runtime supplied by the Codex workspace.
Use `work/<source-stem>-<sha256-prefix>/` as the job directory.

Use the bundled Python interpreter. Runtime flags are optional in a standard Codex installation:
the runner resolves Node, the official artifact-tool package and PowerShell 7 from that runtime.
Explicit flags/environment variables take precedence. `--node-modules` is supported by the ESM
loader directly, so no repository junction or package installation is needed. The default converted
copy is `<job-dir>/source-working.xlsx`, keeping independent translation jobs separate.

## Standard commands

Prepare routing, optional legacy conversion, inspection, and the compact worklist in one command:

```powershell
python scripts/excel_fast_pipeline.py prepare --source <source.xls|xlsx> --job-dir <job-dir> --target-language <language> --output-mode <monolingual|bilingual>
```

Fill only `<job-dir>/translation-worklist.json`, then finish all gates in one command:

```powershell
python scripts/excel_fast_pipeline.py finalize --job-dir <job-dir> --output <translated.xlsx>
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

## Preservation boundary

Monolingual `inspect`, `apply`, and `verify` use `excel_native_ooxml.py` through the existing Node
commands. They read sparse cells and patch the source OOXML package atomically. Shared strings are
split into per-cell inline strings when translated; rich run properties and original styles survive.
Only translated cells, cloned wrapping styles and affected row heights may change. Other ZIP parts
remain byte-identical, including charts, comments, drawings, relationships and unknown extensions.
Their complex text is preserved without translation and disclosed by part name in the manifest and
verification report. Formula input text is retained with cell counts and examples.

Bilingual paired-row reconstruction remains limited to simple grids and rejects unsupported complex
features. Macro/VBA content (including renamed `.xlsx` packages), unsafe legacy conversion and repair
requirements still fail. Unresolved image decisions still require review. Localized image replacement
joins the monolingual atomic write and must preserve format, dimensions and verified replacement hash.

Native verification checks coverage, formulas, numbers, rich formatting, original styles, merges,
sheet structure and untouched part bytes before replacing an existing output. External data links
are preserved without refresh; `office-validate` skips recalculation with an explicit warning for
those workbooks. An unavailable Office runtime is also disclosed after static verification passes;
detected damage still blocks delivery.
