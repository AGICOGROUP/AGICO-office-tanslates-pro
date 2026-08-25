---
name: translate-word-professionally
description: Use when translating uploaded Word documents (.doc or .docx), especially cement-industry tables, quotations, specifications, and technical documents whose styles, pagination, tables, images, editable text, and layout must be preserved.
---

# Professional Word Translation

Translate only human-language content while preserving the document's native Word structure and visual hierarchy.

Top-level routing is complete when this adapter starts. Do not run the root Office router again,
read another format adapter, or consider Excel, PowerPoint, PDF, or image workflows.

This adapter contains the complete professional translation, terminology, structure-preservation,
and quality-control contract; it does not depend on another Office translation skill. Use Microsoft
Word as the final authority for pagination, opening, and visual inspection.

## Start from the original

Hash and preserve the source. Work from a copy and create a separate translated output. Never overwrite the uploaded file.

For `.doc`, use the confirmed CFB result supplied by the top-level route, convert only an immutable working copy with Microsoft Word or a compatible converter, and verify the converted `.docx` against the source before translating. Stop if safe conversion is unavailable.

Read `../../references/水泥专业名词中英对照.md` before translation. Resolve an exact full phrase first, then the longest valid listed term; use professional contextual translation only when no listed term matches the intended sense.

## Required workflow

1. Inventory page size, sections, margins, headers, footers, styles, paragraphs, runs, tables, fields, drawings, text boxes, hyperlinks, notes, comments, relationships, media, and source-language text.
2. Open the source in Microsoft Word, repaginate it, and record the page, section, table, drawing,
   and text-flow baseline. Inspect each page in Word's Print Layout view.
3. Extract text in stable document order without deduplicating repeated strings. Include headers, footers, tables, shapes, charts, comments, notes, and clear image text.
4. Protect numbers, units, formulas, model codes, standards, URLs, identifiers, field codes, bookmarks, whitespace, line breaks, and other protected tokens.
5. Translate native text in place so it remains editable and selectable. Keep paragraph, run, table, style, relationship, media, and drawing structure unchanged unless a documented local repair is required.
6. Review every embedded image. Translate clear labels without changing unrelated pixels or flattening native document content; record unsafe or uncertain regions for manual review.
7. Save one new `.docx`, then reopen it read-only in Microsoft Word with alerts suppressed and
   repaginate it. Compare structure, protected tokens, page count, section breaks, table geometry,
   styles, relationships, media, and unexpected Chinese against the baseline.
8. Inspect every final page in Word's Print Layout view. Reject clipping, overlap, missing text,
   pagination drift, table damage, image changes, repair warnings, or unapproved layout changes.
   Complete this check inside the Word workflow without an external PDF conversion or rendering gate.

## Delivery gate

Deliver only when the source hash is unchanged, Microsoft Word reopens and repaginates the output
without repair, every expected native string remains editable, all clear image text has been
reviewed, glossary terms are consistent, protected tokens match, and the Word-native page review
passes. Do not require PDF export, PDF conversion, or a PDF file as delivery evidence.
