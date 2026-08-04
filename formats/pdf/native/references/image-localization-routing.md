# Image localization routing

Use this reference for every image, diagram, engineering drawing, screenshot,
logo, chart, or scanned technical label that contains source-language text.

## Source priority

Use the first available source in this order:

1. Editable native text in a PDF page or Form XObject.
2. Editable SVG, CAD, presentation, or other layered source supplied inside the
   original document package.
3. The original embedded image XObject at native dimensions.
4. A source-page render and crop only when no original asset exists; render at
   least twice final display size and inspect dense drawings at 3x scale.

Never use an earlier translation, viewer screenshot, or recompressed derivative
as the source.

## Required inventory

Create one image record for every original asset and one stable label record for
every detected source-language label. Run OCR at native scale and again at 3x-4x
scale, map both passes to native coordinates, and manually audit residual hits.

Each image record must contain:

- `id`, page/resource identity, source hash, pixel dimensions, and PDF placement;
- `asset_type`: `editable_vector`, `raster_simple`, `raster_structured`,
  `raster_complex`, or `unreadable`;
- `method`, expected/translated/preserved/confirm counts, structural-review
  status, and final page;
- `labels`, including stable ID, box, source text, translation, label type, OCR
  confidence, status, and method.

Use this review shape:

```json
{
  "complete": true,
  "reviewed_image_ids": ["page-6-process-diagram"],
  "images": [
    {
      "id": "page-6-process-diagram",
      "asset_type": "raster_structured",
      "method": "anchored_line_restore",
      "contains_source_text": true,
      "expected_label_count": 2,
      "translated_label_count": 1,
      "preserved_label_count": 1,
      "confirm_count": 1,
      "structural_review_complete": true,
      "labels": [
        {
          "id": "label-001",
          "source_text": "烟囱",
          "translation": "Chimney",
          "ocr_confidence": "high",
          "method": "anchored_line_restore",
          "status": "translated"
        },
        {
          "id": "label-002",
          "source_text": "…",
          "translation": "",
          "ocr_confidence": "low",
          "method": "preserve_confirm",
          "status": "confirm"
        }
      ]
    }
  ],
  "confirm_items": [
    {"label_id": "label-002", "reason": "source pixels are unreadable"}
  ]
}
```

## Method router

Choose the first method whose predicate is satisfied. Fail closed when its
evidence is incomplete.

If an engineering diagram or flowchart already contains both the source text
and an English counterpart for its labels, preserve the original image
unchanged. Record the labels as reviewed and preserved; do not clean the raster,
remove either language, or add another English overlay.

| Method | Use when | Required output |
|---|---|---|
| `native_edit` | Editable PDF/Form/SVG/CAD text exists | Replace native text while preserving vectors and layers. |
| `deterministic_cleanup` | Raster text lies on a verified simple background | Clean only glyph pixels with a reviewed cleanup mode. |
| `anchored_line_restore` | Raster text crosses a recoverable engineering line | Clean glyphs and reconnect only explicit opposite-edge anchors. |
| `constrained_clean_base` | A complex raster region defeats deterministic cleanup | Produce a local text-free clean base candidate and pass structural gates. |
| `preserve_confirm` | Text or structure cannot be recovered safely | Preserve the original region and create a `[CONFIRM]` record. |
| `preserve_bilingual` | Every clear Chinese label already has a semantic English counterpart | Preserve the exact original asset; record complete pair counts and zero unmatched Chinese labels. |

Do not choose a raster method when an editable native source exists. Do not
choose `constrained_clean_base` merely because manual annotation is tedious.
The presence of some English never proves a diagram is bilingual-complete.
Inventory all clear Chinese labels; use `preserve_bilingual` only when the
matched-pair count equals the clear-Chinese count and the unmatched count is
zero. Otherwise translate only the unmatched Chinese labels.

## Anchored line restoration

Declare every restorable segment explicitly in the cleanup region:

```json
{
  "mode": "anchored_line_restore",
  "box": [40, 80, 120, 112],
  "clean_box": [40, 80, 120, 112],
  "line_anchors": [
    {
      "start": [40, 96],
      "end": [119, 96],
      "width": 1,
      "color_tolerance": 40
    }
  ]
}
```

Endpoints must touch opposite cleanup-box edges and have compatible colors. The
script interpolates only the declared segment inside the box. Missing,
same-edge, incompatible, or ambiguous anchors are failures; never infer a new
branch, bend, arrow, pipe, or connection.

## Constrained clean-base fallback

Use high-fidelity image editing only for the approved local regions. Supply the
exact original asset, the label inventory, and this output contract:

```text
Use case: text-localization clean-base reconstruction.
Remove only the listed source-language glyphs from the approved regions.
Return a text-free clean base. Do not draw target-language text.
Preserve every device, vessel, pipe, arrow, symbol, border, color, number,
equipment relationship, image boundary, aspect ratio, and resolution.
Do not redesign, crop, sharpen, blur, add objects, remove objects, or alter flow.
If underlying structure cannot be recovered reliably, leave the region
unchanged and report it for confirmation.
```

Restore all pixels outside approved regions from the original before checking
the candidate. Reject any candidate that changes protected colors, line anchors,
topology, symbols, borders, dimensions, or aspect ratio.

Never ask an image model to generate final English. After the clean base passes,
add English as embedded PDF vector text through `apply_image_vector_text.py`.

## `[CONFIRM]` policy

Do not guess characters, units, model numbers, equipment tags, or topology. A
confirm item must identify the page, image, label box, OCR text, uncertainty,
current treatment, and recommended source or decision. Reported confirm items
may remain preserved; unreported confirm items block delivery.

## Per-image review

Require all of the following before accepting an edited image:

- all inventoried labels are translated or explicitly confirmed;
- numbers, units, models, standards, and symbols match the source;
- source and clean image dimensions are identical;
- pixels outside approved regions are identical;
- protected engineering colors and declared lines pass;
- original, clean base, difference image, and 50% alpha overlay are reviewed;
- no new object, lost structure, white-box damage, blur, overlap, or clipping is
  visible;
- the final page at actual placement remains clear and correctly anchored.
