# PowerPoint image-localization overlay manifest

Use editable PowerPoint overlays. The host image object and its pixels remain unchanged.

Every new image overlay uses:

- `kind: office_overlay`;
- `localization_mode: bilingual_below`;
- non-empty `source_text` and `translation`;
- the source label's normalized `source_region` inside the host image;
- a normalized target `region` immediately below `source_region`;
- `background.mode: transparent`;
- `location.page_or_slide`, `host_shape_id`, and a stable `region_id`;
- readable font, color, alignment, and positive size.

The target region remains within the host image, does not overlap the source region, and uses a
transparent background. Prefer immediately below the source label; otherwise use the nearest safe
blank area. If no safe area exists, record `manual_review`. Never erase, cover, patch, regenerate,
or replace source text inside the image.

If the image already fully contains the requested target language, create no overlay. Mark the
image group `retain` with `reason_code: target-language-already-present` and skip it. Partial
bilingual images receive overlays only for missing target-language labels.

Overlay IDs must be unique. Never place an overlay on legal evidence or outside its host image.
Final verification confirms the original image SHA-256 is unchanged, every detected label has a
final status, and every added translation is editable and safely placed.
