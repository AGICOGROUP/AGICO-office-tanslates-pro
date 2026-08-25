# PowerPoint balanced workflow

## Processing boundary

`scripts/ppt_pipeline.py` is the only production entry. It owns state, stage order, artifact paths,
risk escalation, and delivery. `pptx_ooxml.py`, `ppt_com.ps1`, and `office_com_pdf.ps1` are internal
adapters and must not be assembled into a second workflow.

## Inspect once

The inspector reads the OOXML package once and records every native text occurrence, its stable
slide/shape/paragraph identity, role, context signature, protected tokens, package features, and
media relationship. Identical media bytes share one SHA-256 image group while retaining all
locations.

Plain text boxes and regular tables remain fast when the scanner covers their text nodes. Charts,
SmartArt, notes, grouped objects, embedded objects, macros, or uncertain image text add explicit
risk reasons. High-stakes user intent selects strict mode regardless of file features.

## Translate once

`occurrences` are the complete location inventory. `translation_units` are the safely reusable
model tasks. Reuse requires equal source text, target language, role, context signature, and
protected tokens. Ambiguous short text stays separate.

Search the shared glossary only for text in the current translation units. Use exact matches first,
then the longest non-overlapping contained terms, then professional contextual translation.

## Write once

Fast `.pptx` jobs mutate all target OOXML text nodes in one archive pass. Complex jobs index shapes
once per slide, write all paragraphs for a shape, perform one local fit check for that shape, and
save once. Never overwrite the source and never carry a prior translated deck forward as input.

## Verify by risk

Deterministic verification precedes visual work: source hash, ZIP integrity, slide count, stable
occurrence IDs, exact expected translations, protected tokens, relationships, and media. Microsoft
PowerPoint then opens the final file and exports one PDF in the same session used to create final
thumbnails.

Fast jobs render all final slides at low resolution and risk slides at high resolution. Complex
jobs add all changed/risk slides at high resolution. Strict jobs render source and target fully.
After a local repair, rerender only affected slides unless new evidence expands the risk set.
The render stage produces review evidence but does not complete delivery. Delivery requires an
explicit successful visual-review gate through the pipeline's `deliver` command.
