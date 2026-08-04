# Same-slide typography and conditional fit

## Classify peer roles

Classify native text objects on each slide as slide title, peer section headings, or peer body text. Infer roles from hierarchy, position, repetition, and the source design; do not treat different hierarchy levels as peers.

- Keep all peer section headings at one font size and bold.
- Keep all peer body text at one font size.
- Preserve the source font family, color, alignment, and hierarchy unless the fit sequence below requires a recorded local change.
- Apply a font-size reduction uniformly to the affected peer role group; never shrink only one sibling heading or body box.

## Gate layout changes

Do not alter layout when translated text fits. A layout change requires verified overflow or collision evidence from PowerPoint bounds, rendered inspection, or both. Record the affected slide, objects, and evidence.

When the gate is met, apply this sequence:

1. Shorten the English without losing professional meaning, supplied terminology, numbers, units, or protected tokens.
2. Enable wrapping and slightly tighten paragraph or character spacing.
3. Reduce the affected peer role group uniformly, with an 85% floor relative to its source size.
4. Expand or reposition text boxes within available whitespace while preserving alignment, margins, reading order, and slide balance.
5. Move or proportionally scale non-background images only as much as required. Preserve aspect ratio, crop intent, z-order, legibility, and all engineering content; do not distort, crop away, redraw, or cover image details.
6. Use manual review when the slide still cannot fit safely.

## Verification

- Confirm peer section headings remain equal-sized and bold.
- Confirm peer body text remains equal-sized.
- Confirm unchanged slides retain their original geometry.
- For changed slides, compare object geometry before and after and verify every change is tied to recorded overflow or collision evidence.
- Recheck text clipping, overlaps, image readability, engineering topology, and slide balance at full-slide render size.
