# PowerPoint picture writeback

Follow [shared embedded-image handling](../../../references/image-translation.md).
Inspect each unique picture once and use the current model for label wording. Select the editing
method allowed by the session, then review readable labels, technical values and non-text meaning.
Reuse accepted replacements only within this job. Partial bilingual text does not exempt other labels.

Record decision `localized` with an absolute `replacement_path` and the supplied ID/hash.
`scripts/ppt_image_replacements.py` normalizes the approved picture to the source's exact dimensions,
then exchanges only its referenced `ppt/media/*` bytes. Picture extent, crop, rotation, group membership,
relationships and unrelated parts remain intact; final verification checks the actual bytes.
Do not substitute external legends, text-box covers or a standalone generated picture for writeback.

Retain logo-only pictures and already-target-language labels with specific reasons. Report unreadable
labels or unsupported native hosts precisely. Charts, SmartArt and OLE previews are not raster
translation shortcuts; preserve their actual content and disclose unsupported translation scope.
