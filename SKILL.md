---
name: office-translate-pro
description: Use when translating uploaded Word (.doc/.docx), Excel (.xls/.xlsx), or PowerPoint (.ppt/.pptx) files whose professional terminology, editable content, graphics, and layout must be preserved.
---

# Office Translate Pro

Route each uploaded file to exactly one format adapter.

All adapters share `references/水泥专业名词中英对照.md`; do not copy, reinstall or validate the
whole repository during an ordinary translation. Read the selected adapter and the references it
requires. The selected adapter's workflow and linked translation-decision rules are required for all
executors and helper scripts; do not replace them with an improvised workflow or hand-edited success
state. Translate only with the current model's native capability and the matched cement terminology subset;
never send document content to a third-party translation service, website, API, local translation
engine or browser translator. Deliver when that workflow completes and its required reviews are performed. Gate on concrete
content loss, technical-value damage, unreadable output or serious layout defects, not cosmetic
imperfection or administrative metadata. Disclose minor limitations with usable output; do not add
repeat checks or approval steps without a specific unresolved risk. Development tests
and installation work are separate tasks. Runtime paths should come from the workspace dependencies,
not a different machine's saved paths.

## Route the uploaded file

1. Run `python scripts/route_office_file.py <uploaded-file>` from this Skill directory.
2. Route strictly by the filename extension. Do not inspect or override routing from ZIP, CFB, or OOXML signatures.
3. Stop only when the file is missing or its extension is unsupported.
4. Read and follow only the adapter returned in `adapter`.

| Detected format | Adapter |
|---|---|
| Word `.doc` / `.docx` | `formats/word/SKILL.md` |
| Excel `.xls` / `.xlsx` | `formats/excel/SKILL.md` |
| PowerPoint `.ppt` / `.pptx` | `formats/ppt/SKILL.md` |

Routing ends immediately after one adapter is selected. Do not read or consider any other format
adapter, do not return to this root router, and do not apply a cross-format workflow. The selected
adapter owns all subsequent processing and delivery rules.

Macro-enabled Office files (`.docm`, `.xlsm`, `.pptm`) are rejected before any Office application
opens them. This skill does not execute, preserve, or rewrite VBA.
