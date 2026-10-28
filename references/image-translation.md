# Embedded-image handling

This reference applies to pictures inside Office files, not standalone image translation.
Inspect each unique source image once. Translate readable labels with the current model and the
same engineering terminology as the native text. Follow the user's image-language and bilingual/
replacement choice. Keep the original label locations: a separate legend is not image translation.

## Classify once

- Logo-only/wordmark, photograph with no document text, or labels already in the requested mode:
  retain the original bytes with a specific reason. Do not regenerate branding.
- Readable document labels: localize them, preserving equipment identity/counts, topology,
  arrows, values, identifiers, logos, aspect ratio and placement.
- Genuinely illegible text or an unsupported host: identify the affected image/labels precisely.
  Do not guess text or describe an unmodified picture as translated.

An image mixing a logo and real labels still needs its labels localized. Partially bilingual
artwork is not a reason to skip the remaining source-only labels.

## Two accepted methods, subject to current tool permissions

Use the image-editing tool actually available in the current session. Tool instructions take
precedence over this reference. Discover its current schema; do not assume an old tool name or
parameter set. For example, `image_gen.imagegen` accepts a prompt and local referenced image paths;
another host may expose `image_edit`. Absence of that historical name is not an image capability failure.

**Generative editing:** inspect the extracted original first, submit it as the reference with a
reviewed source→target label table, requested language/mode, canvas dimensions and preservation
constraints. Ask for one translated version, not visual variants. No invented details or redesign.

**Deterministic erase + refill:** when explicitly allowed by the user's or current session's image
instructions, the bundled `scripts/inimage_erase_refill.py` can preserve engineering line art by
changing only text pixels. For simple labels on clear backgrounds it avoids regenerating geometry.
If the session requires an image tool for edits, use that tool; this reference is not an exemption.

```text
python scripts/inimage_erase_refill.py ocr <image> --out <job>/labels.json
python scripts/inimage_erase_refill.py render <image> --labels <job>/labels.json --out <job>/localized.png --report <job>/image-report.json
python scripts/inimage_erase_refill.py verify <image> <job>/localized.png --labels <job>/labels.json
python scripts/inimage_erase_refill.py zoom <image> --box X0 Y0 X1 Y1 --scale 3 --out <job>/crop.png
```

The label table has entries such as
`{"labels":[{"source":"冷却机","target":"Cooler","x0":10,"y0":20,"x1":90,"y1":45,"angle":0,"size":14}]}`.
OCR is only a draft; hand-transcribe if unavailable and review against enlarged crops.
Oblique or rotated labels crossing meaningful linework need a safer editing method, not a larger
erase rectangle. Method-specific metrics `outside_changed_pct` ≈ 0 and
`outside_edges_retained_pct` = 100 apply to deterministic edits only.
Register the output with the same `localized` decision fields as generative edits.

## One edit, concurrent text work, focused correction

Keep one in-flight request per unique source image and requested mode. While it runs, translate
and merge native document text. Resume the same running request instead of starting another because
it is slow. Inspect the returned file before correcting it. A correction names a concrete missing/
wrong label, unreadable region, changed technical value or non-text meaning; cosmetic font,
antialiasing or minor stroke differences do not justify another generation. Preserve the best usable
version if a later attempt regresses. Do not reuse prior job results for a fresh test.

Generative edits can change pixels. Judge their actual meaning and readability rather than requiring
pixel identity: equipment, numbers, topology, logo and layout must still be preserved. Disclose material
redraw limitations. Deterministic edits must preserve pixels outside the intended text masks and
their verification metrics must come from the real output.

## Normalize and write back

Read the real source and result dimensions. Keep the source display ratio, no content cropping,
no independent width/height stretching, no lower resolution. Size/ratio drift alone does not call
for another generation: use `scripts/normalize_generated_image.py` to fit or pad proportionally, then
inspect the saved file. For WMF/EMF, keep the original vector and use a clear raster edit target at
the original display ratio; disclose raster replacement where relevant.

Record `localized` with the supplied current-job ID/hash and an absolute `replacement_path`.
The format writer must insert those actual bytes into every intended occurrence and verify the
saved package, preserving anchors, crops, z-order and unrelated content. A review flag or generated
file outside the document does not prove writeback. Reuse the accepted replacement across matching
occurrences inside this job. Resolve the remaining image batch until none is pending.
