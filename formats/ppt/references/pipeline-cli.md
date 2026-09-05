# PowerPoint pipeline CLI

Run from `formats/ppt/`:

```powershell
python scripts/ppt_pipeline.py inspect --input <source> --job-dir <job> --target-language <language>
python scripts/ppt_pipeline.py prepare --job-dir <job> --source-language <language-or-auto>
python scripts/validate_manifest.py <job>/translation-manifest.json --require-translations
python scripts/ppt_pipeline.py apply --input <source> --job-dir <job> --output <output.pptx>
python scripts/ppt_pipeline.py verify --source <source> --job-dir <job> --output <output.pptx>
python scripts/ppt_pipeline.py render --source <source> --job-dir <job> --output <output.pptx>
python scripts/ppt_pipeline.py deliver --job-dir <job> --output <output.pptx> --visual-review-passed
```

`prepare` pauses with exit code `3`. Fill all native translation units and assign each unique image
exactly one decision: `skip_target`, `skip_unclear`, or `overlay`. Use `bilingual_below` for editable
overlays. Do not rerun OCR for unclear images.

Embedded objects default to `preserved_untranslated`: retain their binary content and preview images,
report warnings, and continue. Set `pending_native_handler` only for an explicit request to translate
inside an embedded object; validation then blocks delivery until its status becomes `translated`.

The source hash is calculated during `inspect` and compared during `verify`. `render` uses the PPT
module's hidden PowerPoint session to create one low-resolution image for every final slide, with no
external PDF conversion gate. Resume from the first
incomplete stage; do not build a second workflow.
# Compact translation batches

`prepare` also writes `translation-worklist.json`, an index of pending files under `batches/`.
Read those files in order. Roles, context signatures, protected tokens and boundary source context
remain available; read neighboring batches if context is ambiguous. Retain terminology decisions
across batches. The default bounds are 80 units / 12,000 source characters; a paragraph is never split.

```text
python scripts/ppt_pipeline.py batches --job-dir <job>
python scripts/ppt_pipeline.py merge --job-dir <job> --responses <responses.json>
python scripts/ppt_pipeline.py batches --job-dir <job> --ids <unit-id>
```

Results contain `{"job_id":"<from batch>","translations":[{"id":"<unit-id>","translation":"..."}]}`.
No source/occurrence/geometry copies or task-specific scripts are needed. Partial submissions are
supported. Successful items persist even if other items fail. Inspect `translation-merge-report.json`
and resubmit only failed IDs. Exit 2 signals rejected items; foreign job bindings and unknown/duplicate
IDs reject the whole response. The latest report links `translation-retry.json` when there are
rejected IDs, including failed completed-item corrections; ignore stale retry files not linked there.
Run `batches` after interruptions; prepare refuses to overwrite an existing manifest.
For completed-item corrections, export `--ids` and include its exact `previous_translation` in the
response. After corrections, apply, verify and render must run again before visual approval/delivery.

If present, `image-worklist.json` is a READ-ONLY review snapshot, not an image submission file.
Record image decisions/overlays in the existing manifest schema using the existing image workflow.
Text merging preserves these records but does not approve them. All original delivery gates remain.
