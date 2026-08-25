# PowerPoint pipeline CLI

Run from `formats/ppt/` with the Codex workspace Python runtime. Store artifacts under
`work/<source-stem>-<sha256-prefix>/`.

```powershell
python scripts/ppt_pipeline.py inspect --input <source.ppt-or-pptx> --job-dir <job-dir> --target-language <language>
python scripts/ppt_pipeline.py prepare --job-dir <job-dir> --source-language <language-or-auto>
python scripts/validate_manifest.py <job-dir>/translation-manifest.json --require-translations
python scripts/ppt_pipeline.py apply --input <source.ppt-or-pptx> --job-dir <job-dir> --output <translated.pptx>
python scripts/ppt_pipeline.py verify --source <source.ppt-or-pptx> --job-dir <job-dir> --output <translated.pptx>
python scripts/ppt_pipeline.py render --source <source.ppt-or-pptx> --job-dir <job-dir> --output <translated.pptx>
python scripts/ppt_pipeline.py deliver --job-dir <job-dir> --output <translated.pptx> --visual-review-passed
```

`prepare` exits with code `3` intentionally after producing the manifest. Fill
`translation_units[].translation`; do not edit or remove occurrences. Screen every unique image
once and fill `text_screening.labels`; uncovered labels and `pending` groups block apply. Set each
group to `retain`, `localize`, or `manual_review`. Use only `bilingual_below`: place editable target
text immediately below each source label or in the nearest safe blank area while preserving the
source image and pixels. If a label has no safe placement, use `manual_review`; never erase, cover,
patch, regenerate, or replace image text. If the complete target language already exists, use `retain`
with `target-language-already-present`; the pipeline skips that image. Localized images
automatically select the single PowerPoint COM apply route so native text and overlays save once.

After `render`, inspect the generated target thumbnails and every requested high-resolution risk
slide. Run `deliver` only after that visual review passes; `render` never marks the file delivered.

For `.ppt`, `inspect` internally converts an immutable working copy to `working-source.pptx` with
Microsoft PowerPoint. The original remains the hashed source and the output is `.pptx`.

Exit codes:

- `0`: stage passed.
- `2`: invalid input, manifest, state, mutation, verification, or Office export.
- `3`: expected translation pause after `prepare`.

Artifacts:

- `inventory.json`: one-pass structure, text, image groups, and risk classification.
- `translation-manifest.json`: schema-v2 occurrences and translation units.
- `job-state.json`: stages, hashes, route, output, COM counts, and pass counts.
- `apply-report.json`: mutation engine and replacement counts.
- `verification.json`: deterministic pass/fail result and reason codes.
- `render-plan.json`: low/high-resolution source and target slide sets.
- `final.pdf`, `final-renders/`, `office-verification.json`: PowerPoint-authoritative output.

Resume from the first incomplete stage. A changed source hash, target language, manifest, or output
invalidates its stage and all downstream stages. Do not treat code `3` as failure.
