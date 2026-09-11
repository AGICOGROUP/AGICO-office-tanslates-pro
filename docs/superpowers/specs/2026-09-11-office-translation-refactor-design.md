# Office translation architecture

Approved objective: improve professional translation and layout fidelity, shorten translation time, tolerate recoverable failures and reduce unnecessary errors. This replaces the previous minimal-change constraint. Keep source files immutable and preserve technical meaning. No new service, model API, dependency installation or automatic external sending.

## Decision

Use a shared Python task layer with format-specific native writers. Keeping three independent task protocols perpetuates retries and context loss; rebuilding every format in one document model risks losing native objects. Share decisions, batching and checkpoints, but retain OOXML-specific location and formatting logic.

## Translation task contract

`scripts/translation_core.py` provides atomic JSON persistence, canonical content fingerprints, compact worklists, bounded batches and partial decision merging. A failed or missing decision remains pending with an actionable reason; successful decisions are retained. Reject foreign IDs and changed source identity. Normalize only unambiguous equivalent representations, never technical meaning. Preserve source line/tab boundaries. Glossary entries are guidance with context, not blind replacement. No cross-document translation cache is enabled by default.

Word units become location-aware and context-aware instead of using source text as a global replacement key. Legacy manifests continue to work. Worklists expose surrounding text and locations for terminology decisions; repeated text may receive different translations in different contexts.

## Native writers

Excel monolingual output patches text and affected row layout in the original ZIP. Preserve formulas, chart parts, drawings, comments, external relationships and unknown parts. Retain operational strings that formulas reference and disclose untranslated complex objects. Bilingual row reconstruction remains a separate, explicitly limited writer. Validate changed cells and unchanged package parts without importing/exporting the whole workbook.

PowerPoint writes editable image overlays through OOXML in the same atomic pass as native text; Office is used for final rendering, not required merely to write text boxes. Preserve host image bytes. Verify text and geometry, and leave an existing output intact on write failure. Preserve unsupported complex text parts with exact warnings rather than rejecting the entire deck; do not claim these parts were translated.

## Workflow and recovery

`scripts/office_pipeline.py prepare|merge|finalize|status` is the common task interface. Existing adapter commands remain compatible. Preparation resumes identical jobs without replacing decisions. Finalization fingerprints source, decisions and output before reusing completed work. Invalid translation decisions return a repair worklist; missing Office rendering produces a disclosed warning after static checks, while detected damage still blocks delivery.

## Verification

Behavioral fixtures cover partial batches, corrected retries, source mutation, contextual duplicate Word text, rich XLSX strings and formula preservation, chart/image preservation, native PPT overlays and atomic failure. Run existing regressions and compare generated representative workbook timings before/after; report measured processing time separately from human/model translation time. Do not claim total translation quality is proved by unit tests.
