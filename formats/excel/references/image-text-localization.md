# Excel image-text localization

Review each unique image byte sequence once, grouped by SHA-256. Reuse that decision for every
worksheet occurrence of the same image. Do not reopen or reclassify duplicate logos and repeated
equipment photographs.

- If the workbook contains no images, skip image review completely.
- If no clear translatable text exists, record `retain` with reason code `no-source-text`,
  `logo-or-brand`, or `photograph`, and preserve the image bytes at every occurrence.
- Use `localized` only after the unique image has been edited and checked at native resolution.
- Use `manual-review` only when text presence or safe localization remains uncertain. This reason
  escalates the workbook to strict verification.
- Prefer an editable worksheet text box or chart-native label when it can replace or cover only the source label without obscuring cells, chart marks, process lines, or unrelated pixels.
- When raster editing is necessary, limit changes to approved text masks and preserve crop, anchor, aspect ratio, z-order, and all unrelated pixels.
- Preserve logos, equipment, arrows, symbols, topology, numbers, units, and flow direction.
- Deep-review and render only sheets containing `localized` or `manual-review` groups. Reject
  overlap, hidden labels, illegible type, or structural movement.

Never flatten the worksheet or chart into an image and never use a large opaque rectangle to hide source content.
