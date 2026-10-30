---
name: office-translate-pro-word
description: Use when translating Word .doc or .docx documents, especially specifications, quotations and tables requiring editable text and preserved formatting.
---

# Word pipeline

Top-level routing is complete. Do not run the root Office router again.
This adapter does not depend on another Office translation skill. Follow the
[shared workflow](../../references/translation-decisions.md) from the skill root.

## Word-specific behavior

Preserve the document formatting; pagination may change. When translated text expands (for example,
Chinese into English), allow natural line wrapping, paragraph growth and flow onto following pages.
Page breaks, the total number of pages and the pages on which content appears may therefore change;
these translation-driven changes alone are not formatting damage or a delivery failure.

Keep the original formatting properties: styles, font formatting and sizes, alignment, indentation,
line/paragraph spacing, numbering, table structure/column widths/borders, paper size/orientation,
margins, sections, headers/footers, and image sizes/anchors. Preserve explicit page/section breaks,
editable objects and relationships; allow Word's automatic pagination to reflow around them.
Retain page-number and contents fields, their numbering rules and styling; their displayed values
may update to follow the new pagination. Do not replace those fields with fixed original numbers.
Do not reduce fonts or spacing, change margins/table widths, move objects or shorten away meaning
to force the translation back into the original pagination. Actual clipping, overlap or missing
content still needs a targeted resolution; additional pages alone do not.
Never overwrite the original. Microsoft Word converts legacy `.doc` once to a working `.docx`.

Read complete paragraphs and their neighboring/style context, not separate runs. Keep protected tokens,
real tabs and explicit line-break boundaries, including empty groups around consecutive breaks.
The writer preserves native formatting and boundary spaces; avoid inherited negative/compressed
Latin spacing. Use the matched `../../references/水泥专业名词中英对照.md`, not mechanical word replacement.

If there is embedded image text, follow [image handling](../../references/image-translation.md).
Retain logo-only pictures. Localized pictures must be written back, not delivered as separate
legends. Preserve their display size, aspect ratio and anchors. Supported main-story inline/raster
replacements are verified against actual embedded media; report an unsupported image host specifically.

## Delivery

`office_pipeline.py finalize` checks text locations, technical values, structure and media, then
publishes the verified candidate. Deliver without an external PDF conversion or rendering gate.
Native Word checking is optional and non-blocking when unavailable; use it for a concrete opening or
layout concern, not as another routine round. Actual corruption/content loss still needs repair.
Legacy `scripts/word_pipeline.py` commands remain for targeted diagnosis, not a second ordinary flow.
