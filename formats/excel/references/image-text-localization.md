# Excel image-text localization

Review every worksheet and chart image at native resolution.

- If no clear translatable text exists, record `reviewed` with a reason and preserve the image bytes.
- Prefer an editable worksheet text box or chart-native label when it can replace or cover only the source label without obscuring cells, chart marks, process lines, or unrelated pixels.
- When raster editing is necessary, limit changes to approved text masks and preserve crop, anchor, aspect ratio, z-order, and all unrelated pixels.
- Preserve logos, equipment, arrows, symbols, topology, numbers, units, and flow direction.
- Render the complete sheet after localization; reject overlap, hidden labels, illegible type, or structural movement.

Never flatten the worksheet or chart into an image and never use a large opaque rectangle to hide source content.
