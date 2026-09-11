# Excel image-text localization

Review each unique image byte sequence once, grouped by SHA-256, within the current job. Reuse its
decision and final replacement for every worksheet occurrence. A fresh test starts a new job and
does not reuse translations or generated images from earlier jobs.

- If the workbook contains no images, skip image review completely.
- If no clear translatable text exists, record `retain` and preserve the image bytes at every
  occurrence. Optional notes such as `no-source-text`, `logo-or-brand`, or `photograph` help explain
  the decision but their absence or wording must not block delivery.
- Use `localized` only after the unique PNG/JPEG has been edited and checked at native resolution.
  Keep the supplied image `id` and `sha256`, and set `replacement_path` to the absolute edited-image
  path in the worklist; the runner records the replacement SHA-256. An omitted redundant source
  hash can be resolved from a known current-job ID; an explicit conflicting hash is rejected.
  The compact worklist includes `source_image` for the extracted original. Replacement
  must retain the original format and pixel dimensions. `apply` replaces all matching image parts
  atomically after workbook export; `verify` checks their resulting hashes and occurrence counts.
- Use `manual-review` only when text presence or safe localization remains uncertain; inspect the
  affected labels rather than repeating review of all workbook images.
- This pipeline writes raster replacements; it does not create worksheet text boxes or translate
  native chart labels. Limit image edits to source-text masks and preserve all unrelated pixels.
  The image writer leaves package relationships, crop, anchors and z-order unchanged.
- Preserve logos, equipment, arrows, symbols, topology, numbers, units, and flow direction.
- Review localized images at native resolution, focusing on translated labels, technical values,
  arrows and table boundaries. Repair hidden or illegible text, meaning changes and structural
  movement. Minor cosmetic differences can accompany a usable delivery with a concise disclosure.

## Image calls and waiting

Use the active image-editing tool's supported workflow. Prepare the exact translated labels once,
reusing reviewed cell wording only when the screenshot has the same content and context. Specify
the current replacement/bilingual mode, all labels, source dimensions and preserved regions in the
first call. Treat each unique image as one edit target, not a request for several visual variants.

Keep one in-flight request per image and mode. When a call returns a running ID, retain it and
continue cell translation, terminology review or merging; wait on that same ID when the independent
work is done. Do not submit the same image again because a call is slow or a preview looks unchanged.
If the user changes the mode, stop the obsolete request when supported, keep completed cell work,
and edit from the original image for the new mode. A stopped client wait does not itself prove the
backend request was cancelled; do not repeatedly restart it.

Inspect the returned file before requesting a correction. For a real defect, describe its exact
region and exact replacement text, retaining the usable image. Normally use one targeted correction;
if it does not improve the defect, change the repair approach supported by the active tools instead
of repeating an equivalent whole-image prompt. Extra calls require a specific unresolved content
or readability defect, not font taste, white margins or a desire for another version. A minor,
unambiguous spelling imperfection can be disclosed with usable output; wrong units, missing labels
or ambiguous technical meaning still require repair.

Do not ask the generator to fix spelling and crop the whole canvas in the same correction. For
allowed deterministic finishing, crop only verified blank outer margins and resize once to the
source dimensions. Determine the complete content bounds first, including the bottom table row;
check the saved result once. Do not regenerate for pixel dimensions or blank margins alone, or
guess a crop that could remove labels. Preserve the best usable result when a later attempt regresses.

Never flatten the worksheet or chart into an image and never use a large opaque rectangle to hide source content.
