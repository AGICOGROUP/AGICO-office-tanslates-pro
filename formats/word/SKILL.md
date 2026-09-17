---
name: office-translate-pro-word
description: Use when translating uploaded Word documents (.doc or .docx), especially technical tables, quotations and specifications whose terminology, editable text, styles, images and layout must be preserved.
---

# Professional Word Translation

Top-level routing is complete. Do not run the root Office router again or read another format adapter.
This adapter does not depend on another Office translation skill.

## Standard task

From this adapter directory, run:

```text
python ../../scripts/office_pipeline.py prepare <source> --job-dir <job> --target-language <language>
python ../../scripts/office_pipeline.py merge --job-dir <job> --decisions <batch.json>
python ../../scripts/office_pipeline.py finalize --job-dir <job> --output <translated.docx>
python ../../scripts/office_pipeline.py status --job-dir <job>
```

Read [translation decisions](../../references/translation-decisions.md), then the job's
`translation-worklist.json` and `relevant-glossary.json`. Read the listed batches with their context,
then submit compact ID/translation decisions with the unchanged `job_identity` as described in that reference.
Merge completed subsets and immediately continue pending batches through finalization and delivery.
Accepted decisions remain saved; only missing or invalid items return with repair reasons. Finalize
also merges the default worklist, so small jobs can omit a separate merge command. Repeated preparation
preserves existing work; use a new job directory for a different source or target language.

## Translation quality

The shared terminology source is `../../references/水泥专业名词中英对照.md`. Use its matched subset,
exact phrases before shorter terms, and returned context/aliases to choose the engineering meaning.
Chinese targets support reverse English lookup. Do not load the complete glossary during ordinary work.

Units include neighboring paragraphs and style context. The same source word can need different
translations in different contexts; writes use locations rather than global string replacement.
Translate complete thoughts rather than formatting runs. Preserve numbers, units, signs, models,
standards, meaningful line breaks and tabs. Protected tokens accept equivalent spacing and full-width
symbols while retaining SI prefix case and repeated values. Retain source text only when appropriate
in the requested output; do not hide untranslated sentences behind a retention decision.

Review each unique embedded image text once, including WMF/EMF diagrams, following
[the shared in-image translation rule](../../references/image-translation.md).
Use GPT image editing as the only method; replace text or add bilingual text at its original location
as requested. Inspect the result using the shared accepted quality criteria; cosmetic redraw
differences alone do not require another generation. Insert the translated image back into the file.
Record and verify source/output pixel dimensions and exact aspect ratio. Never crop, truncate,
downsample or independently stretch the generated image; use equal-size output or proportional
upscaling, with blank padding when necessary to restore the source ratio.
External bilingual legends do not meet this requirement and must not be used as the translation
result. The Word pipeline replaces GPT-localized main-story inline images while preserving their
display dimensions and verifies the resulting package. Unsupported image hosts remain pending;
do not claim that review/retention translates an image or that a standalone trial updated the file.

## Preservation and delivery

Preserve the document formatting; pagination may change. Keep styles, tables, editable objects,
section relationships and the overall visual structure, but allow translation-driven page reflow.
Do not treat pagination differences alone as damage or a reason to block delivery.

Hash and preserve the source. Never overwrite it. `.doc` conversion uses Microsoft Word once to
create a working `.docx`. The writer preserves styles, tables, editable text, namespace mappings and
boundary spaces, and removes unsafe inherited compression from Latin translations. Only changed text
parts are rewritten. Output replacement is atomic.

Finalize checks translated paragraph locations, protected tokens, media bytes and structure. Repair
actual content loss, value changes or malformed output, then resume. Deliver at `next_stage: deliver`.
The legacy `scripts/word_pipeline.py prepare|apply|validate` commands remain for existing jobs and
troubleshooting. `validate --word-native` is optional and non-blocking, reporting diagnostics and
warnings. Deliver without an external PDF conversion or rendering gate. Never hide confirmed damage.
