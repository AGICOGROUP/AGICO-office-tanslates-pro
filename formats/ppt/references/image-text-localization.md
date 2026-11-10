# PowerPoint picture writeback

Follow [shared embedded-image handling](../../../references/image-translation.md).
Use the original media asset as the editing reference. For a paired deck,
the A slide keeps original media. The B slide uses an edited asset for
readable text in diagrams, charts, tables, control screens, certificates
and press scans. Replace text at the original positions. Preserve equipment,
connections, arrows, readings, table cells, units, identifiers, photos, seals
and signatures. Use an image editing tool. Do not replace an image with a
text summary, redraw its technical content, or cover it with slide text boxes.
Keep standalone real photographs unchanged, including lettering in the photo.

Read readable print in scans and reports in full. Check long Russian or other
target labels for clipping inside cropped images. Treat genuinely unreadable
or cropped source print as such. Compare the edited image with the original
before writeback and reject changes to equipment topology, numeric readings,
document dates, or other facts. Use one edit per unique image and language
mode and retry only a concrete defect.

Record decision `localized` with an absolute `replacement_path` and the supplied
ID/hash. `scripts/ppt_image_replacements.py` normalizes the approved picture to
the source dimensions and verifies the actual bytes. Preserve picture extent,
crop, rotation, group membership and unrelated relationships. When pairing,
the source and target copies must resolve to their own original and localized
bytes respectively, even if they began with the same asset.

Use `skip_target` with a specific retention reason for real photographs,
logo-only images and images already in the requested language mode.
Use `skip_unclear` only when source text cannot be read. Disclose residual
unreadable content or technical hosts outside image writeback.
