# PowerPoint image translation

This path is only for static graphics whose text is not selectable or copyable. An embedded object,
chart, SmartArt item, or other selectable or copyable content is not an image. Its preview image
must never be translated as a substitute for the editable object; route the object to its native
editable-content handler and stop if that handler is unavailable.

Use one single-pass screen for each unique image. Do not retry OCR or enlarge unclear text for repeated recognition.
Apply exactly one decision:

- `skip_target`: all readable source labels already have an equivalent target-language translation.
  Partial target-language text does not skip the whole image; overlay every uncovered readable label.
- `skip_unclear`: no source label can be read confidently at normal useful resolution. Small but readable
  text is not unclear and must be translated. If some labels are readable, use `overlay` for those labels.
- `overlay`: at least one source label is readable and still lacks the target language. Preserve the original image and add each
  translation as a transparent, editable PowerPoint text box immediately below its source label
  using `bilingual_below`.

Screen all readable source labels in actual static diagrams, flowcharts, and screenshots.

For `overlay`, preserve all original pixels, crop, geometry, arrows, lines, equipment, numbers,
units, models, symbols, and flow direction. Never erase, cover, patch, regenerate, redraw, or
replace image content.
