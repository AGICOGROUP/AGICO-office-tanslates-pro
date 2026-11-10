---
name: office-translate-pro-ppt
description: Use when translating PowerPoint .ppt or .pptx presentations while preserving native text, slide geometry, graphics and technical content.
---

# PowerPoint pipeline

Top-level routing is complete. Do not run the root Office router again.
Follow the [shared workflow](../../references/translation-decisions.md) from the skill root.

## Choose the delivery mode

For bilingual PowerPoint, deliver one presentation in source/target pairs:
A1, B1, A2, B2, through the last slide. Each A slide is the source page,
and each B slide is its target-language counterpart. Keep a pair even for
photo-only or already bilingual slides. On B, reuse correct target wording
and complete missing target text. Keep terminology consistent across native
text and images.

Prepare and finalize a one-to-one target deck with the shared PPT workflow
(default mode). Then pair it with the prepared source .pptx:

```text
python formats/ppt/scripts/pair_slides.py <prepared-source.pptx> <verified-target.pptx> <private-paired.pptx>
```

This uses Microsoft PowerPoint, verifies the pair order and embedded picture
bytes, and reopens the candidate. Use the working .pptx for legacy .ppt inputs.
If PowerPoint is unavailable or pairing fails, keep the verified target deck,
diagnose the failure, and report the bilingual deliverable as pending. Render
the paired candidate and inspect A/B order, slide dimensions, and visual
fidelity before publishing. The Excel bilingual flag does not select this mode.

## Translate within the slide design

Translate complete paragraphs and table cells in context with the matched
`../../references/水泥专业名词中英对照.md`. Preserve technical values, meaningful line breaks,
shape geometry, themes, relationships, animations and boundary spaces. Prefer concise, natural
target language that fits the available shape; do not summarize away meaning to force a fit.
Reset inherited character or paragraph spacing when it causes letter gaps
or overlapping lines. Repair wrapping within the slide and check the rendered
result before changing geometry.

For embedded images, read [image writeback](references/image-text-localization.md) and its shared
rule. Translate readable embedded text with an image editing tool in its
original position on B. Preserve artwork and check the actual replacement
bytes. Keep real photographs unchanged, including signage and lettering.

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
