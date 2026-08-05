# Manifest contract

Copy page geometry and `source_lines` from `extraction-report.json`; do not renumber source-line IDs.

```json
{
  "source": "C:/docs/input.pdf",
  "source_sha256": "...",
  "selected_pages": [1],
  "pages": [{
    "source_page": 1,
    "width_pt": 595.28,
    "height_pt": 841.89,
    "render_path": "C:/job/extract/source-pages-400dpi/source-page-01.png",
    "pixel_width": 3307,
    "pixel_height": 4678,
    "dpi": 400,
    "vector_lines": [{"points": [100, 220, 800, 220], "width": 0.45, "color": [0, 0, 0]}]
  }],
  "source_lines": [{"id": "p01-l001", "page": 1, "box": [100, 100, 300, 140], "text": "原文", "score": 0.97}],
  "blocks": [{
    "id": "p01-title",
    "page": 1,
    "source_line_ids": ["p01-l001"],
    "source": "原文",
    "translation": "Professional English",
    "role": "title",
    "status": "translated",
    "action": "replace",
    "box": [100, 95, 600, 160],
    "clean_box": [98, 98, 305, 144],
    "background": "sample",
    "bold": true,
    "align": "left",
    "valign": "top",
    "color": [0, 0, 0],
    "max_font": 18,
    "min_font": 11
  }]
}
```

Coordinates are in source-render pixels with origin at top left. Colors are RGB floats from 0 to 1 for text/vector lines; cleanup backgrounds use integer RGB 0–255 or `sample`.

`preserve_confirm` blocks must use `action: preserve`, keep a nonblank `source`, and state the reason in `translation` (for example `Trademark; preserve exactly`). A manifest is invalid if any source-line ID is missing, duplicated, or assigned to an unknown block.

Use `status: bilingual_complete` with `action: preserve` only for a complete
Chinese/English diagram region. `bilingual_evidence` must contain
`clear_source_label_count`, the equal `matched_bilingual_pair_count`,
`unmatched_source_label_count: 0`, and a 64-character
`source_region_sha256`.

Page `layout_adjustments` use source-render pixel coordinates and require
`original_box`, `target_box`, `scale`, `trigger: text_does_not_fit`,
`fit_failure: true`, and `approved_background_regions`. Target boxes must stay
on the same page, preserve aspect ratio, and avoid every `protected_box`.
`source_box`, when present, must equal `original_box`. Both the original and
target boxes must avoid all translated/preserved text blocks because this
fallback does not transform text coordinates with the image.

Use `vector_lines` only when a cleanup box necessarily removed a known straight segment. Coordinates must come from visible anchors on both sides; never guess hidden geometry.

## Rich text and exact source-icon reuse

Use `rich_lines` only when a block needs mixed colors/emphasis or an icon lies inside an unavoidable cleanup area. Each line is an ordered list of runs. Text runs support `color` and `bold`; source-crop runs require an in-bounds `source_box` and non-empty `alt` description.

```json
{
  "id": "p07-command",
  "page": 7,
  "source_line_ids": ["p07-l014"],
  "source": "按图标，然后选择确认",
  "translation": "Press , then select [OK]",
  "role": "list_item",
  "status": "translated",
  "action": "replace",
  "box": [420, 630, 1760, 720],
  "clean_box": [418, 632, 1110, 710],
  "background": [255, 255, 255],
  "min_font": 7,
  "max_font": 10,
  "rich_lines": [[
    {"type": "text", "text": "Press ", "color": [0, 0, 0]},
    {"type": "source_crop", "source_box": [690, 642, 728, 680], "alt": "original menu icon"},
    {"type": "text", "text": ", then select [OK]", "color": [1, 0.35, 0], "bold": true}
  ]]
}
```

Coordinates for `source_box` use the same top-left source-render pixel system. The crop is taken from the immutable `render_path`, not from the cleaned base. Keep its box tight around the original icon. The validator rejects out-of-page crops, blank alt text, unknown run types, invalid RGB values, and rich text that does not match `translation` after normalization.
