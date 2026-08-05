---
name: route-pdf-translation
description: Use when an uploaded PDF must be classified as native-text, mixed native/raster, or scan-only before professional translation.
---

# Route PDF Translation

Select exactly one of the two independent PDF translation skills. Never merge their workflows.

1. Run `python formats/pdf/scripts/route_pdf_file.py <uploaded-file>` from the repository root.
2. Stop if the report contains an `error` or returns a nonzero exit code.
3. Read and follow only the returned `adapter`. Resolve its relative commands from that adapter's own directory:

| PDF classification | Adapter |
|---|---|
| Native selectable text | `formats/pdf/native/SKILL.md` |
| Mixed selectable text and raster/image text | `formats/pdf/native/SKILL.md` |
| Scan-only or image-only | `formats/pdf/scan/SKILL.md` |

The native adapter preserves existing selectable/copyable text and separately localizes embedded image text. The scan adapter treats each page as an image while preserving all non-text pixels and graphics.

Do not route by extension, filename, or user wording alone. Do not run both adapters on the same input.
