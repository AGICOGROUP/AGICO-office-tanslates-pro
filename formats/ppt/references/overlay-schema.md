# PowerPoint image-localization overlay manifest

Use editable PowerPoint overlays for both precision modes. The host image object remains unchanged.

Every new image overlay uses:

- `kind: office_overlay`;
- `localization_mode: bilingual_below`;
- non-empty `source_text` and `translation`;
- the source label's normalized `source_region` inside the host image;
- a normalized target `region` immediately below `source_region`;
- `background.mode: transparent`;
- `location.page_or_slide`, `host_shape_id`, and a stable `region_id`;
- readable font, color, alignment, and positive size.

For `bilingual_below`, the target region remains within the host image and does not overlap the
source region; use a transparent background.

For `text_region_replace`, set `localization_mode: text_region_replace`, make `region` exactly equal
to `source_region`, and use `background.mode: image_patch` with a lossless patch asset. The image
group must include `outside_mask_pixel_check: {"passed": true, "changed_pixels": 0}`. If the mask
would touch a number, unit, model, arrow, line, symbol, or equipment boundary, record
`manual_review`.

If the image already fully contains the requested target language, create no overlay. Mark the
image group `retain` with `reason_code: target-language-already-present` and skip it. Partial
bilingual images receive overlays only for missing target-language labels.

Overlay IDs must be unique. Never place an overlay on legal evidence or outside its host image.
Final verification confirms the original image SHA-256 is unchanged, every added translation is
editable, and the selected mode's geometry and outside-mask gate pass.
