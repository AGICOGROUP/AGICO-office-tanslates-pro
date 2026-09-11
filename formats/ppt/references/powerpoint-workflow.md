# PowerPoint lightweight workflow

The common Office task entry dispatches to `scripts/ppt_pipeline.py`; its existing commands remain
compatible. Preparation, native package writing, structural verification, and final PowerPoint
rendering remain separate resumable stages. Internal OOXML and COM helpers must not be assembled
into another workflow.

## Inventory and translation

Read the OOXML package once. Record native text with stable slide, shape, paragraph, table-cell,
context, and protected-token locations. Group identical media bytes by SHA-256. Reuse a translation
only when source text, target language, context, role, and protected tokens match.

Retrieve only glossary terms matched to the extracted source text. Translate remaining units through
the shared worklist and write accepted final decisions in one atomic package pass.

Preserve OLE/Visio/PDF embedded objects and their preview images unchanged by default, report them
as untranslated warnings, and continue. Require a native handler only when the user explicitly asks
to translate content inside an embedded object.

Charts, SmartArt, notes, and custom master/layout text outside supported slide paragraphs remain
untranslated. Inventory lists their exact package paths and SHA-256 values in `preserved_parts`;
warnings carry through the manifest, verification, and delivery. Verification checks those bytes
and all non-slide package parts against the original working source.

## Images

Screen each unique image once at normal useful resolution. Use only `skip_target`, `skip_unclear`,
or `overlay`. Do not repeat OCR, open a high-resolution recognition loop, or block the presentation
for unclear image text. `overlay` uses `bilingual_below` and editable PowerPoint text while the
original image remains unchanged.

The OOXML writer adds native text boxes in the same atomic ZIP pass as paragraph translations.
It preserves existing image bytes, geometry, and shape styling. Overlays require ungrouped,
unrotated, unflipped image hosts with explicit geometry; an unsupported host returns the overlay
ID and correction guidance. A failed write leaves the previous generated output intact.

## Verification

Hash the source and converted working copy during inspection and check both before applying.
Protect both paths from output replacement, and recheck source integrity during verification. Check package
integrity, slide count, native translations, protected tokens, and required overlays. Then open the
output in a hidden background session in PowerPoint and create one low-resolution render of every
final slide without an external PDF conversion gate. The visual review checks only missing native text,
clipping, overlap, broken layout, and obviously misplaced overlays. If native rendering is unavailable
or exceeds 60 seconds, review any available slides and disclose the unreviewed pages on delivery.
The warning applies only to an unchanged output that passed structural verification; known opening
failures and serious visual defects remain blocking.
