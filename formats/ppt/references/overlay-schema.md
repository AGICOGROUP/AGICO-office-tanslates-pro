# PowerPoint bilingual image-overlay manifest

Use editable PowerPoint overlays for image translation. The host image and its source-language
pixels remain unchanged.

Every new image overlay uses:

- `kind: office_overlay`;
- `localization_mode: bilingual_below`;
- non-empty `source_text` and `translation`;
- the source label's normalized `source_region` inside the host image;
- a normalized target `region` immediately below `source_region`;
- `background.mode: transparent`;
- `location.page_or_slide`, `host_shape_id`, and a stable `region_id`;
- readable font, color, alignment, and positive size.

The target region must remain within the host image and must not overlap the source region. Do not
use solid fills, image patches, source cleanup, inpainting, or source-text replacement for new PPT
image translations. If no safe below-label region exists, record `manual_review`.

If the image already fully contains the requested target language, create no overlay. Mark the
image group `retain` with `reason_code: target-language-already-present` and skip it. Partial
bilingual images receive overlays only for missing target-language labels.

Overlay IDs must be unique. Never place an overlay on legal evidence or outside its host image.
Final verification must confirm the original image SHA-256 is unchanged, every added translation
is editable, and no overlay clips or obscures technical content.
