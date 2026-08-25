---
name: translate-word-professionally
description: Use when translating Word .doc or .docx files quickly and professionally while keeping editable text, tables, visual hierarchy, and protected technical content; automatically escalates complex or strict-layout documents.
---

# Fast Professional Word Translation

Produce an accurate, editable translation with no major visual change. Exact pagination, run geometry, and pixel-level fidelity are not default requirements.

Top-level routing is complete when this adapter starts. Do not run the root Office router again, read another format adapter, or apply a cross-format gate. This adapter owns its final validation and delivery.

**REQUIRED SUPPORTING SKILL:** Use `documents:documents` for DOCX inspection and editing, but do not use its LibreOffice renderer. This adapter contains the complete professional translation, terminology, structure-preservation, and quality-control contract; it does not depend on another Office translation skill.

For Word files, this adapter's risk-based render scope and layout tolerance supersede broader root-skill wording about complete rendering or exact structure preservation.

Use native DOCX/OOXML tooling for extraction, writing, and core validation. `documents:documents` may assist with DOCX structure, but its LibreOffice renderer must not be used. On Windows, Microsoft Word is the authoritative engine for `.doc` conversion and optional visual QA.

## Start

Run the repository router. Hash and preserve the source, work on a copy, and create one translated `.docx`. Never overwrite the uploaded file.

For `.doc`, confirm the CFB signature and convert the working copy with Microsoft Word COM. Stop if Word is unavailable; do not silently substitute LibreOffice.

Run `python scripts/analyze_docx.py <working.docx> --output <preflight.json>` from this skill directory. Use its occurrence list, unique-text cache, protected-token inventory, media count, and `fast`/`complex` recommendation instead of repeating separate discovery passes.

Read `../../references/水泥专业名词中英对照.md`. Apply exact full-phrase matches, then the longest valid term, then professional contextual translation.

## Classify once

Use the initial extraction to choose one path. Do not ask the user unless the file is ambiguous or their requirement conflicts with the detected risk.

- **Fast path — default:** ordinary paragraphs, headings, headers/footers, and conventional tables; no tracked changes, text-bearing floating objects, complex fields, or raster text requiring translation.
- **Complex path:** tracked changes, comments, footnotes/endnotes, TOC or other important fields, text boxes, charts, multi-column sections, floating objects, nested/irregular tables, or images that contain relevant text.
- **Strict path:** use only when the user explicitly requests exact pagination/format matching, or the document is a legal, tender, certificate, or publication artifact whose page geometry is materially significant.

Complexity escalates only the checks needed by the detected feature. Do not apply strict-layout work to an otherwise ordinary document.

## Fast path

Run a streaming pipeline:

1. **One extraction:** collect editable source-language text in document order from paragraphs, tables, headers, footers, footnotes/endnotes, comments, and native text objects that exist. In the same pass, record styles, table geometry, protected tokens, special features, and image metadata.
2. Build a per-occurrence manifest, but deduplicate identical source strings for translation. Batch related segments; do not translate one run at a time. Reuse approved translations for consistency.
3. Protect numbers, units, formulas, model codes, standards, URLs, identifiers, field codes, bookmarks, whitespace, and line breaks. Preserve protected tokens exactly.
4. **One write pass:** write translated strings back to their owning paragraph, cell, header/footer, or native text object. Keep hyperlinks, fields, lists, tables, styles, relationships, and media functional. Preserve the dominant local formatting; do not reconstruct harmless run-level fragmentation.
5. Reopen the output once and run the mandatory quality gates below.
6. Ordinary fast-path documents do not require PDF export. Deliver the validated DOCX directly after the mandatory quality gates pass.

Allow natural line wrapping, small row-height changes, and reasonable pagination drift. Pagination change alone is not a defect. Repair only missing text, clipping, overlap, broken tables, displaced critical objects, or clearly degraded hierarchy.

## Complex and strict additions

- Run PDF-based visual QA only for the complex path, strict path, or when the user explicitly requests visual or PDF-based QA. Export with Microsoft Word using `powershell -NoProfile -ExecutionPolicy Bypass -File ../../scripts/office_com_pdf.ps1 ...`, then rasterize the PDF.
- **Complex path:** render a source baseline for affected pages, process the detected special objects, and compare their structure after writing. Render every page only on the complex or strict path.
- **Strict path:** render every source and output page; compare pagination, sections, object positions, table geometry, relationships, and media. Apply bounded layout repairs until the requested fidelity is met.
- PDF export failure must not block saving or returning a DOCX that has passed the mandatory core gates. Report the missing visual QA explicitly. If strict visual fidelity was required, also report that the strict visual gate remains incomplete.
- Native text in shapes/charts remains editable. Review raster images only when triage indicates relevant text or the user requests image-text translation. Do not OCR images without detected text; skip logos, decorative images, photos, and diagrams with no relevant language.
- If raster text cannot be translated safely, preserve the image and report its location instead of blocking unrelated native-text translation, unless the user required complete image localization.

## Mandatory quality gates

Every path must verify:

- the source hash is unchanged and the output opens normally without repair warnings;
- translation coverage is complete for expected editable source-language occurrences;
- glossary consistency for repeated technical terms;
- protected-token equality for numbers, units, models, standards, identifiers, URLs, and fields;
- translated native content remains editable and selectable;
- paragraph/list order, section count, and table integrity are intact;
- no unexpected source-language residue remains in translated native text;

Do not fail the fast path for reasonable pagination drift, harmless font fallback, minor spacing changes, or non-text image differences.

Never install, locate, configure, or invoke LibreOffice/soffice automatically. Use it only after Microsoft Word is unavailable and the user explicitly authorizes that fallback.

## Delivery

Deliver one translated `.docx` and a concise summary stating the selected path, translation coverage, protected-token result, table result, any optional render scope, and any intentionally preserved image text. Do not return to the root router after delivery.
