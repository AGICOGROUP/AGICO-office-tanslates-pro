# Mandatory quality gates

## Visual-review evidence

Create this only after inspecting the final rendered PDF:

```json
{
  "candidate_sha256": "<64-character SHA-256 of the exact reviewed PDF>",
  "reviewed_output_pages": [1, 2],
  "text_overlap_failures": [],
  "clipping_failures": [],
  "unreviewed_images": 0,
  "untranslated_clear_image_labels": 0,
  "logo_review_complete": true,
  "header_footer_review_complete": true,
  "image_difference_review_complete": true,
  "full_render_review_complete": true,
  "icon_review_complete": true,
  "source_icon_provenance_complete": true,
  "icon_substitution_failures": [],
  "mixed_color_failures": [],
  "reviewed_ocr_false_positives": []
}
```

An OCR false-positive record requires `output_page`, `box`, and `reason`. Accept it only after source/output crop comparison proves the pixels are artwork, a symbol, noise, or an explicitly illegible source mark. The verifier matches boxes by IoU and fails unmatched declarations.

## Delivery must satisfy all gates

- Source OCR coverage: every source-line ID assigned exactly once.
- Translation coverage: every `replace` block rendered and extractable from the output text layer.
- Cement terminology: every match from `references/cement-terminology.md` uses
  the lookup-selected translation; unmatched content may use model translation.
- Selectability: all added English exists as embedded vector text; fonts are embedded.
- Page integrity: page count, page order, dimensions, and orientation match the selected source pages.
- Graphic integrity: zero pixel changes outside approved cleanup boxes; no blurred, missing, displaced, or covered non-text structure.
- Icon fidelity: every icon preserved in the raster base or restored from exact source pixels; build-report provenance reviewed; zero text, Unicode, library-icon, or approximate-icon substitutions.
- Color fidelity: meaningful mixed colors and emphasis preserved; zero unreviewed or flattened command/link/warning color changes.
- Language residue: dual-scale OCR finds zero unexplained CJK text.
- Bilingual preservation: every exempt CJK region is hash-bound, has complete
  Chinese/English pair coverage, and has zero unmatched Chinese labels.
- Layout: zero detected or visually observed text overlaps; zero clipping; no text below minimum font size.
- Typography: each page has one rendered font family, size, and weight for each
  of `major_title`, `minor_title`, and `body`; dense content reduces the full
  group uniformly.
- Image-layout fallback: every placement adjustment follows a recorded fit
  failure, preserves aspect ratio and exact source content, and has zero changes
  outside approved original/target regions.
- Image review: every page and every image region reviewed; clear logo, header, footer, screenshot, table, diagram text, icon, and mixed-color instruction translated or explicitly preserved.

`passed: true` is necessary but not sufficient if the review evidence is stale or dishonest. Any build change invalidates the previous visual review.
The verifier must reject a visual-review report whose `candidate_sha256` does
not equal the exact output PDF.

The verifier also derives automatic gates: the number of manifest `source_crop` runs must equal the number of build-report provenance records; every record must contain valid source/output boxes, source page, alt description, and a 64-character pixel SHA-256; every manifest block with multiple text-run colors must be reported as mixed-color rendered.
