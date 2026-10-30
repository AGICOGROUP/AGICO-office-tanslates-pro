---
name: office-translate-pro-ppt
description: Use when translating PowerPoint .ppt or .pptx presentations while preserving native text, slide geometry, graphics and technical content.
---

# PowerPoint pipeline

Top-level routing is complete. Do not run the root Office router again.
Follow the [shared workflow](../../references/translation-decisions.md) from the skill root.

## Translate within the slide design

Translate complete paragraphs and table cells in context with the matched
`../../references/水泥专业名词中英对照.md`. Preserve technical values, meaningful line breaks,
shape geometry, themes, relationships, animations and boundary spaces. Prefer concise, natural
target language that fits the available shape; do not summarize away meaning to force a fit.
Remove unsafe inherited negative Latin spacing before changing font size or geometry.

For embedded images, read [image writeback](references/image-text-localization.md) and its shared
rule. Translate labels at their original positions, preserve the picture extent/crop/rotation,
and verify actual replacement bytes. External legends and text-box covers do not translate an image.

Charts, SmartArt, notes, master/layout text and embedded objects without a supported translator stay
preserved with specific warnings. Do not translate an embedded object's preview instead of its native
content or claim those objects were translated. Actual template prompts are not slide body text.

## One render, focused repair

Finalize verifies the private candidate and renders it once using a hidden, bounded Microsoft PowerPoint
session when available. At `visual-review`, inspect the rendered slide set with attention to dense
tables, expanded translations, image replacements and any visible clipping/overlap. Readable text
near the bottom edge is not automatically a defect. Use `measure-fit` and `fit-text` only for an
observed or measured fit problem, then rerender the affected output after repair.

After actual review, continue the same finalize command with `--visual-review-passed`; unchanged
verified work/renders are reused. Missing rendering can permit a structurally verified file with a
clear warning; serious clipping, changed values and confirmed opening failures still need repair.
No routine PDF conversion or second whole-deck audit.

For a confirmed stale OLE/Visio overlay or a package-level repair, read
[native repair procedures](references/powerpoint-workflow.md). Use the supported repair/amended-baseline
commands, preserve the original, and verify the honest amended package; do not reserialize unrelated
parts or hand-edit success flags. `scripts/ppt_pipeline.py` is the native adapter, not a second workflow.
