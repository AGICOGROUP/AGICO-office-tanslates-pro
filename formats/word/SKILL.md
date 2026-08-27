---
name: translate-word-professionally
description: Use when translating uploaded Word documents (.doc or .docx), especially cement-industry tables, quotations, specifications, and technical documents whose styles, pagination, tables, images, editable text, and layout must be preserved.
---

# Professional Word Translation

Translate only human-language content while preserving the document's native Word structure and visual hierarchy.

Top-level routing is complete when this adapter starts. Do not run the root Office router again,
read another format adapter, or consider another format workflow.

This adapter contains the complete professional translation, terminology, structure-preservation,
and quality-control contract; it does not depend on another Office translation skill.

## Start from the original

Hash and preserve the source. Work from a copy and create a separate translated output. Never overwrite the uploaded file.

Use `scripts/word_pipeline.py` for the complete workflow. For `.doc`, its conversion stage opens visible Microsoft Word and immediately saves an immutable working `.docx`; do not inventory, repaginate, or run statistics before conversion.

Read `../../references/水泥专业名词中英对照.md` before translation. Resolve an exact full phrase first, then the longest valid listed term; use professional contextual translation only when no listed term matches the intended sense.

## Required workflow

1. Run `prepare` to convert when needed, inventory the working DOCX, and create `translation-manifest.json`.
2. Fill every manifest target in stable source order after applying the glossary and protected-token rules.
3. Run `apply`; the program uses `lxml`, preserves ZIP parts and namespace mappings, keeps whitespace-only runs from carrying translated words, preserves visible boundary spaces, and removes CJK-only character compression from Latin-script translations without rebuilding OOXML with the standard XML library.
4. Review embedded image text and record any unsafe region for manual review.
5. Run `validate` once. Its static checks for source hash, translated strings, structure, media, and protected tokens are the required delivery gate.
6. Use `validate --word-native` only when a Word-native opening or pagination diagnostic is specifically useful. This check is optional and non-blocking; failure or timeout is recorded as a warning and never prevents delivery.

## Delivery gate

Deliver only when the source hash is unchanged, every expected native string remains editable,
clear image text has been reviewed, glossary terms are consistent, protected tokens match, and
the static validation passes, including its boundary-space and unsafe character-compression checks. The optional Word-native check and its pagination result are
diagnostic only and never a delivery gate. Do not require PDF export, PDF conversion, or a PDF file
as delivery evidence. Complete the final check without an external PDF conversion or rendering gate.
