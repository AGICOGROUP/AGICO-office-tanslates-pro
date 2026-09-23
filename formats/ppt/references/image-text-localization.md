# PowerPoint image-text translation

Follow [the shared in-image translation rule](../../../references/image-translation.md).
Two methods are accepted and selected per image by that rule: generative `image_edit` for renders,
photos and sketches, and deterministic erase + refill (`scripts/inimage_erase_refill.py`) for technical
line drawings whose linework must survive unchanged. Native text-box overlays and external legends must
not be used to translate image text, whether the requested output is monolingual or bilingual.

Inspect each unique image once. Translate every readable label with the current model and matched
terminology. Method A: send the original image, exact translations and preservation constraints to
`image_edit`. Method B: render from the reviewed label table and require the shared rule's fidelity
numbers before accepting. Review the actual result using the shared accepted quality criteria; reuse it
for matching occurrences within the job. Insert the finished image at its original position, preserving
size, crop, rotation, group membership and surrounding content. Verify the saved image and slide
appearance.

Approve an edit with decision `localized` and an absolute `replacement_path`. The replacement writer
`scripts/ppt_image_replacements.py` fits the approved edit to the source image's exact pixel
dimensions, then exchanges only the referenced `ppt/media/*` bytes; the picture shape, its extent,
crop, rotation, relationships and every unrelated part stay byte-for-byte identical. `verify`
tolerates that one declared part change and still rejects any other changed part. Never substitute a
declared replacement for one that was not actually written, and do not mark an unmodified image as
translated.
Retain only logos/identifiers, already translated labels or genuinely unreadable source content with
a specific reason. Partial existing translations do not justify skipping other readable labels.
Editable charts, SmartArt and embedded objects are native content; their previews must not substitute
for translation inside those objects.
