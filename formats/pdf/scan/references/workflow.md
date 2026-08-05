# Scan-only PDF workflow

## 1. Prepare

Work from the original PDF. Create `<work>/<stem>-<sha8>/` with `extract/`, `manifest/`, `output/`, `review/`, and `qa/`. Keep the source immutable.

```powershell
python scripts/classify_pdf.py --source "input.pdf"
python scripts/extract_scan.py --source "input.pdf" --pages all --output "job/extract" --dpi 400
python scripts/make_manifest_template.py --extraction "job/extract/extraction-report.json" --output "job/manifest/translation-manifest.json"
```

## 2. OCR inventory and translation

Use both 1x and 3x OCR results merged by geometry. Visually compare the 400-DPI render because OCR can split, merge, hallucinate, or miss text. Every clear source label belongs in the manifest, including text in diagrams, tables, photos, screenshots, seals, logos, headers, footers, and rotated regions.

Group OCR lines into semantic blocks before translation. Preserve numbers, units, model names, standards, URLs, emails, and trademarks exactly unless localization is explicitly required. Build a document-level glossary before translating repeated technical terms. Translate meaning, not OCR noise.

Before translating a diagram, inventory all clear Chinese labels and their
nearby English counterparts. Preserve the diagram as `bilingual_complete` only
when every Chinese label is paired. Some English on the image is insufficient;
translate every unmatched Chinese label.

## 3. Choose cleanup geometry

The default is tight glyph-only cleanup:

- Uniform background: use a clean box only 1–3 pixels beyond the glyph envelope.
- Table cells: clean glyphs, not the whole cell. If a rule crosses text, clean the smallest necessary interval and rebuild that verified segment with `vector_lines`.
- Leaders or dotted lines: leave dots outside the English text box intact; rebuild only the verified interrupted segment.
- Engineering/process diagrams: preserve pipes, arrows, wires, beams, borders, symbols, and color coding. Never regenerate the diagram. Use local sampling only when the surrounding region is genuinely uniform.
- Photographs/UI/screenshots: do not synthesize unknown background. If text sits on a nonuniform texture and a clean removal cannot be proved, perform pixel-local clone/inpaint outside these generic scripts, then verify the protected structure at high zoom.
- Logos: translate the readable wording while preserving artwork. A trademark or brand name may use `preserve_confirm` when translation would be incorrect.

### Icon routing and mixed-color text

Classify each icon before cleanup:

1. **Outside the glyph cleanup area:** leave it untouched in the raster base. This is preferred.
2. **Inside an unavoidable cleanup area:** add a `rich_lines` `source_crop` run using the exact source-render pixel coordinates. The builder restores those source pixels inline and records their SHA-256 provenance.
3. **Not safely recoverable:** use `preserve_confirm`, describe the issue, and block delivery pending review.

Do not replace a source icon with Unicode, a font glyph, explanatory text, or a similar icon from another library. For lines containing orange commands, blue links, warnings, or other meaningful color changes, use `rich_lines` text runs and preserve each run's RGB color. The concatenated text runs must equal the block `translation`; source-crop runs do not add text.

The `box` is the English text area. The `clean_box` is the source-glyph removal area. They are intentionally separate. Never enlarge `clean_box` merely because English is longer; instead reflow, reduce font within the allowed minimum, or use nearby whitespace.

Plan `major_title`, `minor_title`, and `body` typography once per page. Use one
font, size, and weight for each group. If English still cannot fit at the
readable floor, record the fit failure before using a page `layout_adjustment`.
Try shifting a large image first, then proportional shrink. The old image area
must be verified uniform background and both old and new boxes become approved
difference regions.

## 4. Build

```powershell
python scripts/build_scan.py --manifest "job/manifest/translation-manifest.json" --output "job/output/translated.pdf"
```

The builder hard-fails when complete English cannot fit. It records changed pixels and requires zero changes outside approved cleanup boxes. Optional `vector_lines` are drawn after the cleaned page image and before English text. For every `source_crop` run it records the source page, source box, output box, pixel SHA-256, and alt description in the build report.

## 5. Review and verify

Render the output at 200 DPI for full-page inspection and at 400 DPI for text-adjacent structure, logos, tables, headers, footers, icons, and mixed-color instructions. Compare source/output crops for every translated block. Confirm each `source_crop` against its build-report provenance and verify that no pictogram became text or a similar substitute. Create `visual-review.json` using the contract in `quality-gates.md`.

```powershell
python scripts/verify_scan.py --source "input.pdf" --manifest "job/manifest/translation-manifest.json" --pdf "job/output/translated.pdf" --visual-review "job/review/visual-review.json" --report "job/qa/final-qa.json"
```

If QA fails, correct the smallest affected block and rerun build, render review, and verification. Never reuse stale visual-review evidence after changing the PDF.
