# In-image text translation — shared Office rule

Translate every readable image label into the user's requested language, using the current model
and relevant terminology. Follow the requested monolingual replacement or bilingual mode. If the
user explicitly permits either image mode, choose the clearest, fastest implementation.
Translations must appear inside the image at the corresponding label locations. A separate legend,
caption, appendix or image-review flag does not satisfy this requirement.

Use GPT's built-in image editing capability as the only method for translatable embedded image
text in Word, Excel and PowerPoint. Supply the original image as the edit
target, exact reviewed source/translation pairs, requested mode and explicit preservation constraints.
For WMF/EMF, render the original clearly before editing; preserve the source vector separately.
Do not use a screenshot of an entire Office page when a clean source image is available.
The model translates the text; image editing renders that wording. This is not permission to call
third-party translation services. Do not assume that generated non-text content is unchanged.
Do not switch to native text-box overlays, external legends, programmatic label drawing or
another image generator. Monolingual and bilingual are output modes of this same GPT method.
If the tool is unavailable, report the blocker and keep images pending rather than substituting
another method or claiming completion.

Request text-only changes and high-fidelity preservation of aspect ratio, layout, colors,
background, equipment details, icon counts, arrows, connections, linework, symbols, dimensions,
numbers, units, identifiers and logos. Avoid redesign, simplification and invented details.
Before the GPT edit, record the source image's pixel width, pixel height and exact aspect ratio in
the image decision. For WMF/EMF or another vector source, use the clean raster edit target's pixel
dimensions; if the raster target is derived from the Office placement, preserve that displayed
aspect ratio. State these dimensions and the ratio explicitly in the edit prompt.

The returned image must keep the same aspect ratio and must never crop or cut off any source edge,
label, symbol or drawing element. Its pixel width and height must either equal the recorded source
dimensions or both be greater by the same scale factor; neither output dimension may be smaller.
Do not stretch width and height independently. If GPT returns a larger canvas with a different
ratio, proportionally scale it and add blank canvas padding as needed—never crop—to restore the
recorded ratio while keeping both final dimensions at least as large as the source. Verify actual
pixel dimensions and the aspect ratio before accepting or inserting the replacement.
Inspect the returned image against the source, checking every readable label and non-text details.
The user accepted the GPT-edited CIM pyramid trial as sufficient quality. Judge output by readable,
accurate translations and preserved engineering meaning and overall appearance, not pixel identity.
Minor changes in stroke rendering, antialiasing, spacing or icon appearance are acceptable when they
do not alter equipment identity, counts, topology or technical values. Do not regenerate solely for
such cosmetic differences. Repair missing/wrong labels, unreadable text, changed values, missing
equipment or changed connections with a targeted correction. Do not claim pixel-exact reproduction.
Start one edit per unique image, continue document text work while it runs, inspect once and correct
only concrete defects. A successful generated image must be inserted back into the Office document
before claiming the file's image text is translated. Keep standalone trials distinct from delivery.

Check the actual saved image and its placement in the Office file. Preserve the source document,
anchors, crop, relationships and unrelated content. Image hashes may change only for approved
replacements. If the adapter lacks a replacement writer, implement and verify it before claiming
an integrated result; never bypass verification or substitute a legend. Reuse each reviewed edited
image across its occurrences within the current job. Logos/identifiers and already translated labels
may remain unchanged; flag genuinely illegible source text specifically, never guess it.
