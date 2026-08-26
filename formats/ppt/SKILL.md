---
name: translate-powerpoint-professionally
description: Use when translating PowerPoint presentations (.ppt or .pptx) while preserving editable native text, technical tokens, images, and layout with Microsoft PowerPoint verification.
---

# Professional PowerPoint Translation

Top-level routing is complete when this module starts. Do not run the root Office router again,
read another format adapter, or consider another format workflow.

Use `scripts/ppt_pipeline.py` as the single production entry. Preserve the immutable source, write
one separate `.pptx`, translate native text in place, and use Microsoft PowerPoint as final
authority.

Classify content by capability: selectable or copyable text belongs to an editable-content handler,
including charts and SmartArt. Preserve OLE/Visio/PDF embedded objects, their binary content, and
their preview images unchanged by default; record a warning and continue translating ordinary slide
content. Never translate the preview image as a substitute for the object. Only when the user explicitly
requests translation inside an embedded object, set it to `pending_native_handler` and stop if its native
editor or handler is unavailable.

## Read only what is needed

Read `references/powerpoint-workflow.md`, `references/pipeline-cli.md`, and
`references/manifest-schema.md`. The shared glossary is
`../../references/水泥专业名词中英对照.md`; do not load it completely. After text extraction,
use `scripts/resolve_repo_glossary.py` to retrieve only relevant source-matched terms, resolving
exact phrases first and then the longest non-overlapping terms before model translation. Read
`references/image-text-localization.md` only when images exist and `references/overlay-schema.md`
only when an image needs an overlay.

## One lightweight flow

1. `inspect`: hash the source once, inventory editable text and tables, and group identical images.
2. `prepare`: create location-safe, deduplicated translation units and pause for batch translation.
3. Fill native translations using the matched glossary subset. Screen every unique image once.
4. Apply exactly one image decision:
   - `skip_target`: every readable source label already has its target-language equivalent; partial target text never skips the whole image.
   - `skip_unclear`: no source label is readable with confidence; small but readable labels must not be skipped.
   - `overlay`: at least one readable source label still lacks the target language; preserve the original image and add editable
     target-language text immediately below each source label using `bilingual_below`.
5. `apply`: write all native translations and overlays once.
6. `verify`: compare the final source hash, package integrity, slide count, translations, protected
   tokens, and required overlays.
7. `render`: open the output in one hidden, alert-suppressed Microsoft PowerPoint session and
   render every final slide once at low resolution. Do not use an external PDF conversion gate.
8. Review the final slides and run `deliver --visual-review-passed`.

## Quality boundary

- Preserve masters, layouts, themes, geometry, z-order, animations, relationships, media, arrows,
  process lines, numbers, units, models, standards, and formulas.
- Keep native translations and image overlays selectable and editable.
- Keep default-preserved embedded objects byte-for-byte unchanged and report them as untranslated warnings.
- PowerPoint embedded images only use `skip_target`, `skip_unclear`, or `overlay`.
- Never erase, cover, patch, regenerate, redraw, or replace an image.
- Allow natural wrapping and repair only actual clipping, overlap, missing text, or broken layout.
- Never use LibreOffice unless PowerPoint is unavailable and the user explicitly authorizes it.

Deliver when the output opens without repair, native translation coverage passes, protected tokens
match, image decisions are complete, and the final visual review passes.
