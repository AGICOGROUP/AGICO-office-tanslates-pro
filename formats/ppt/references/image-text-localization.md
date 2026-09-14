# PowerPoint image-text translation

Follow [the shared GPT image-editing workflow](../../../references/image-translation.md).
GPT image editing is the only method. Native text-box overlays and external legends must not be
used to translate image text, whether the requested output is monolingual or bilingual.

Inspect each unique image once. Translate every readable label with the current model and matched
terminology. Send the original image, exact translations and preservation constraints to GPT image
editing. Review the actual result using the shared accepted quality criteria; reuse it for matching
occurrences within the job. Insert the generated image at its original position, preserving size,
crop, rotation, group membership and surrounding content. Verify the saved image and slide appearance.

The existing low-level overlay writer is not a replacement writer. Implement and verify replacement
support before claiming integrated delivery. Do not mark an unmodified image as translated.
Retain only logos/identifiers, already translated labels or genuinely unreadable source content with
a specific reason. Partial existing translations do not justify skipping other readable labels.
Editable charts, SmartArt and embedded objects are native content; their previews must not substitute
for translation inside those objects.
