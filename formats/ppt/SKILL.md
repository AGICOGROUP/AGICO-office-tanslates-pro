---
name: office-translate-pro-ppt
description: Use when translating PowerPoint presentations (.ppt or .pptx) while preserving editable native text, technical tokens, images and layout with Microsoft PowerPoint verification.
---

# Professional PowerPoint Translation

Top-level routing is complete. Do not run the root Office router again or read another format adapter.

## Standard task

From this adapter directory:

```text
python ../../scripts/office_pipeline.py prepare <source> --job-dir <job> --target-language <language>
python ../../scripts/office_pipeline.py merge --job-dir <job> --decisions <batch.json>
python ../../scripts/office_pipeline.py finalize --job-dir <job> --output <translated.pptx>
python ../../scripts/office_pipeline.py finalize --job-dir <job> --output <translated.pptx> --visual-review-passed
```

Read [translation decisions](../../references/translation-decisions.md), then
`translation-worklist.json` and `relevant-glossary.json` initially. Translate complete
paragraphs and table cells using the returned batches and context. Preserve `job_identity`, IDs and
source text. Merge completed subsets; successful decisions remain saved and only missing or invalid
items need repair. Small jobs may fill the default worklist and finalize directly.

The entry delegates native operations to `scripts/ppt_pipeline.py`; existing commands remain for
troubleshooting. Read CLI/manifest references only when needed. The matched subset of
`../../references/水泥专业名词中英对照.md` is resolved before model translation. Use exact phrases first,
then the longest applicable term and its context/aliases. Chinese targets support reverse English
lookup. Do not load the entire glossary during ordinary work.

## Native text and images

Preserve numbers, units, models, standards, formulas and meaningful line breaks. Equivalent unit
spacing is allowed; changed values, prefixes and identifiers are not. Preserve boundary spaces and
remove unsafe inherited negative spacing from Latin translations.

Screen every unique image once and follow [the shared in-image translation rule](../../references/image-translation.md).
Use only GPT image editing and read `references/image-text-localization.md` when images exist.
Translate all readable labels in the image and replace it at its original slide position.
Use the shared accepted quality criteria. Native text-box overlays and external legends are
not image translation methods. The current low-level writer needs verified image-replacement
support before integrated delivery; do not bypass this by using old overlay support.
Require the original aspect ratio, no cropping, and equal-or-higher pixel dimensions; verify actual
dimensions before insertion and never stretch width and height independently.

Charts, SmartArt, notes, actual master/layout text and embedded objects without a native translator
are preserved byte-for-byte with exact warnings. Do not claim they were translated or translate an
embedded object's preview image as a substitute. Template editing prompts are excluded from ordinary
slide translation. Geometry, themes, relationships and animations remain intact.

## Verification and delivery

Never overwrite the source or working presentation. Verify source identity, translated locations,
technical values, untouched parts, intended image replacements and placement. Failed writes leave the
previous output intact. Changed decisions invalidate dependent completed work.

Microsoft PowerPoint renders final slides once in a hidden session with a bounded timeout. When
finalize returns `visual-review`, inspect available slides for clipping, overlap and missing text.
Correct affected decisions as needed. Use `--visual-review-passed` only after actual review; this
continuation reuses verified output and renders. Unavailable rendering may permit structurally
verified output with a disclosed limitation; confirmed opening failures or serious defects still block.

Deliver at `next_stage: deliver`, including warnings about untranslated objects or unreviewed slides.
Do not add external PDF conversion, repeated full-deck checks or repository audits.
