---
name: translate-powerpoint-professionally
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

Read only `translation-worklist.json` and `relevant-glossary.json` initially. Translate complete
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

Screen every unique image once. PowerPoint embedded images only use:

- `skip_target`: every readable source label already has its target-language equivalent.
- `skip_unclear`: no source label is readable with confidence; small but readable labels count.
- `overlay`: readable labels need translation. Preserve the original image and add editable text
  immediately below each label using `bilingual_below`.

For overlays read `references/image-text-localization.md` and `references/overlay-schema.md`. Put
editable objects in the image decision's `overlays` array. Native transparent text boxes are written
in the same atomic OOXML pass as text, without starting Office. Images are never erased, regenerated
or replaced. Grouped, rotated or flipped hosts need supported placement; correct the affected decision.

Charts, SmartArt, notes, actual master/layout text and embedded objects without a native translator
are preserved byte-for-byte with exact warnings. Do not claim they were translated or translate an
embedded object's preview image as a substitute. Template editing prompts are excluded from ordinary
slide translation. Geometry, themes, relationships and animations remain intact.

## Verification and delivery

Never overwrite the source or working presentation. Verify source identity, translated locations,
technical values, untouched parts, image bytes and overlay text/geometry. Failed writes leave the
previous output intact. Changed decisions invalidate dependent completed work.

Microsoft PowerPoint renders final slides once in a hidden session with a bounded timeout. When
finalize returns `visual-review`, inspect available slides for clipping, overlap and missing text.
Correct affected decisions as needed. Use `--visual-review-passed` only after actual review; this
continuation reuses verified output and renders. Unavailable rendering may permit structurally
verified output with a disclosed limitation; confirmed opening failures or serious defects still block.

Deliver at `next_stage: deliver`, including warnings about untranslated objects or unreviewed slides.
Do not add external PDF conversion, repeated full-deck checks or repository audits.
