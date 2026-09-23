# In-image text translation — shared Office rule

Translate every readable image label into the user's requested language, using the current model
and relevant terminology. Follow the requested monolingual replacement or bilingual mode. If the
user explicitly permits either image mode, choose the clearest, fastest implementation.
Translations must appear inside the image at the corresponding label locations. A separate legend,
caption, appendix or image-review flag does not satisfy this requirement.

The model always produces the wording. A method only renders it. Choosing a method is never
permission to call a third-party translation service.

## Classify before editing: logo-only images are retained, never regenerated

Classify every extracted image before planning an edit. An image whose only content is a logo,
wordmark or brand mark carries **no document text**: record it as retained with note `logo-or-brand`,
preserve its bytes unchanged at every occurrence, and do **not** re-render it by either method.
Generative redrawing of brand artwork adds no translated label while risking changed lettering,
spacing, colour or icon form, which breaks brand identity. Company and product names inside a logo
lockup stay untranslated in both monolingual and bilingual output; this is a correct retain, not an
omission, and must not be counted against translation coverage.

This exemption is only for logo-only images. An image that combines a logo with real document labels
is still translatable: localize those labels and keep the logo element itself unchanged.

## Two accepted methods — select by image structure, not by habit

| Method | Mechanism | Correct choice when |
|---|---|---|
| **A · Generative image editing** — native `image_edit` | redraws the whole canvas with the target wording | photographs, equipment renders, shaded or 3D art, hand-drawn sketches, textured or noisy backgrounds, lettering fused into artwork, and any label whose erase box would have to cover a graphic that carries meaning |
| **B · Deterministic erase + refill** — `scripts/inimage_erase_refill.py` | source pixels are never regenerated; only glyph pixels are rewritten and the target is typeset with a real CJK font | technical line drawings, schematics, P&IDs, dimensioned diagrams, tables-as-image — anything where linework, arrows, hatching, circle outlines and borders must survive unchanged |

Select in this order:

1. Logo-only → retain (rule above). Neither method applies.
2. Labels sit as dark text over flat or gradient fills **and** the non-text content is line art →
   method **B**. It is the fidelity-preserving default for engineering graphics: measured on a
   two-sheet auger schematic it held 100.0% of strong edges and 0.000% pixel change outside the
   label boxes, where method A retained 21.5%.
3. The image is a render, photo or sketch, or B cannot free a label without eating a graphic →
   method **A**.
4. Decide per image, never per document. A file may legitimately mix both.

No method is universally correct, and no run may treat either one as mandatory. Record the chosen
method and its reason in the image decision, and keep the quality criteria below for both.

## Method A · native `image_edit`

Name the concrete tool, not an approximation. If `image_edit` is unavailable, report the blocker and
keep that image pending rather than substituting another method or claiming completion. Do not assume
that generated non-text content is unchanged.

Call `image_edit` with exactly this parameter shape:

- `reference_images`: the stable asset ID of the extracted clean source image (never a rewritten
  URL, never a screenshot of an entire Office page). For WMF/EMF, render the original clearly
  first and use that raster as the edit target; preserve the source vector separately.
- `resolution`: `2K`.
- `must_change`: one entry — replace all source-language text with the reviewed translation at
  each label's original location.
- `must_keep`: numbers and unit values unchanged (render units in Latin: m³, kg, t, mm, μm, °C),
  equipment renders, icon counts, arrows, connections, linework, panel shapes, background,
  colors, layout, identifiers and logos, and the recorded source canvas size with its exact
  aspect ratio.
- `prompt`: the full per-label `source → target` pair table transcribed from the image, the
  explicit canvas dimensions and ratio, closing with a text-only-edit / no-redesign /
  no-invented-details line.

### Dimension gate before registering the decision

Before the edit, record the source image's pixel width, pixel height and exact aspect ratio in
the image decision. For WMF/EMF or another vector source, use the clean raster edit target's pixel
dimensions; if the raster target is derived from the Office placement, preserve that displayed
aspect ratio. State these dimensions and the ratio explicitly in the edit prompt.

`image_edit` output is generative and its canvas may deviate from the source by a few pixels
(e.g. a 1312×1199 source returning 1312×1200, which the pipeline's exact-ratio verify rejects).
Measure the actual returned pixels before accepting the replacement: they must equal the recorded
source dimensions or exceed both by the same scale factor; never smaller, never independently
stretched, never cropped. When the ratio or size deviates, run `scripts/normalize_generated_image.py`
— `fit()` resamples back to the exact source dimensions when the output is at least as large;
`normalize()` pads a differently shaped larger canvas with background — then re-verify the restored
file. Never crop to fix a ratio.

## Method B · deterministic erase + refill

`scripts/inimage_erase_refill.py` from the Skill directory. The label table is JSON
`{"labels": [{"source", "target", "x0", "y0", "x1", "y1", "angle", "size"}]}`; a row with an empty
`target` is left untouched, which is how a deliberately retained label is expressed.

```text
python scripts/inimage_erase_refill.py ocr    <image>          --out <job>/img-<n>.labels.json
python scripts/inimage_erase_refill.py render <image> --labels <job>/img-<n>.labels.json --out <job>/img-<n>-zh.png --report <job>/img-<n>-report.json
python scripts/inimage_erase_refill.py verify <image> <job>/img-<n>-zh.png --labels <job>/img-<n>.labels.json
python scripts/inimage_erase_refill.py zoom   <image> --box X0 Y0 X1 Y1 --scale 3 --out <job>/crop.png
```

1. `ocr` pre-fills boxes and text (needs `rapidocr_onnxruntime`; if absent, hand-author the table
   from a full-image read plus `zoom` crops). Review it against the image before translating: OCR
   misses short labels and splits stacked ones, and every miss becomes surviving English.
2. Translate each `source` into `target`, keeping numbers, units and identifiers verbatim.
3. `render` erases glyph pixels only and typesets the target at the freed position, matched size,
   colour and alignment.
4. `verify` **must** report `outside_changed_pct` ≈ 0 and `outside_edges_retained_pct` = 100 before
   the result is registered. A nonzero value means a bad box coordinate or a mis-ordered table, not a
   broken method — fix the table and re-render. It returns an `error` if the canvas changed at all;
   method B never regenerates the image, so that is always a defect.
5. Register the output with the same `localized` decision fields as method A.

### Method B limits — do not fight them

- **Oblique or rotated labels.** An axis-aligned erase box around text set at an angle also covers
  whatever the text runs alongside. When that is a load-bearing graphic (a member outline, a circle
  or arc), leave the label in the source language and record the reason. Damaging geometry to gain
  one translated label is the wrong trade.
- **No colour-path rescue for the case above.** Restricting erasure to pixels on the
  background→stroke line was tried and reverted: it was globally neutral but mis-estimated the stroke
  colour whenever a box held both a dark outline and light text, so the source text survived instead.
- Never hand-edit the output to fake a passing `verify`.

## Review and reinsertion (both methods)

Inspect the returned image against the source, checking every readable label and non-text detail.
The user accepted the GPT-edited CIM pyramid trial as sufficient quality. Judge output by readable,
accurate translations and preserved engineering meaning and overall appearance. For method A, minor
changes in stroke rendering, antialiasing, spacing or icon appearance are acceptable when they do not
alter equipment identity, counts, topology or technical values; do not regenerate solely for such
cosmetic differences, and do not claim pixel-exact reproduction — generative editing redraws the
canvas, so disclose that stroke-level differences exist while numbers, topology and layout are
verified unchanged. For method B, pixel identity outside the label boxes is required and measured, so
report it as a number rather than as an impression.
Repair missing/wrong labels, unreadable text, changed values, missing equipment or changed
connections with a targeted correction.
For dense drawings with small or crowded annotations, use `inimage_erase_refill.py zoom` to produce
enlarged crops of the region — once before the edit to transcribe every label, number and unit
accurately, once after to verify the result region by region — instead of relying on whole-image
eyeballing.
Start one edit per unique image, continue document text work while it runs, inspect once and correct
only concrete defects. A successful image must be inserted back into the Office document before
claiming the file's image text is translated. Keep standalone trials distinct from delivery.

Check the actual saved image and its placement in the Office file. Preserve the source document,
anchors, crop, relationships and unrelated content. Image hashes may change only for approved
replacements. If the adapter lacks a replacement writer, implement and verify it before claiming
an integrated result; never bypass verification or substitute a legend. Reuse each reviewed edited
image across its occurrences within the current job. Logo-only images follow the retention rule above
and are never re-rendered; already translated labels may remain unchanged. Flag genuinely
illegible source text specifically, never guess it.
