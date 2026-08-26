# PowerPoint lightweight workflow

`scripts/ppt_pipeline.py` is the only production entry. It performs one inventory, one preparation,
one write, one verification, and one final PowerPoint render. Internal OOXML and COM helpers must
not be assembled into another workflow.

## Inventory and translation

Read the OOXML package once. Record native text with stable slide, shape, paragraph, table-cell,
context, and protected-token locations. Group identical media bytes by SHA-256. Reuse a translation
only when source text, target language, context, role, and protected tokens match.

Retrieve only glossary terms matched to the extracted source text. Translate all remaining units
in one batch and write them once.

Preserve OLE/Visio/PDF embedded objects and their preview images unchanged by default, report them
as untranslated warnings, and continue. Require a native handler only when the user explicitly asks
to translate content inside an embedded object.

## Images

Screen each unique image once at normal useful resolution. Use only `skip_target`, `skip_unclear`,
or `overlay`. Do not repeat OCR, open a high-resolution recognition loop, or block the presentation
for unclear image text. `overlay` uses `bilingual_below` and editable PowerPoint text while the
original image remains unchanged.

## Verification

Hash the source during inspection and compare it once during final verification. Check package
integrity, slide count, native translations, protected tokens, and required overlays. Then open the
output in a hidden background session in PowerPoint and create one low-resolution render of every
final slide without an external PDF conversion gate. The visual review checks only missing native text,
clipping, overlap, broken layout, and obviously misplaced overlays.
