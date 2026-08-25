---
name: translate-image-professionally
description: Use when translating one static PNG, JPG, or JPEG image while preserving its pixel dimensions, layout, photographs, diagrams, tables, icons, logos, colors, and non-text pixels. Reuses the scan-PDF raster workflow through a one-page PDF bridge and returns the same image format.
---

# Professional Image Translation

## Scope

Translate one static PNG or JPEG image. Return the same image format with the same pixel dimensions. Reject GIF, SVG, multi-page TIFF, animated images, and image batches in this version.

## Required Workflow

Read `formats/pdf/scan/SKILL.md` and all references it requires. Apply its OCR inventory, translation, glyph-only cleanup, icon fidelity, terminology, layout, visual review, and residual-language gates without weakening them.

1. Fingerprint the immutable source image and create an isolated job directory.
2. Run `scripts/image_pdf_bridge.py wrap <source-image> <job/source.pdf> <job/image-metadata.json>`.
3. Treat `job/source.pdf` as a one-page scan-only PDF. Follow `formats/pdf/scan/SKILL.md` from extraction through verified translated PDF output. Do not run the PDF classifier; the bridge output is deliberately raster-only.
4. Run `scripts/image_pdf_bridge.py unwrap <translated.pdf> <job/image-metadata.json> <output-image>`.
5. Visually compare the final image with the original at full view and high zoom. Apply the scan quality gates to the single image, excluding only PDF-specific selectability, font-embedding, and page-count delivery requirements.

## Image Output Contract

- Preserve the same pixel dimensions and same image format as the normalized source.
- Preserve PNG alpha using the source alpha channel; translated visible pixels still come from the verified scan workflow.
- Save JPEG at high quality without changing its dimensions.
- The raster output cannot contain selectable text. Keep the verified translated PDF as an optional secondary artifact only when the user requests selectable text.
- Never resize, crop, stretch, regenerate, or globally inpaint the image.

## Commands

Use the Python interpreter available in the current runtime:

```powershell
python scripts/image_pdf_bridge.py wrap "source.png" "job/source.pdf" "job/image-metadata.json"
python scripts/image_pdf_bridge.py unwrap "job/translated.pdf" "job/image-metadata.json" "translated.png"
```
