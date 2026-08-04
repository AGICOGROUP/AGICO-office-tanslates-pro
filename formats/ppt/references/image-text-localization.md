# PowerPoint image-text localization

Extract each original embedded image at native resolution. Never use a slide screenshot, thumbnail, earlier translated presentation, or generated redraw as the image source.

## Method order

1. Edit native PowerPoint text when it exists.
2. On a verified uniform, semantic-free background, remove only the source glyph region with `scripts/make_text_patch.py` and add a transparent native text box.
3. When text touches linework, arrows, borders, gradients, texture, or equipment, use a lossless local repair patch that restores every non-text pixel, then add the native text box.
4. If reading or repair cannot be verified, preserve the region and record manual review.

The cleanup mask follows source glyphs; the English text frame may be wider and remains transparent. Never enlarge an opaque patch to fit a longer translation.

## Engineering protection

- Preserve every number, unit, tag, standard, arrow, leader line, process line, symbol, equipment component, and flow direction.
- Never redraw the complete diagram or use broad generative inpainting.
- Preserve original crop, aspect ratio, anchors, rotation, color, and z-order.
- Require zero changed pixels outside approved text masks.
- Verify connected-line continuity and compare dense diagrams at 3x using side-by-side and alpha-overlay review.

## Editable result

Keep translated image labels as native PowerPoint text boxes whenever possible. They must remain selectable, copyable, and editable. Use lossless raster output only for the local repaired background layer.
