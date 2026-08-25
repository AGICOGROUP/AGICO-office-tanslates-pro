# PowerPoint embedded-image translation

## Screen unique media once

Use `inventory.json.image_groups`. Run one single-pass OCR screen per SHA-256 group, visually confirm the OCR
result once, and apply the decision to every recorded slide/shape occurrence. Do not rerun OCR for
duplicate image bytes. Record every detected source label in `text_screening.labels`; each label
ends as `localized`, `target-language-already-present`, or `manual_review`.

- `retain`: no translatable source text, or the image is already fully bilingual and contains the
  requested target language.
- `localize`: source labels need target-language partners.
- `manual_review`: uncertain reading or an unsafe replacement mask.

When the complete target language is already present, skip the image and record
`reason_code: target-language-already-present`. Do not add duplicate translations. If only some
labels have target-language partners, add only the missing partners.

Native text outside an image does not cover source text detected inside that image. The reason
`source-labels-covered-by-native-text` is invalid when image text exists.

## Two precision localization modes

Prefer `localization_mode: bilingual_below` with `preserve_source_image: true`:

1. Preserve the original image, original pixels, and source-language labels unchanged.
2. Add each target-language translation as a transparent, editable PowerPoint text box immediately below
   its corresponding source label.
3. Match the local alignment, color, and readable scale without covering equipment, arrows,
   linework, dimensions, or another label.
4. If the space below is insufficient, use `text_region_replace`.

`text_region_replace` covers only a confirmed source-text region with a lossless patch and writes
editable target text inside that exact region. The source image object remains unchanged beneath
the patch. The patch mask and text region must match, and the automatic outside-mask comparison
must report zero changed pixels. If a safe mask cannot be proved, use `manual_review`.

Both modes preserve crop, aspect ratio, anchors, z-order, numbers, units, tags, arrows, process
lines, symbols, equipment, and flow direction. Run high-resolution review only for an automatic
gate failure or a `manual_review` item.
