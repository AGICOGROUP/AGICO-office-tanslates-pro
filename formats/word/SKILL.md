---
name: office-translate-pro-word
description: Use when translating Word .doc or .docx documents, especially specifications, quotations and tables requiring editable text and preserved formatting.
---

# Word pipeline

Top-level routing is complete. Do not run the root Office router again.
This adapter does not depend on another Office translation skill. Follow the
[shared workflow](../../references/translation-decisions.md) from the skill root.

## Word-specific behavior

Preserve the document formatting; pagination may change. Keep styles, tables, sections,
headers/footers, editable objects and relationships. Translation-driven reflow is not damage.
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
