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

## Embedded objects and legacy previews

Preserve OLE/Visio/PDF embedded objects and their preview images unchanged by default, report them
as untranslated warnings, and continue. Require a native handler only when the user explicitly asks
to translate content inside an embedded object.

That default has one exception, and it is a quality defect whenever it is missed. A legacy OLE
preview can paint source-language artwork *over* a slide whose own text is already translated. The
object then is not the slide's content; it is a stale overlay that makes a delivered slide read in
the wrong language. Detect it by rendering the slide and comparing what the shape XML says against
what the picture shows, and confirm with a byte probe of the object parts
(`scripts/ppt_repairs.py scan-text --package <deck> --probe <source-language word>`).

Remove such a preview with `scripts/ppt_repairs.py strip-ole-preview --output <deck> --slide <n>
--shape-id <id> --report <job>/ole-strip.json`; run `--dry-run` first and check the listed parts.

- The preview renders through two paths — the `mc:AlternateContent`/`p:oleObj` OLE path and the
  `mc:Fallback` picture — while the drawing itself lives in the VML part the slide relates to.
  Deleting only the slide's `mc:AlternateContent` element does **not** remove the artwork; the parts
  must go.
- The removal set is the OLE container (`ppt/embeddings/oleObjectN.bin`), its VML drawing
  (`ppt/drawings/vmlDrawingN.vml` and `ppt/drawings/_rels/vmlDrawingN.vml.rels`), the preview media
  (`ppt/media/imageN.emf`), the slide's relationships to them, and their `[Content_Types].xml`
  overrides. Every other part must stay byte-identical.
- Keep the object and disclose it when the preview *is* the slide's content, for example an embedded
  PDF drawing with no native alternative. Blanking it destroys the slide.
- Drop a removed object from `embedded_objects` in `translation-manifest.json`: no status describes a
  removed object, and `preserved_untranslated` would keep warning about content that no longer ships.
  Record the removal in the baseline amendment instead.

Charts, SmartArt, notes, and custom master/layout text outside supported slide paragraphs remain
untranslated. Inventory lists their exact package paths and SHA-256 values in `preserved_parts`;
warnings carry through the manifest, verification, and delivery. Verification checks those bytes
and all non-slide package parts against the original working source.

## Images

Follow [shared image handling](../../../references/image-translation.md), using the active tool's
actual interface and session permissions. Inspect each unique image, translate its labels, edit, review and insert the accepted image
at its original location. Do not use native text-box overlays or external legends. Implement
and verify image-replacement support before integrated delivery.

## Repairing a verified package

`verify` compares every non-slide package part byte-for-byte against
`inventory.working_source_path`. The only tolerated deviations are the slide parts (the exemption is
`ppt/slides/slide*.xml` — note that `ppt/slides/_rels/*.rels` is **not** exempt) and media declared
`localized` with a matching replacement hash.

- Build a repair by copying parts from the working source and overriding only the parts you intend to
  change. Re-serialising the whole package through Python changes every XML part — ElementTree writes
  `<?xml version='1.0' encoding='UTF-8' standalone='yes'?>` and LF where PowerPoint wrote double
  quotes and CRLF — and verification then reports dozens of `package-part-changed` errors even though
  the XML content is equivalent.
- When the repair must delete package parts, amend the baseline rather than weakening the check:
  `scripts/ppt_repairs.py amend-baseline --job-dir <job> --deck <deck> --report <ole-strip.json>
  --reason "<why>"` writes `working-source-amended.pptx` (the original minus the removed parts, with
  `[Content_Types].xml` and the affected slide `.rels` taken from the repaired deck), repoints
  `working_source_path` and `working_source_sha256` in `inventory.json`, and records the removed parts
  with their hashes in `baseline-amendment.json`. Never edit or delete the original working source,
  and never retype a hash — copy it from the file the tool wrote.
- After any repair re-run `verify` and require `passed: true` with no errors, then `render`, inspect
  the new slide images, and only then `deliver --visual-review-passed`.

## Translated text that outgrows its frame

Translated paragraphs are usually taller than the source text. With `spAutoFit` PowerPoint grows the
shape downward and the last line lands on the slide's bottom band, so the closing sentence competes
with the frame. Measure the rendered extent instead of guessing:

```text
python scripts/ppt_repairs.py measure-fit --render <job>/final-renders/target/slide-05.png \
    --x0 0.05 --x1 0.42 --box-top-emu 1989138 --current-leading 130
```

Then tighten the leading of every paragraph in that shape by the same factor, which preserves the
paragraph hierarchy and keeps the type size and geometry intact:

```text
python scripts/ppt_repairs.py fit-text --output <deck> --slide 5 --shape-id 7174 --leading 105,115
```

- `<a:lnSpc><a:spcPct val="…"/></a:lnSpc>` must be the first child of `<a:pPr>`, ahead of
  `spcBef`/`spcAft` and the bullet elements.
- Use the actual slide design and visible frame boundary to diagnose collision. The helper's
  default 6.2M EMU target is an estimate, not a universal defect threshold; pass the real target
  when it differs. Readable text near the bottom without clipping/overlap needs no repair.
- Do not reach for smaller fonts, moved shapes or edited frames first, and leave a paragraph alone
  when its box is unchanged and its text still ends inside the frame.

## Verification

Hash the source and converted working copy during inspection and check both before applying.
Protect both paths from output replacement, and recheck source integrity during verification. Check package
integrity, slide count, native translations, protected tokens, and required image replacements. Then open the
output in a hidden background session in PowerPoint and create one low-resolution render of every
final slide without an external PDF conversion gate. The visual review checks only missing native text,
clipping, overlap, broken layout, and obviously misplaced images. If native rendering is unavailable
or exceeds 60 seconds, review any available slides and disclose the unreviewed pages on delivery.
The warning applies only to an unchanged output that passed structural verification; known opening
failures and serious visual defects remain blocking.
