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
2. Read `translation-worklist.json` (a compact batch index) and its listed batch files in stable source order. Read the full shared glossary as before. Return only the batch `job_id` and `translations` with ID/translation decisions, then run `merge --job-dir <job> --responses <responses.json>`. Do not rewrite the complete manifest or generate translation/merge Python scripts. Fill every manifest target through this merge after applying the glossary and protected-token rules. See `references/translation-work.md` for the response schema, resume and local corrections.
3. Run `apply`; the program uses `lxml`, preserves ZIP parts and namespace mappings, keeps whitespace-only runs from carrying translated words, preserves visible boundary spaces, and removes CJK-only character compression from Latin-script translations without rebuilding OOXML with the standard XML library. `apply` also adapts fixed CJK layout devices for non-CJK targets: vertical or portrait-locked text boxes are reflowed horizontally with landscape extents, `第%1章`-style chapter counters in `numbering.xml` become `Chapter %1`, and exact line spacing tuned for CJK glyphs is relaxed to at-least for paragraphs that now hold Latin text (skipped when the target language is CJK, where those devices are the intended design).
4. Review every unique embedded image. Translate clear raster labels inside the image when the requested output is bilingual, preserving the source labels, image dimensions, format, crop, and all pixels outside approved text-overlay regions. Use `localize-images` with a reviewed JSON plan and follow `references/image-text-localization.md`. Record only unclear or unsafe regions for manual review.
5. Run `validate` once. Its static checks for source hash, translated strings, structure, media files, live media references, and protected tokens are the required delivery gate.
6. Use `validate --word-native` only when a Word-native opening or pagination diagnostic is specifically useful. This check is optional and non-blocking; failure or timeout is recorded as a warning and never prevents delivery.
7. Documents converted from PDF often anchor every paragraph in floating text boxes sized for the CJK source; for non-CJK targets `apply` unwraps those boxes into normal flowing paragraphs at the same position, which removes the text-over-table/artwork overlap class. Decorative boxes (callouts drawn over images) should still be reviewed manually, and remaining fixed-size frames may need a desktop-publishing pass.

## Delivery gate

Deliver only when the source hash is unchanged, every expected native string remains editable,
clear image text has been localized or explicitly retained, every expected media file remains referenced by document content, glossary terms are consistent, protected tokens match, and
the static validation passes, including its boundary-space and unsafe character-compression checks. The optional Word-native check and its pagination result are
diagnostic only and never a delivery gate. Do not require PDF export, PDF conversion, or a PDF file
as delivery evidence. Complete the final check without an external PDF conversion or rendering gate.
