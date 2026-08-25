# PowerPoint embedded-image translation

## Screen unique media only

Use `inventory.json.image_groups`. Review each SHA-256 group once and apply the decision to every
recorded slide/shape occurrence. Skip this workflow when no media groups exist.

- `retain`: no translatable source text, or the image is already fully bilingual and contains the
  requested target language.
- `localize`: source labels need target-language partners.
- `manual_review`: uncertain reading, incomplete existing bilingual content, or unsafe placement.

When the complete target language is already present, skip the image and record
`reason_code: target-language-already-present`. Do not add duplicate translations. If only some
labels have target-language partners, add only the missing partners.

## Required localization mode

PowerPoint embedded images only use `localization_mode: bilingual_below` with
`preserve_source_image: true`:

1. Preserve the original image, original pixels, and source-language labels unchanged.
2. Add each target-language translation as a transparent, editable PowerPoint text box immediately below
   its corresponding source label.
3. Match the local alignment, color, and readable scale without covering equipment, arrows,
   linework, dimensions, or another label.
4. If the space below is insufficient or the pairing is uncertain, use `manual_review`.

Do not erase, cover, patch, inpaint, or replace the original image text. Preserve crop, aspect
ratio, anchors, z-order, numbers, units, tags, arrows, process lines, symbols, equipment, and flow
direction. This rule applies only to images embedded in PowerPoint; other adapters keep their own
image policies.
