---
name: route-pdf-translation
description: Use when an uploaded PDF must be classified as native-text, mixed native/raster, or scan-only before professional translation, or when the user wants bilingual overlay mode.
---

# Route PDF Translation

Select exactly one of the three independent PDF translation skills. Never merge their workflows.

1. Run `python formats/pdf/scripts/route_pdf_file.py <uploaded-file>` from the repository root.
2. Stop if the report contains an `error` or returns a nonzero exit code.
3. If the user wants the original text kept visible with Chinese translation
   added beside it (bilingual / dual-language / 双语版 / 中英对照), use
   `formats/pdf/bilingual/SKILL.md` regardless of the PDF type — as long as
   the PDF contains selectable native text (native-text or mixed).
4. Otherwise, read and follow only the returned `adapter`. Resolve its
   relative commands from that adapter's own directory:

| PDF classification | Adapter |
|---|---|
| Native selectable text | `formats/pdf/native/SKILL.md` |
| Mixed selectable text and raster/image text | `formats/pdf/native/SKILL.md` |
| Scan-only or image-only | `formats/pdf/scan/SKILL.md` |
| Bilingual overlay (keep original + add translation) | `formats/pdf/bilingual/SKILL.md` |

The native adapter preserves existing selectable/copyable text and separately localizes embedded image text. The scan adapter treats each page as an image while preserving all non-text pixels and graphics. The bilingual overlay adapter keeps all source text unchanged and adds Chinese translations as a new text layer in surrounding whitespace.

Do not route by extension, filename, or user wording alone. Do not run more than one adapter on the same input.
