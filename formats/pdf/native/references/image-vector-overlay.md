# Image text as a vector PDF overlay

Use this method for diagrams, screenshots, equipment illustrations, and raster
engineering drawings that contain translatable text.

## Required architecture

Keep two independent layers:

1. **Clean raster base:** original XObject pixels with only source text removed.
2. **Vector text overlay:** translated English drawn by ReportLab with an
   embedded TrueType font.

Do not draw new English into a low-resolution image. Scaling the image will
blur the text and may make nearby drawing lines appear damaged.

## Metadata

Image pixels use top-left origin. PDF placement uses bottom-left origin and
points.

```json
{
  "images": [
    {
      "id": "page-6-process-diagram",
      "source": "images/process-original.png",
      "output": "images/process-clean.png",
      "page": 6,
      "placement": [196.92, 114.10, 222.36, 283.68],
      "regions": [
        {
          "box": [40, 181, 101, 223],
          "clean_box": [40, 181, 101, 223],
          "mode": "neutral_plain",
          "text": "Thermal-Oil Pump Set\nand Heat Exchanger",
          "max_font": 3.0,
          "color": [0.07, 0.07, 0.07]
        },
        {
          "box": [300, 291, 343, 405],
          "clean_box": [300, 291, 343, 405],
          "mode": "neutral_plain",
          "text": "Fuel-Gas Heat Exchanger",
          "max_font": 3.0,
          "rotation": 90
        }
      ]
    }
  ]
}
```

`placement` is `[x, y, width, height]` in PDF points. `box` controls vector text
placement. `clean_box` controls which raster pixels may change; keep it tighter
when a leader line lies near the label.

## Cleanup modes

| Mode | Use |
|---|---|
| `neutral_plain` | Black/gray text on a verified blank background |
| `neutral_lines` | Neutral text near long horizontal/vertical structure |
| `neutral_boundary` | Neutral text near structure connected to box edges |
| `red` | Red text; no red drawing line crossing the box |
| `cyan` | Cyan text with long horizontal leader-line protection |
| `ui_glyph` | Dark or light text on a colored software-UI fill; removes only contrasting glyph pixels and protects long dividers |
| `ui_text_patch` | Preferred for compressed UI screenshots: reconstructs each tight word box row-by-row from its real left/right pixels, preserving scanlines, gradients, and horizontal dividers |
| `anchored_line_restore` | Neutral text intersects a recoverable engineering line; clean glyphs, then restore only explicit opposite-edge anchors |
| `text_only_area` | Entire box is text-only background; no drawing pixels |

Use `cyan_glyph` and `white_text_area` only as backward-compatible aliases for
`text_only_area`.

Select the cleanup mode through
[image-localization-routing.md](image-localization-routing.md). Do not use a
raster cleanup mode when editable native text exists. For
`anchored_line_restore`, declare `line_anchors` with absolute native-image
coordinates, compatible endpoint colors, width, and tolerance.

For screenshots, prefer word-level OCR boxes with `ui_text_patch`; use
`ui_glyph` only when the text box overlaps a vertical structure that row
reconstruction would remove. Do not use
`text_only_area` over a colored toolbar, button, field, icon, border, or divider.

Run at least two OCR scales for compressed screenshots: native resolution and
3x-4x upscaled. Map all boxes back to native pixels before cleanup. Group
repeated screens into UI families and reuse reviewed boxes for fixed chrome
such as `FOLDER/LOCATION` headers and function keys. A cropped XObject is a new
variant: scale or redefine its template instead of reusing absolute coordinates.

## Coordinate mapping

For image size `(Iw, Ih)`, placement `(Px, Py, Pw, Ph)`, and pixel box
`(x0, y0, x1, y1)`:

```text
left   = Px + x0 * Pw / Iw
right  = Px + x1 * Pw / Iw
bottom = Py + (Ih - y1) * Ph / Ih
top    = Py + (Ih - y0) * Ph / Ih
```

Use these page coordinates for the vector text rectangle.

## Commands

```powershell
python scripts/build_clean_image_bases.py metadata.json --report clean-report.json

python scripts/apply_image_vector_text.py `
  translated-native.pdf metadata.json translated-with-image-text.pdf
```

Pass `--regular-font` and `--bold-font` when Arial or DejaVu Sans is not
available.

## Verification

- Clean image dimensions equal source dimensions.
- Changed pixels outside all `clean_box` regions equal zero.
- Protected saturated engineering pixels changed equal zero.
- Clean image is embedded at the original page placement.
- Every metadata `text` value appears in page text extraction.
- A geometric overlap scan reports zero collisions between native text and
  vector image-label text.
- Pages outside the approved image set have identical content streams.
- High-resolution render contains no source text, white-box damage, blur,
  overlap, or clipped label.
- Difference and 50% alpha-overlay evidence has been inspected; every declared
  restored line passes continuity verification.
