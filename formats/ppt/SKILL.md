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
Choose its method per image: generative `image_edit`, or deterministic erase + refill
(`../../scripts/inimage_erase_refill.py`) for technical line drawings. Read
`references/image-text-localization.md` when images exist.
Translate all readable labels in the image and replace it at its original slide position.
Use the shared accepted quality criteria. Native text-box overlays and external legends are
not image translation methods; old overlay decisions are not an allowed processing method.
Insert an accepted edit with decision `localized` and an absolute `replacement_path`. The replacement
writer `scripts/ppt_image_replacements.py` fits it to the source image's exact pixel dimensions, swaps
only the referenced `ppt/media/*` bytes, and leaves the picture shape, its extent, crop, rotation and
relationships untouched; `verify` accepts that one intentional part change and rejects any other.
Require the original aspect ratio, no cropping, and equal-or-higher pixel dimensions; verify actual
dimensions before insertion and never stretch width and height independently.

Charts, SmartArt, notes, actual master/layout text and embedded objects without a native translator
are preserved byte-for-byte with exact warnings. Do not claim they were translated or translate an
embedded object's preview image as a substitute. Template editing prompts are excluded from ordinary
slide translation. Geometry, themes, relationships and animations remain intact.

One exception, and only after seeing it in a render: a legacy OLE/Visio preview that paints
source-language artwork over an already translated slide is a stale overlay, not that slide's content.
Remove it with `scripts/ppt_repairs.py strip-ole-preview` — the slide's container element plus the OLE
container, its VML drawing and rels, the preview media, the slide relationships and the content-type
overrides. Keep and disclose an object whose preview *is* the slide's content, such as an embedded PDF
drawing with no native alternative. Record a removal with `amend-baseline` so verification still runs
against an honest baseline; read `references/powerpoint-workflow.md` for the procedure.

## Verification and delivery

Never overwrite the source or working presentation. Verify source identity, translated locations,
technical values, untouched parts, intended image replacements and placement. Failed writes leave the
previous output intact. Changed decisions invalidate dependent completed work.

A repair keeps that guarantee: copy unchanged parts from the working source and override only the
parts you intend to change, because `verify` compares every non-slide part byte-for-byte (slides are
exempt as `ppt/slides/slide*.xml`; `ppt/slides/_rels/*.rels` is not). Never re-serialise the whole
package through Python — its XML declarations and line endings differ from PowerPoint's and the byte
comparison fails. A repair that must delete package parts runs `scripts/ppt_repairs.py amend-baseline`,
which repoints the job's working source and writes `baseline-amendment.json`; the original working
source is never edited. Re-run `verify` (expect zero errors), then `render`, then deliver.
Translated body text that ends on the slide's bottom band is a defect: measure it with `measure-fit`
and tighten paragraph leading with `fit-text` before adjusting shapes, fonts or frames.

Microsoft PowerPoint renders final slides once in a hidden session with a bounded timeout. When
finalize returns `visual-review`, inspect available slides for clipping, overlap and missing text.
Correct affected decisions as needed. Use `--visual-review-passed` only after actual review; this
continuation reuses verified output and renders. Unavailable rendering may permit structurally
verified output with a disclosed limitation; confirmed opening failures or serious defects still block.

Deliver at `next_stage: deliver`, including warnings about untranslated objects or unreviewed slides.
Do not add external PDF conversion, repeated full-deck checks or repository audits.
