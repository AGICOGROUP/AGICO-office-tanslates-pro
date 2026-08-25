---
name: translate-powerpoint-professionally
description: Use when translating PowerPoint presentations (.ppt or .pptx), especially technical decks whose editable text, tables, charts, images, engineering graphics, terminology, and layout must be preserved with risk-driven Microsoft PowerPoint verification.
---

# Professional PowerPoint Translation

Run one resumable PowerPoint pipeline. Preserve the immutable source, write one separate output,
and use Microsoft PowerPoint as the final authority. Do not compose a task from individual COM,
OOXML, extraction, or render commands.

## Required inputs

Read these files completely before execution:

- `references/powerpoint-workflow.md`
- `references/pipeline-cli.md`
- `references/manifest-schema.md`

Do not load `../../references/水泥专业名词中英对照.md` in full. Use
`scripts/resolve_repo_glossary.py` to return only relevant exact and longest matches before model
translation.

Read `references/image-text-localization.md` only when inspection reports image groups. Read
`references/overlay-schema.md` only when a confirmed image label requires an editable overlay.
Read `references/typography-and-fit.md` only for shapes reported as overflow or collision risks.

## Single production pipeline

Use `scripts/ppt_pipeline.py` in this order:

1. `inspect` hashes the source, performs one OOXML inventory, groups identical images, classifies
   risk, and creates `job-state.json`.
2. `prepare` creates schema-v2 occurrences and safely reusable translation units, then pauses for
   translation.
3. Retrieve only relevant glossary entries with `scripts/resolve_repo_glossary.py`: exact phrase,
   then longest non-overlapping listed terms, before model wording. Fill every translation unit.
   Classify each unique image group as `retain`, `localize`, or `manual_review`; `pending` blocks
   apply.
4. Validate the manifest and run `apply` once. Fast `.pptx` uses OOXML; complex work uses one
   internal PowerPoint COM mutation session.
5. `verify` checks source hash, structure, occurrence coverage, translations, and protected tokens.
6. `render` opens the result in Microsoft PowerPoint once, exports one official PDF, renders all
   target slides as low-resolution thumbnails, and renders only risk slides at high resolution.
7. Review those renders, then run `deliver --visual-review-passed`. Rendering alone must never mark
   a presentation delivered.

Resume from the first incomplete stage. Never recreate task-specific builder or verification
scripts. Do not read historical translations unless the user explicitly asks to reuse them.

## Risk routes

- **Fast:** ordinary native text and regular tables that the OOXML scanner and writer fully cover.
- **Complex:** charts, SmartArt, notes, important grouped objects, confirmed image text, embedded
  objects, or another feature requiring the PowerPoint object model.
- **Strict:** user-requested page/slide fidelity, bids, contracts, certificates, legal/publication
  work, macros, repair warnings, invariant mismatches, or failed verification.

A text box alone is not a complex feature. An unexpected condition stops the current route and
escalates it; it never silently weakens a quality gate.

## Quality boundary

- Keep native text selectable and editable. Never flatten a slide or redraw a complete diagram.
- Preserve slide size, masters, layouts, themes, object IDs, geometry, z-order, animations,
  relationships, media, arrows, process lines, numbers, units, models, and standards unless a
  verified local repair requires a recorded change.
- Deduplicate translation tasks only when source text, target language, role, context signature,
  and protected tokens match. Every occurrence remains independently written and verified.
- Group images by SHA-256 and review each unique byte sequence once. Modify only confirmed source
  text masks and require zero changed pixels outside approved masks.
- Allow natural wrapping and reasonable local reflow. Repair only real clipping, overlap,
  overflow, missing text, object displacement, or hierarchy damage.
- Never install, locate, configure, or invoke LibreOffice automatically. Use it only after
  Microsoft PowerPoint is unavailable and the user explicitly authorizes that fallback.

Deliver only after the source remains unchanged, the output reopens in PowerPoint without repair,
all expected occurrences are translated, protected tokens match, required renders exist, and the
risk-appropriate visual review passes.
