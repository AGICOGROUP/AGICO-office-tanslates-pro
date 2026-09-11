---
name: translate-excel-professionally
description: Use when translating monolingual or bilingual Excel workbooks (.xls or .xlsx), especially technical tables whose formulas, layout, images and editable structure must be preserved.
---

# Professional Excel Translation

Top-level routing is complete. Do not run the root Office router again or read another format adapter.

## Standard task

From this adapter directory:

```text
python ../../scripts/office_pipeline.py prepare <source> --job-dir <job> --target-language <language> --output-mode monolingual
python ../../scripts/office_pipeline.py merge --job-dir <job> --decisions <batch.json>
python ../../scripts/office_pipeline.py finalize --job-dir <job> --output <translated.xlsx>
```

Use `--output-mode bilingual` for paired translation rows. Read
[translation decisions](../../references/translation-decisions.md), then `translation-worklist.json` and
`relevant-glossary.json`. Follow its batches, keeping `job_identity`, IDs and source strings intact.
Fill `translation` in the supplied worklist and merge completed subsets. For a small batch, fill the
default worklist and call finalize directly; it performs merge itself. When using explicit merge,
continue to finalize only when its JSON says `ready: true`; exit code 0 alone does not mean ready.
Repair only rejected items from the refreshed worklist. Accepted work persists. Repeated
prepare/finalize resumes work; use status only to recover uncertain or interrupted state.

Existing jobs can still use `scripts/excel_fast_pipeline.py prepare` and
`scripts/excel_fast_pipeline.py finalize`. Runtimes resolve from bundled dependencies; do not install
packages or create runtime junctions per job. `stage-timings.json` measures pipeline commands, not
end-to-end translation, image generation, model work or waiting. Use actual task/tool timestamps
when investigating total latency; do not describe pipeline milliseconds as total task time.

## Translation and preservation

Use matched glossary terms with cell context and aliases, including reverse English lookup for
Chinese targets. Preserve engineering meaning, numbers, units, models, identifiers and line breaks.
Safe labels are prefilled; ambiguous terminology stays pending. Context-safe and parameter-label
reuse reduce repeated translation. Do not translate individual formatting runs separately.

Monolingual output patches original OOXML cells and expands only affected rows. Shared-string edits
remain local to each cell, including rich text. Original formulas, typed values, styles, merges,
charts, comments, drawings, media, relationships and unknown package parts are preserved. Unsupported
complex-object text remains untranslated with explicit warnings. Formula-dependent source labels may
be retained to preserve calculation; disclose this limitation rather than claiming complete translation.

Bilingual paired blue rows use a separate reconstruction writer for grid-safe workbooks. Read
`references/bilingual-row-layout.md` for this mode. Unsupported objects and row-sensitive formulas
need a supported layout choice; never silently discard objects or substitute monolingual output.

## Images and delivery

Read `references/image-text-localization.md` only when images exist. Review each unique image once;
choose `reviewed`, `retain` or `localized`. Localization requires an absolute `replacement_path` to
an edited PNG/JPEG of the original format and dimensions. Start required image editing after reading
its labels, then use asynchronous generation time to translate/review/merge cells. Do not leave the
text batch untouched while repeatedly waiting for images. The writer replaces every matching part
and verifies actual bytes; status alone is not translation. Disclose labels left untranslated.

The source stays unchanged. `.xls` converts once to a working `.xlsx`. Corrupt, encrypted and
macro-enabled containers remain unsupported; VBA is never enabled. External relationships are
preserved without refresh, and native recalculation is skipped with a warning when external data
would be evaluated.

Finalize verifies coverage, typed values, formulas, merges, sheet order and untouched package parts.
Ordinary native checking uses Microsoft Excel read-only with a bounded timeout. Missing Office or
timeout allows the verified file with a warning; confirmed opening failures, new formula errors or
content damage require repair. Accepted decisions survive repair. Deliver at `next_stage: deliver`.
Do not rerun repository tests, export PDF or add an ordinary visual gate. Read pipeline references
only for a concrete troubleshooting need.
