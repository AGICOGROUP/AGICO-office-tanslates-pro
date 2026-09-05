# Word raster image localization

Review each unique embedded image byte sequence once. Preserve logos, photographs, decorative
assets, arrows, equipment, topology, numbers, units, colors, crop, dimensions, and aspect ratio.

For a bilingual image, keep every readable source label and add its translated label inside the
same raster image, immediately below or beside the source label when space permits. Use a compact,
borderless font by default. Never cover, erase, regenerate, or move source content.

Create a JSON plan with one entry per localized `word/media/*` part. Each overlay declares an
approved rectangle (`x`, `y`, `width`, `height`), translated `text`, and optional `font_size`,
`color`, `stroke_width`, `stroke_fill`, and `align`. `stroke_width` defaults to `0`; add an outline
only when the user explicitly requests one. Run:

```text
python scripts/word_pipeline.py localize-images translated.docx --plan image-localization.json --output bilingual.docx
```

The command refuses missing or orphaned images, keeps the source DOCX unchanged, verifies the
image format and pixel dimensions, proves that edits before image encoding stay inside approved
rectangles, preserves the document's media-reference inventory, and writes
`image-localization-report.json` beside the plan. JPEG encoding can introduce visually negligible
compression changes; use quality 98 with no chroma subsampling and inspect every changed image at
native resolution.

Deliver only after `validate` passes on the localized DOCX. The validation baseline includes both
the media files and the media parts that are still referenced from Word content, so orphaned media
cannot satisfy the gate.
