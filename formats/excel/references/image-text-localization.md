# Excel image-text localization

Review each unique image byte sequence once, grouped by SHA-256. Reuse that decision for every
worksheet occurrence of the same image. Do not reopen or reclassify duplicate logos and repeated
equipment photographs.

- If the workbook contains no images, skip image review completely.
- If no clear translatable text exists, record `retain` and preserve the image bytes at every
  occurrence. Optional notes such as `no-source-text`, `logo-or-brand`, or `photograph` help explain
  the decision but their absence or wording must not block delivery.
- Use `localized` only after the unique PNG/JPEG has been edited and checked at native resolution.
  Set `replacement_path` to the absolute edited-image path in the worklist; the runner records its
  SHA-256. The compact worklist includes `source_image` for the extracted original. Replacement
  must retain the original format and pixel dimensions. `apply` replaces all matching image parts
  atomically after workbook export; `verify` checks their resulting hashes and occurrence counts.
- Use `manual-review` only when text presence or safe localization remains uncertain. This reason
  escalates the workbook to strict verification.
- This pipeline writes raster replacements; it does not create worksheet text boxes or translate
  native chart labels. Limit image edits to source-text masks and preserve all unrelated pixels.
  The image writer leaves package relationships, crop, anchors and z-order unchanged.
- Preserve logos, equipment, arrows, symbols, topology, numbers, units, and flow direction.
- Deep-review only images marked `localized` or `manual-review`. Reject
  overlap, hidden labels, illegible type, or structural movement.

Never flatten the worksheet or chart into an image and never use a large opaque rectangle to hide source content.
