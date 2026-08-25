---
name: office-translate-pro
description: Use when translating uploaded Word (.doc/.docx), Excel (.xls/.xlsx/.xlsm), PowerPoint (.ppt/.pptx), PDF (.pdf), or static image (.png/.jpg/.jpeg) files whose professional terminology, editable content, graphics, and layout must be preserved.
---

# Office Translate Pro

Route each uploaded file to exactly one format adapter.

## Route the uploaded file

1. Run `python scripts/route_office_file.py <uploaded-file>` from this Skill directory.
2. Trust the detected container signature before the filename extension.
3. Stop on corrupt, encrypted, ambiguous, unsupported, or extension-mismatched files.
4. Read and follow only the adapter returned in `adapter`.

| Detected format | Adapter |
|---|---|
| Word `.doc` / `.docx` | `formats/word/SKILL.md` |
| Excel `.xls` / `.xlsx` / `.xlsm` | `formats/excel/SKILL.md` |
| PowerPoint `.ppt` / `.pptx` | `formats/ppt/SKILL.md` |
| PDF `.pdf` | `formats/pdf/SKILL.md` |
| Static image `.png` / `.jpg` / `.jpeg` | `formats/image/SKILL.md` |

Routing ends immediately after one adapter is selected. Do not read or consider any other format
adapter, do not return to this root router, and do not apply a cross-format workflow. The selected
adapter owns all subsequent processing and delivery rules.

Do not route by user wording or extension alone. The PDF adapter may perform its own PDF-content
subroute after the Office format is already fixed as PDF. The image adapter may use its documented
one-page scan bridge after the format is already fixed as a static image. Neither case reopens the
other Office-format doors.
