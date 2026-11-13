# Embedded-image handling

This reference applies to pictures inside Office files, not standalone image translation.
Inspect each unique source image once. Use the current model and the same
engineering terminology as the native text. Follow the user's image-language
and bilingual/replacement choice. Edit readable text in place with the available
image editing tool, keeping its original location. A separate legend is not
image translation.

## Classify once

- Real photographs (including sites, buildings, equipment, and people), logo-only
  images, and labels already in the requested mode: retain the original bytes
  with a specific reason. Keep lettering, banners, and nameplates within photos
  as captured. In a document or composite graphic, localize the surrounding
  printed text and keep any embedded photograph intact.
- Readable document labels: localize them, preserving equipment identity/counts, topology,
  arrows, values, identifiers, logos, aspect ratio and placement.
- Genuinely illegible text or an unsupported host: identify the affected image/labels precisely.
  Do not guess text or describe an unmodified picture as translated.

An image mixing a logo and real labels still needs its labels localized. Partially bilingual
artwork is not a reason to skip the remaining source-only labels.

Certificates, approvals and press scans are document images, not exempt photographs.
Translate their readable print in place while preserving seals, signatures and embedded photos.
Authenticity, third-party ownership, density, time/budget limits, or editing difficulty do not
justify leaving readable text untranslated. Overlap with a seal or linework calls for a safer
edit; it does not create a blanket geometry exemption. Identify truly unreadable labels precisely.

Every unchanged image decision needs both a non-empty `reason` identifying what was inspected
and an allowed `reason_code`:

| Actual content | `reason_code` |
|---|---|
| Genuine standalone site, building, equipment, people, crowd or scene photograph | `photo_exempt_site`, `photo_exempt_building`, `photo_exempt_equipment`, `photo_exempt_people`, `photo_exempt_crowd`, `photo_exempt_scene` |
| All labels already satisfy the requested language mode | `already_target` |
| No text, or logo-only artwork | `no_text`, `logo_only` |
| Genuinely unreadable source labels, identified in `reason` | `unreadable_text` |

PPT uses `skip_target` for the first three rows and `skip_unclear` only for the last.
Word/Excel use `retain` (legacy `reviewed` has the same checks). `localized` needs no retention
reason. Missing or unknown codes are rejected; old invalid decisions return to pending work.
Reinspect affected images and correct their decisions rather than guessing a code to pass validation.
These are structural checks, not proof that the classification or translation is correct.
Disclose any residual unreadable text; never describe it as translated.

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
