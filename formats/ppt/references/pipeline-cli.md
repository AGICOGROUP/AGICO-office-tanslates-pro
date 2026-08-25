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

The source hash is calculated during `inspect` and compared during `verify`. `render` uses the PPT
module's hidden PowerPoint session to create one low-resolution image for every final slide, with no
external PDF conversion gate. Resume from the first
incomplete stage; do not build a second workflow.
