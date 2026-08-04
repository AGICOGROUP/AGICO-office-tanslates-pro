---
name: translate-office-files
description: Use when translating uploaded Microsoft Office files in Word (.doc/.docx), Excel (.xls/.xlsx/.xlsm), or PowerPoint (.ppt/.pptx) formats, especially cement-industry documents whose terminology, editable structure, formulas, images, and layout must be preserved.
---

# Translate Office Files

Route each uploaded Office document to exactly one professional translation adapter. Preserve the source and produce a separate translated artifact.

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

Do not route by user wording or extension alone. For a legacy CFB file, require a confirmed CFB signature and let the selected adapter perform safe conversion.

## Shared translation contract

- Hash and preserve the uploaded source. Work on a copy and never overwrite the original.
- Read `references/水泥专业名词中英对照.md` before translating. Apply exact full-phrase matches first, then the longest valid listed term, then professional contextual translation.
- Preserve numbers, formulas, units, model codes, standards, URLs, identifiers, line breaks, and other protected tokens.
- Keep native text editable and selectable. Review text in shapes, charts, headers, footers, comments, notes, and embedded images.
- Preserve formatting, layout, object geometry, relationships, media, and format-specific structure unless a documented local repair is necessary.
- Reopen and render the complete output with the selected adapter's required tool. Reject missing text, unexpected Chinese, clipping, overlap, corruption, or unapproved structural change.

Deliver only the translated file and a concise verification summary after every adapter gate passes.
