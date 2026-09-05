# Translation worklists and batches implementation plan

**Goal:** Implement the user's accepted optimizations 1 and 2 without changing translation, glossary, layout, image review, or final delivery gates.

**Architecture:** Adapter-owned commands use a shared format-neutral JSON batching helper. Word and PPT prepare emit compact pending work; Excel keeps its existing worklist/finalize contract. Results contain job binding plus ID/translation decisions, never regenerated manifests. Successful decisions persist atomically; failed decisions remain retryable.

**Constraints:** Work only in this repository. Preserve unrelated jobs changes. No glossary subset optimization, Office-session optimization, deployment sync, or publishing. No claim of minute-scale savings without end-to-end timing. No cross-adapter routing. Keep source context, stable IDs, protected tokens, image decisions and final checks.

- [x] 1. Add failing tests for compact worklists, stable batch binding, partial responses, failed-item retries, duplicate/unknown/stale IDs, completed-result conflict protection, context, and image preservation.
- [x] 2. Implement shared atomic worklist/batch/result helper and integrate Word/PPT prepare and adapter commands; preserve old direct-manifest commands.
- [x] 3. Integrate Excel batching with its existing worklist, leaving finalize and Office verification intact.
- [x] 4. Update each adapter's SKILL and workflow/CLI documentation with exact commands, response schema, resume and local correction rules.
- [x] 5. Run root, PPT and Excel regression suites; replay existing translations on disposable work copies and compare output content/parts where available. Measure response volume, not an invented elapsed-time benefit.

## Evidence

Word replay: 443 existing translations in 6 batches; all DOCX ZIP part contents equal to the direct-manifest apply output, and static validation passed. Full filled manifest: 114,856 bytes; batch inputs: 54,511 bytes; compact responses: 56,293 bytes. This measures payload volume, not end-to-end time or model-generated translation quality. Artifacts/logs are under `work/batch-verification/`.

Read-only reviewer checked code and recovery instructions. Fixed introduced-separator acceptance and missing retry exports for failed completed-item corrections. Final gates remain required. No live Office render/COM integration was rerun for this text-workflow change; existing Office-dependent tests retain their skip gates.
