---
name: translate-scan-pdf-professionally
description: Use when translating scan-only or image-only PDFs whose text cannot be selected, especially manuals, catalogs, tables, screenshots, process diagrams, engineering drawings, logos, headers, and footers where page appearance and non-text graphics must remain unchanged.
---

# Professional Scan PDF Translation

## Overview

Translate rasterized PDFs by changing only source-language glyph regions, then add embedded vector English text. Preserve page geometry, colors, photographs, diagram lines, table rules, icons, logos, and all non-text pixels.

## Route Gate

Run `scripts/classify_pdf.py`. Use this skill only when it reports `scan-only`.
If it reports `mixed-or-native`, use the mixed/native PDF route. If it reports
`normalize-rotation-first`, normalize page rotation without rasterizing or
changing visible pixels, then classify again.

## Required Workflow

Read these files before acting:

- `references/workflow.md` for the complete execution order and image-text handling rules.
- `references/manifest-schema.md` before creating or editing the translation manifest.
- `references/quality-gates.md` before review and delivery.
- `references/cement-terminology.md` only through
  `scripts/glossary_lookup.py` when cement-industry terms or sentences occur.

Use an isolated job directory named with the source SHA-256 prefix. Never modify the source PDF.

1. Classify the source and fingerprint it.
2. Render every required page at 400 DPI and run dual-scale OCR with
   `scripts/extract_scan.py`; batching page ranges is allowed.
3. Create a manifest with `scripts/make_manifest_template.py`.
4. Inventory every OCR line. Group lines into semantic blocks. For each cement
   block or batch, run `python scripts/glossary_lookup.py scan "<Chinese source>"`.
   Use every returned table translation before model wording; use the model only
   for unmatched terms or sentences. The lookup uses longest matches and the
   final occurrence of duplicate entries because later table sections contain
   revisions. Apply matches consistently to body text and image labels. Every
   source-line ID must be assigned exactly once as `translated` or
   `preserve_confirm`.
5. For each translated block, approve a tight `clean_box` around glyph pixels only. Preserve drawing lines crossing or touching text; explicitly reconstruct only verified line segments through `vector_lines`. Keep icons in the raster base whenever possible. If cleanup must cover an icon, use a `rich_lines` `source_crop` run to copy the exact original pixels back; never substitute a similar icon.
6. Build with `scripts/build_scan.py`. English is embedded vector text and must be selectable/copyable.
7. Render and inspect every output page at full-page and zoomed resolution. Complete the visual-review evidence.
8. Run `scripts/verify_scan.py`. Deliver only when it exits successfully and its report says `passed: true`.

## Shared Layout Rules

- Mark a diagram `bilingual_complete` and preserve it unchanged only when every
  clear Chinese label has a semantic English counterpart. Record the source
  region hash, clear-Chinese count, matched-pair count, and zero unmatched
  labels. Partial bilingual diagrams translate only unmatched Chinese labels.
- Within one page, `major_title`, `minor_title`, and `body` each use one font,
  size, and weight derived from the source. Plan the whole group before drawing.
  If one body block cannot fit, reduce every body block on that page to the same
  fitting size; do not shrink only the dense paragraph.
- Preserve image placement first. Only after a recorded text-fit failure may a
  text-free large image shift or shrink proportionally into verified whitespace.
  A shift reuses exact pixels; a shrink may only resample the original crop
  proportionally. Reject any collision, page escape, crop, stretch, redraw, or
  change outside the approved old/new image regions.

## Non-Negotiable Rules

- Do not use broad white rectangles, blur, generative redraw, global inpainting, or whole-page image regeneration.
- Do not cover process lines, borders, leaders, arrows, symbols, photos, or logo artwork.
- Treat icons as immutable artwork. Preserve them in place or reuse exact source pixels; never redraw them, replace them with text, or choose a similar glyph/icon from a library.
- Preserve mixed source-language emphasis and color changes with `rich_lines` text runs when they carry meaning or navigation cues.
- A translated label may be shorter, smaller, or reflowed, but never clipped, omitted, or placed over structure.
- Clear Chinese inside images, logos, UI screenshots, headers, and footers must
  be translated unless it belongs to a strictly proven complete bilingual
  region. Illegible text may be preserved only with an explicit review record.
- OCR confidence never replaces visual review. OCR false positives require exact bounding-box evidence and a documented reason.
- Zero unreviewed pages, zero unreviewed images, zero icon substitutions, zero mixed-color failures, zero overlap/clipping findings, zero unexplained CJK residuals, and zero pixel changes outside approved cleanup regions.
- Approved CJK inside a hash-bound `bilingual_complete` region is not an
  untranslated residual; clear Chinese without a paired English label remains
  a delivery failure.
- Cement glossary hits must use the bundled table's selected English lexical
  form. Only capitalization or grammatical number may change; a model synonym
  is a delivery failure when a table match exists.

## Quick Commands

Use the Python interpreter available in the current runtime. Install `scripts/requirements.txt` only when dependencies are missing. Run each script with `--help`; path-safe commands and manifest examples are in `references/workflow.md`.

## Stop Conditions

Stop and redesign the affected page when cleanup blurs or removes nearby structure, the exact source icon cannot be recovered, a translation cannot fit above the minimum size, a line cannot be reconstructed from reliable anchors, or QA cannot distinguish a residual glyph from artwork. Record irrecoverable icons as `preserve_confirm`; do not invent substitutes or lower the gate to force delivery.
