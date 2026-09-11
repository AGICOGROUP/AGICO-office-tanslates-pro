# Office Translation Refactor Implementation Plan

> Execution: use superpowers:subagent-driven-development for independent native writers and local shared-core integration, completing testable batches in this task. The user has authorized the architectural direction and continuous implementation.

**Goal:** improve translation quality, time and recoverability across Word, Excel and PowerPoint.

**Architecture:** shared decision and recovery layer; native OOXML writers retain format-specific geometry and structure. Existing entry points remain compatible.

**Tech Stack:** bundled Python, lxml, existing Node runtime and Microsoft Office diagnostics; no installed dependencies.

**Spec:** `docs/superpowers/specs/2026-09-11-office-translation-refactor-design.md`

## Global constraints

- Source files remain immutable; atomic replacement applies to generated files only.
- Replace superseded production behavior and instructions; do not accumulate contradictory workflows.
- Partial failures preserve accepted work; actual content damage cannot be disguised as success.

## Batch 1: translation decisions and Word context

Files: `scripts/translation_core.py`, Word analyzer/pipeline, `tests/test_translation_core.py`, `tests/test_word_pipeline.py`.

Interfaces: `atomic_json(path, value)`, `fingerprint(value)`, `build_worklist(manifest, format_name, max_chars=12000)`, `merge_decisions(manifest, worklist, format_name) -> (manifest, report)`.

- [x] Write fixtures asserting valid decisions survive incomplete/invalid neighbors, old source IDs cannot overwrite new work, batches stay within budget except indivisible long units.
- [x] Run `python -m unittest discover -s tests -p test_translation_core.py -v` and observe missing implementation.
- [x] Implement shared helpers and map Word/Excel/PPT unit fields at the boundary.
- [x] Change Word writes to `(part, paragraph)` location keys, add context to prepared units and retain legacy manifest mapping.
- [x] Test different translations for identical words in different paragraphs, untouched media and legacy manifests; run root tests and commit batch.

## Batch 2: Excel preservation writer

Files: new Excel OOXML module, existing Excel entry/writer/verification integration, Excel tests.

- [x] Create XLSX fixtures with rich strings, charts, comments, formulas and duplicate shared strings; require all non-target ZIP parts unchanged.
- [x] Observe failing tests, implement monolingual text patching and selective layout adjustment in an atomic ZIP writer.
- [x] Route monolingual apply and verification through the preservation writer; keep bilingual reconstruction separate. Preserve operational formula strings and disclose complex content limits.
- [x] Run Python and Node Excel suites; measure representative workbook apply/verify timings and commit batch.

## Batch 3: PowerPoint native overlays

Files: `formats/ppt/scripts/pptx_ooxml.py`, PPT inspector/pipeline and tests.

- [x] Require editable overlay text/geometry without COM; require failed writes leave prior outputs intact.
- [x] Observe failures, implement overlay shape insertion in the native ZIP writer, remove production COM apply dependency.
- [x] Preserve unsupported text parts with explicit part-level warnings and verify their bytes; retain final native rendering behavior.
- [x] Run PPT tests and native fixture validation; commit batch.

## Batch 4: common entry and delivery

Files: `scripts/office_pipeline.py`, shared core, root/adapter SKILL.md and README, integration tests.

- [x] Test prepare/partial merge/finalize/status plus repeated prepare and finalize without redoing completed work.
- [x] Implement adapter dispatch, compact decisions, source/decision/output fingerprints and actionable repair reports; wire shared layer into the production instructions.
- [x] Replace obsolete workflow claims, document preservation limitations and commands.
- [x] Completed 253 regression cases: 242 passed, 11 existing skips. Scoped review findings were fixed and rechecked. Actual Microsoft Excel native validation and PowerPoint rendering passed on generated fixtures. Final benchmark: 3.291 s baseline versus 1.701 s native for inspect/apply/verify; excludes translation, preparation and Office checking. Commits: 3e433e2 (core), b2c0c15 (workflow), e6ae406 (Excel), afb7da0 (PowerPoint).
