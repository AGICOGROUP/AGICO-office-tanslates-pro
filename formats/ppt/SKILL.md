---
name: translate-powerpoint-professionally
description: Use when translating PowerPoint presentations (.ppt or .pptx), especially technical decks with tables, charts, screenshots, flowcharts, or engineering drawings, where layout, colors, object structure, professional terminology, and editable/selectable text must be preserved.
---

# Professional PowerPoint Translation

Translate with Codex/GPT and mutate only the original presentation's text-bearing objects. Keep native text native. Preserve slide design and engineering meaning.

## Start from the original

Hash and preserve the source. Create every run from that immutable original; use earlier translations only as review evidence. Inventory slide size, theme, masters, layouts, object IDs, geometry, tables, charts, notes, media, crops, fonts, fills, lines, and source-language text before applying changes.

Read these references before acting:

- `references/powerpoint-workflow.md`
- `../../references/水泥专业名词中英对照.md` for the repository-wide cement terminology source
- `references/typography-and-fit.md` for same-slide typography and conditional layout changes
- `references/manifest-schema.md`
- `references/image-text-localization.md`
- `references/overlay-schema.md` when an image needs editable labels

## Required workflow

1. Extract native text in stable slide/shape/paragraph order without deduplicating repeated strings.
2. Run `scripts/resolve_repo_glossary.py` and resolve cement terminology against `../../references/水泥专业名词中英对照.md` before model preference: use an exact full phrase first, then the longest listed term; use contextual model translation only when no listed translation matches the intended sense. Preserve every matching listed English translation unless a genuine contextual conflict is recorded for review. Fail closed when the repository glossary is unavailable.
3. Build a task glossary for remaining equipment, process terms, units, model numbers, standards, and recurring headings, then translate with slide and neighboring-object context.
4. Validate the manifest with `scripts/validate_manifest.py`.
5. For `.ppt`, use `scripts/ppt_com.ps1`; for `.pptx`, prefer `scripts/pptx_ooxml.py` when ordered text-node replacement is sufficient, otherwise use PowerPoint COM.
6. Translate every clear label inside embedded images using `references/image-text-localization.md`.
7. Reopen and render every slide. Compare source and target for structure, editability, coverage, clipping, overlap, and image fidelity.

## Non-negotiable fidelity rules

- Preserve slide size, masters, layouts, themes, colors, geometry, z-order, animation, media, relationships, tables, charts, and object IDs unless a reviewed repair explicitly requires a local addition.
- Keep originally editable text selectable, copyable, and editable.
- Never flatten a slide or native text into an image.
- Never regenerate or redraw a complete engineering diagram.
- Modify raster images only inside approved source-text masks; require zero changed pixels outside those masks.
- Preserve arrows, leader lines, borders, process lines, equipment, symbols, topology, numbers, units, and flow direction.
- Never use a large opaque rectangle to hide source text.
- Record uncertain or unsafe image regions for manual review instead of guessing.

## Typography and text fit

Apply `references/typography-and-fit.md` on every slide. Keep peer section headings at one font size and bold; keep peer body text at one font size. Do not alter layout when text fits. Only after verified overflow or collision may the workflow adjust text boxes or proportionally move/scale images within that slide.

## Delivery gate

Deliver only when the source is untouched, the output opens without repair warnings, all expected native text remains editable, all clear source-language text is translated, terminology follows the supplied table, peer typography is consistent, protected tokens match, and rendered visual review finds no unapproved structural change.
