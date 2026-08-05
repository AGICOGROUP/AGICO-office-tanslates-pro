# Selectable text and image-text reconstruction

## Why flattening failed

A page-render/erase/redraw pipeline can look correct while converting all text
to pixels. That destroys the source document's selectable/copyable behavior.
When native source text matters, the rebuild must preserve a PDF text layer:

1. clone the original PDF;
2. remove original text-show operations from page and Form streams;
3. preserve non-text vectors, images, geometry, and resources;
4. add translated text as embedded TrueType vector text;
5. verify extraction and copy/paste.

Checking only visible output is insufficient. Count text-show operators and
extract representative text from the final file.

## Why broad image editing failed

The rejected approaches were:

- regenerating the whole engineering diagram;
- inpainting a broad region around a label;
- covering Chinese with opaque white rectangles;
- replacing a page with a screenshot.

All can blur thin process lines, hide structure, shift colors, or reduce
resolution. The accepted invariant is:

> Outside explicit source-glyph regions, every original image pixel remains
> unchanged.

## Accepted image-label method

1. Work from the original embedded image, never a screenshot of a translated
   PDF.
2. Locate the exact Chinese glyph bounds.
3. Build a glyph mask from neutral or label-color pixels.
4. Protect process-line colors and any structural component crossing the text
   region.
5. Remove glyph pixels only and save a clean raster base.
6. Reinsert the clean image at the exact original page geometry.
7. Add compact English as an embedded PDF vector text layer mapped from image
   pixel coordinates to page coordinates.
8. Compare source/clean arrays and fail on any unexpected pixel change.

When a label area contains no drawing pixels, it is acceptable to clean the
complete text-only band. It is never acceptable to clear a band that crosses
equipment, rules, arrows, or process lines.

## Selectability and image QA checklist

- Native source text remains extractable and selectable.
- No original source text survives invisibly below overlays.
- No extractable CJK remains.
- All clear image labels are English.
- Image-label English is extractable, selectable, and remains sharp when zoomed.
- Genuinely illegible labels are logged instead of guessed.
- Image pixels outside approved text regions are byte-identical.
- Saturated engineering-line pixels are unchanged.
- Rebuilt image dimensions match the source image dimensions.
- Page placement and aspect ratio match the source.
- Full-page render shows no white-box damage, blur, overlap, or square glyphs.

## Native layout reconstruction rules

PDF extraction blocks are evidence, not layout containers. A source paragraph
may be split into one block per visual line, while one extracted table line may
cross several cells. Rebuilding each block independently causes inconsistent
font sizes, lost centering, image collisions, and cell overflow.

Use these invariants:

1. Determine semantic roles from source font family, source weight, numbering,
   position, and reading-text-weighted font-size frequency. Absolute point size
   alone is not a heading signal.
2. Merge compatible source lines into one paragraph flow. Fit the translation
   once across the original line slots so every line uses one font size.
3. Preserve left/center/right alignment. A symmetric full-width body line is
   body copy, not a centered title.
4. Use embedded-image boxes as exclusion geometry. A continuation slot that
   intersects most of an image is forbidden.
5. Segment table text by physical cell, including extraction blocks that cross
   several cells. Aggregate all fragments assigned to the same cell and render
   that cell exactly once.
6. Use exact font ascent, descent, spacing, and line count for vertical fitting.
   Ink-bounding-box height alone underestimates PDF line height and can cross a
   lower border.
7. Shrink dense cell text uniformly. Never expand a cell container to the page
   edge and never let one cell borrow space from a neighbor.
8. Keep semantic role and font weight separate. A heading role does not grant
   bold. Use the source run/font evidence; if the PDF metadata cannot represent
   a visually verified weight, set a block-level `source_bold_override`.
9. Do not use the smallest paragraph as the page-wide body size. Use a median
   fitted baseline. Before shrinking one paragraph independently, apply the
   page-level adaptive layout procedure below. Native body text should stay at
   or above `max(9.5 pt, 60% of source size)` unless the entire page is
   genuinely dense. Tighten the English wording before crossing that floor.
10. Treat new numbered items as paragraph boundaries, but do not mistake decimal
    values such as `0.5` for list numbers. Semicolon-separated equipment lists
    remain one flow.
11. Preserve header/footer source size and verified visual weight. Replacement
    font metrics may require a taller container, not a smaller font.

These are source-level rules. Do not fix the same failures with page IDs,
coordinate patches, or document-specific block suppressions.

## Adaptive single-page layout planning

Treat the page as a composition, not as frozen independent boxes. Trigger a
review when same-level headings differ by more than 0.5 pt, body prose differs
by more than 0.5 pt outside tables/captions, or prose falls below its preferred
size while an image or vertical region leaves reclaimable whitespace.

Use this order:

1. Choose one body-size target for the page and one bold size target for each
   source-verified heading level. A heading should remain visibly larger than
   body copy.
2. Reclaim empty regions before shrinking text: when an image box consumes page
   area needed by prose, moderately reduce its footprint and reposition it, or
   move a lower content region downward to rebalance top and bottom whitespace.
   Do not enlarge an image merely to fill blank space when prose needs that area.
3. Preserve original image pixels and aspect ratio; never crop or regenerate
   the image. Move its caption with it, retain reading order, and leave about
   8–12 pt clearance from text and neighboring objects.
4. Merge reviewed paragraph flows or add safe text slots in the reclaimed area,
   then tighten redundant English without deleting technical meaning.
5. If the page is still genuinely dense, use one smaller body size across that
   page instead of a patchwork of unrelated sizes. Keep heading levels
   consistent and distinct.
6. Only after these options fail, use a continuation page or report the layout
   limitation.

This is an adaptive decision sequence, not permission to redesign arbitrarily:
keep page count, visual hierarchy, object order, colors, and source identity
unless the user explicitly authorizes a broader redesign.

## Proven recovery strategy

If a translated version is flattened or its diagram is damaged, discard it as
an input. Restart from the original source PDF, reuse only reviewed translations
as translation memory, and rebuild with the gates above.
