---
name: translate-word-professionally
description: Use when translating uploaded Word documents (.doc or .docx), especially cement-industry tables, quotations, specifications, and technical documents whose styles, pagination, tables, images, editable text, and layout must be preserved.
---

# Professional Word Translation

Translate only human-language content while preserving the document's native Word structure and visual hierarchy.

**REQUIRED SUB-SKILLS:** Use `translate-documents-professionally` for professional translation coverage and `documents:documents` for DOCX inspection, editing, rendering, and visual verification.

## Start from the original

Hash and preserve the source. Work from a copy and create a separate translated output. Never overwrite the uploaded file.

Run the repository router first. For `.doc`, require its confirmed CFB signature, convert only an immutable working copy with Microsoft Word or a compatible converter, and verify the converted `.docx` against the source before translating. Stop if safe conversion is unavailable.

Read `../../references/水泥专业名词中英对照.md` before translation. Resolve an exact full phrase first, then the longest valid listed term; use professional contextual translation only when no listed term matches the intended sense.

## Required workflow

1. Inventory page size, sections, margins, headers, footers, styles, paragraphs, runs, tables, fields, drawings, text boxes, hyperlinks, notes, comments, relationships, media, and source-language text.
2. Render every page before editing to establish a visual and pagination baseline.
3. Extract text in stable document order without deduplicating repeated strings. Include headers, footers, tables, shapes, charts, comments, notes, and clear image text.
4. Protect numbers, units, formulas, model codes, standards, URLs, identifiers, field codes, bookmarks, whitespace, line breaks, and other protected tokens.
5. Translate native text in place so it remains editable and selectable. Keep paragraph, run, table, style, relationship, media, and drawing structure unchanged unless a documented local repair is required.
6. Review every embedded image. Translate clear labels without changing unrelated pixels or flattening native document content; record unsafe or uncertain regions for manual review.
7. Save one new `.docx`, reopen it, and compare structure, protected tokens, page count, section breaks, table geometry, styles, relationships, media, and unexpected Chinese against the baseline.
8. Use the `documents:documents` render workflow to render every page of the final DOCX. Reject clipping, overlap, missing text, pagination drift, table damage, image changes, repair warnings, or unapproved layout changes.

## Delivery gate

Deliver only when the source hash is unchanged, the output opens normally, every expected native string remains editable, all clear image text has been reviewed, glossary terms are consistent, protected tokens match, and complete rendered comparison passes.
