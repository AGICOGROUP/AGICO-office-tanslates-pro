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

`apply` uses native OOXML for paragraph translations and editable image overlays; PowerPoint COM is
needed for legacy `.ppt` conversion and final rendering. The source and converted working copy are
hashed during `inspect` and checked before `apply`; source integrity is rechecked during `verify`.
Writes replace only the generated output after the ZIP closes successfully, preserving any prior
output on failure. Complex untranslated parts are listed in `preserved_parts` and delivery warnings.
`render` uses the PPT
module's hidden PowerPoint session to create one low-resolution image for every final slide, with no
external PDF conversion gate. Rendering has a 60-second timeout. If native rendering is unavailable,
the pipeline records a warning; review any available slide images and disclose unreviewed pages.
Only when no pages were rendered, run `deliver` without `--visual-review-passed`. Opening failures
and structural verification failures still stop delivery. Resume from the first
incomplete stage; do not build a second workflow.
