---
name: translate-office-files
description: Use when translating uploaded Word (.doc/.docx), Excel (.xls/.xlsx/.xlsm), PowerPoint (.ppt/.pptx), PDF (.pdf), or static image (.png/.jpg/.jpeg) files whose professional terminology, editable content, graphics, and layout must be preserved.
---

# Translate Office, PDF, and Image Files

Route each uploaded document to exactly one format adapter. Preserve the source and produce a separate translated artifact.

## Route the uploaded file

1. Run `python scripts/route_office_file.py <uploaded-file>` from this Skill directory.
2. Trust the detected container signature before the filename extension.
3. Stop on corrupt, encrypted, ambiguous, unsupported, or extension-mismatched files.
4. Read and follow only the adapter returned in `adapter`:

| Detected format | Adapter |
|---|---|
| Word `.doc` / `.docx` | `formats/word/SKILL.md` |
| Excel `.xls` / `.xlsx` / `.xlsm` | `formats/excel/SKILL.md` |
| PowerPoint `.ppt` / `.pptx` | `formats/ppt/SKILL.md` |
| PDF `.pdf` | `formats/pdf/SKILL.md` |
| Static image `.png` / `.jpg` / `.jpeg` | `formats/image/SKILL.md` |

Do not route by user wording or extension alone. The PDF adapter performs a second signature and content classification before selecting one of its three independent PDF skills. The image adapter wraps a verified static PNG or JPEG as a one-page scan PDF, reuses the scan-PDF workflow, and returns the same image format and dimensions.

## Shared translation contract

- Hash and preserve the uploaded source. Work on a copy and never overwrite the original.
- Read `references/水泥专业名词中英对照.md` before translating. Apply exact full-phrase matches first, then the longest valid listed term, then professional contextual translation.
- Preserve numbers, formulas, units, model codes, standards, URLs, identifiers, line breaks, and other protected tokens.
- Keep native text editable and selectable. Review text in shapes, charts, headers, footers, comments, notes, and embedded images.
- Preserve formatting, layout, object geometry, relationships, media, and format-specific structure unless a documented local repair is necessary.
- Reopen and render the complete output with the selected adapter's required tool. Reject missing text, unexpected Chinese, clipping, overlap, corruption, or unapproved structural change.

Deliver only the translated file and a concise verification summary after every adapter gate passes.
