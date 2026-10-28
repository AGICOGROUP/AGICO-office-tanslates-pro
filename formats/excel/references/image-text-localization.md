# Excel picture writeback

Follow [shared embedded-image handling](../../../references/image-translation.md).
No images means no image work. Classify unique SHA-256 groups once; logo-only pictures retain
their exact bytes. Localize readable labels according to the user's requested mode.

Use the current image tool's actual schema, not a historical interface. Keep one running request
per unique image/mode and translate cells while it runs. Accept readable, accurate edits with
preserved technical meaning; do not generate another version for font taste. Pixel identity outside
text masks applies only to explicitly permitted deterministic erase/refill, not to generative editing.

For a finished edit, preserve `id`/`sha256` and set `status: "localized"` plus an absolute
`replacement_path` in the batch/worklist image decision. An explicitly conflicting hash is rejected.
The source is at `source_image`. Preserve aspect ratio, equal-or-higher resolution and all content;
normalize harmless canvas drift once rather than regenerating or cropping labels.

The writer replaces matching `xl/media/*` parts and verifies hashes and occurrence counts.
Relationships, anchors, crop and z-order stay unchanged. Inspect final labels in their saved placement
when there is a concrete cropping/readability risk. A `localized` status without matching embedded
replacement bytes is not completion.

These are raster-picture replacements, not a native chart-label translator. Do not flatten a
worksheet/chart or hide source content behind opaque worksheet objects. Report genuine unsupported
native-object labels separately. Legacy `manual-review` is pending work: inspect only that affected
image, not all already-accepted images.
