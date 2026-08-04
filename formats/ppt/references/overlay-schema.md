# PowerPoint overlay manifest

`overlay-manifest.json` records translations that are safe to place above a
non-editable PowerPoint host shape. Coordinates are normalized to that host
shape, not to the slide. The source presentation and host shape remain
unchanged.

## Manifest

```json
{
  "schema_version": 2,
  "source_file": "sample.ppt",
  "overlays": [],
  "manual_reviews": [],
  "legal_evidence": []
}
```

Each `overlays` item requires:

- unique `id`, `kind: "office_overlay"`, non-empty `source_text`, and non-empty
  `translation`;
- `location.page_or_slide`, `location.host_shape_id`, and a stable
  `location.region_id`;
- `region.x`, `y`, `w`, and `h` in the closed interval `0..1`, with
  `x + w <= 1` and `y + h <= 1`;
- `style.fill_rgb` and `style.text_rgb` as exactly six hexadecimal digits;
- non-empty `style.font_name`, positive `style.font_size_pt`, Boolean
  `style.bold`, and `style.align` in `left`, `center`, or `right`.

Overlay IDs must be non-empty and unique within the manifest. Every location
must contain a positive `page_or_slide`, positive `host_shape_id`, and non-empty
`region_id`. All four region fields must be present. A location listed in
`legal_evidence` must never be referenced by an overlay.

Each shape-level `manual_reviews` item requires a complete `location` with
`page_or_slide` and `host_shape_id`, an existing `preview` path, and non-empty
`scope`, `reason`, and `evidence`. Its location set must match the inventory's
`manual_review` disposition set exactly, with no duplicates, omissions, or
extra records. Partial unsafe regions on an otherwise safe-overlay host may be
documented separately in `screening_notes`; they do not change the host's
single inventory disposition.

## Background handling

Version 2 separates source-text cleanup from translated-text layout. Use one of
these modes:

```json
{
  "source_region": { "x": 0.35, "y": 0.36, "w": 0.20, "h": 0.19 },
  "region": { "x": 0.32, "y": 0.32, "w": 0.27, "h": 0.27 },
  "background": {
    "mode": "image_patch",
    "asset_path": "patches/label-001.png"
  }
}
```

- `solid` is the legacy/default mode. It is allowed only on a visually verified
  solid, semantic-free panel. The text shape uses `style.fill_rgb`.
- `image_patch` requires `source_region` and an existing lossless PNG in
  `background.asset_path`. The adapter places this tight repair patch over the
  source text and creates a separate no-fill, no-line editable text shape at
  `region`.
- `transparent` creates only a no-fill editable text shape. Use it only when a
  previously declared patch or cleaned native host already removed the source
  glyphs; record that dependency in the manifest build notes.
- `source_region` is the smallest rectangular cleanup area that contains the
  source glyphs and necessary antialiasing pixels. Do not enlarge it to fit the
  English translation.
- `region` may be wider than `source_region` for readable English, because its
  text shape is transparent.
- A patch crossing a line, pipe, arrow, device, border, gradient, or texture must
  restore those pixels from the original image. A flat-color patch is invalid in
  that case. If reliable restoration is unavailable, use `manual_review`.

Version 1 manifests remain readable and behave as `solid`; do not create new v1
manifests for technical diagrams. Legal certificates remain `legal_evidence`
and must not receive overlays.

## Executable validation

The integration test opens the real presentation through PowerPoint COM and
validates every overlay rather than grepping this document:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_overlay_inventory.ps1
```

It rejects empty or duplicate IDs, empty source text/translations, incomplete
locations or regions, out-of-range coordinates, missing patch assets, malformed
RGB values, empty font names, non-positive font sizes, non-Boolean bold values,
invalid alignment, legal-evidence overlays, and any manual-review
inventory/manifest mismatch.

Run the v2 integration test as well:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/test_image_patch_overlay.ps1
```
