---
name: translate-word-professionally
description: Use when translating uploaded Word documents (.doc or .docx), especially cement-industry tables, quotations, specifications, and technical documents whose styles, pagination, tables, images, editable text, and layout must be preserved.
---

# Professional Word Translation

Translate only human-language content while preserving the document's native Word structure and visual hierarchy.

Top-level routing is complete when this adapter starts. Do not run the root Office router again,
read another format adapter, or consider another format workflow.

This adapter contains the complete professional translation, terminology, structure-preservation,
and quality-control contract; it does not depend on another Office translation skill. Use Microsoft
Word as the final authority for pagination, opening, and visual inspection.

## Start from the original

Hash and preserve the source. Work from a copy and create a separate translated output. Never overwrite the uploaded file.

Use `scripts/word_pipeline.py` for the complete workflow. For `.doc`, its conversion stage opens visible Microsoft Word and immediately saves an immutable working `.docx`; do not inventory, repaginate, or run statistics before conversion.

Read `../../references/水泥专业名词中英对照.md` before translation. Resolve an exact full phrase first, then the longest valid listed term; use professional contextual translation only when no listed term matches the intended sense.

## Required workflow

1. Run `prepare` to convert when needed, inventory the working DOCX, and create `translation-manifest.json`.
2. Fill every manifest target in stable source order after applying the glossary and protected-token rules.
3. Run `apply`; the program uses `lxml`, preserves ZIP parts and namespace mappings, and writes translated text without rebuilding OOXML with the standard XML library.
4. Review embedded image text and record any unsafe region for manual review.
5. Run `validate` once. It reopens the candidate read-only in Word, repaginates once, records `Content.Information(4)` as informational content pages, and checks structure, media, tokens, and repair-free opening.
6. Deliver only after that one Word-native validation passes. Do not tune fonts or repeat pagination checks merely to make page totals equal.

## Delivery gate

Deliver only when the source hash is unchanged, Microsoft Word reopens the output without repair,
every expected native string remains editable, clear image text has been reviewed, glossary terms
are consistent, protected tokens match, and the one Word-native validation passes. Content pages
are diagnostic information, not an equality gate. Do not require PDF export, PDF conversion, or a
PDF file as delivery evidence.
The entire final check stays in Word without an external PDF conversion or rendering gate.
