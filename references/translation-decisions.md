# Shared Office workflow

Run commands from the skill root, using the discovered Python interpreter. All three format
pipelines use this interface; their native readers and writers remain independent.

```text
python scripts/office_pipeline.py prepare <source> --job-dir <job> --target-language <language>
python scripts/office_pipeline.py batch --job-dir <job> --output <job>/batch.json
python scripts/office_pipeline.py merge --job-dir <job> --decisions <job>/batch.json
python scripts/office_pipeline.py finalize --job-dir <job> --output <translated-file>
```

## Prepare once, read a bounded batch

Choose a new job directory for a different source, target language, or fresh test. Preparation
extracts native content, conversion when needed, location/context, protected values, unique images
and matched terminology. Existing jobs resume; they are not fresh tests. `.doc`, `.xls` and `.ppt`
convert once, never repeatedly. Keep the supplied original untouched.

`batch` exports the first pending text batch with its relevant terminology and up to four pending
unique images. Translate those `translation_units`, preserve their IDs and `job_identity`, and fill
`translation`. Submit that file to `merge`; repeat `batch` until pending text and images are resolved.
Use `--index N` to read another pending batch without rewriting the master worklist. Batch indices
change after merge: normally continue with index 1. Read `batch.remaining_images` and continue image
decisions even when no text remains. Existing drafts in the worklist are preserved.

The default budget is 24,000 source/context characters, not a requirement to fill that much.
Lower `prepare --batch-chars` for dense multilingual or ambiguous material; increase it only when
the complete context and complete response fit comfortably. Never truncate translations to fit a batch.
For a small job, fill the worklist directly and call finalize; finalize performs merge itself.

## Translate meaning, use terminology as evidence

Use the current model's native translation capability. Do not send document content to third-party translation services,
websites, APIs, local translation engines or browser translators.

All pipelines reference `references/水泥专业名词中英对照.md`, including its aliases and context.
The job's `relevant-glossary.json` and each exported batch contain matched subsets; Chinese targets
also support reverse English lookup. Prefer the longest applicable phrase, but judge it in context:
do not force a glossary typo or a wrong equipment sense. For non-English targets, use the Chinese/English
reference to establish the engineering concept, then translate that concept into the requested language.
User-specified terms take precedence. Search the shared reference for a genuinely ambiguous term;
do not load the whole glossary or invent a successful lookup when one is unavailable.

Read complete paragraphs, table cells and nearby headings. Translate headings and short labels as
language, even when uppercase. Preserve numbers, signs, models, standards, identifiers and engineering
dimensions; `m²`/`m³` and equivalent unit spacing are typography, not unit conversions. Do not silently
correct a suspicious source specification. Review each unique term/context once and reuse only where
meaning matches. Keep real lists, tabs and line boundaries that the native writer relies on.

Compact decisions are also accepted:

```json
{"job_identity":"<from batch>","translation_units":[{"id":1,"translation":"Power 45 kW"}]}
```

To intentionally keep text unchanged, use `status: "retain"` with a specific `reason` such as a
model designation, already-target-language text or a formula-controlled label. Source text is optional
in decisions; if present it must be exact. A retention-only decision can omit `translation`: the
current job resolves the unchanged source from its ID and reason. A retention reason does not make an untranslated sentence
acceptable. Review actual wording and whole multi-line thoughts before merging.

## Repair locally and finish

Merge returns accepted IDs and precise rejections; accepted work persists. `ready: true` means
decisions are ready for writing, not that translation quality has been proven. Repair only rejected
items. If a technical checker rejects correct text, inspect the exact value/token instead of inserting
untranslated prose to please the checker. Fix a reproducible workflow bug in the reusable implementation,
then resume. Do not edit manifests, fingerprints, verification flags or pipeline state to force success.

Finalize writes a private candidate, verifies it, then atomically publishes the requested output.
An unsuccessful finalization leaves any previous deliverable intact. PPT can return `visual-review`:
inspect its current renders and continue with `--visual-review-passed` only after real review.
Do not claim a generated picture was translated inside the document until actual writeback is verified.

Image decisions keep the format's supplied field: Word/Excel use `status` (`retain`, `localized`);
PPT uses `decision` (`skip_target` for already-target/no-text/logo pictures, `skip_unclear` only for
unreadable text, or `localized`). Include the specific reason for retention. Word/Excel localized
decisions also carry actual `source_pixel_width` and `source_pixel_height`; PPT resolves them from
the extracted source. Every localized decision needs the absolute `replacement_path`.

| Finding | Action |
|---|---|
| Missing/wrong meaningful translation, changed technical value, corrupt/opening failure, new formula error, lost content, serious unreadability | Repair affected content before final delivery. |
| Minor spacing, harmless antialiasing, small font differences, Word pagination reflow | Accept useful output; disclose a material limitation without repeating the whole task. |
| No native Office renderer or a bounded timeout, while package/content verification succeeds | Use the format pipeline's supported warning path; state what could not be checked. |
| Unsupported object preserved intact | Identify the actual untranslated scope; do not call it fully translated or convert it into a blanket document failure. |

Deliver the file returned at `next_stage: deliver`, with only relevant limitations. If success remains
impossible after targeted repair, preserve accepted work and any usable candidate, label it incomplete
and explain the specific missing capability; never replace a requested result with a generic error.

`status --job-dir <job>` recovers uncertain progress. Reports distinguish adapter execution time from
`session_elapsed_ms` (prepare-to-delivery wall time, including model work, tools, waits and user pauses).
Do not present adapter milliseconds as total translation time or promise a speedup without measurement.
Repository tests, installation checks and full-suite audits belong to development, not ordinary translation.
