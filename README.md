# Office Translate Pro

Professional Office translation with contextual terminology, editable native output and resumable
batches. Word, Excel and PowerPoint retain native writers behind a shared task interface.

```text
python scripts/office_pipeline.py prepare source.docx --job-dir job --target-language en
python scripts/office_pipeline.py batch --job-dir job --output job/batch.json
python scripts/office_pipeline.py merge --job-dir job --decisions batch.json
python scripts/office_pipeline.py finalize --job-dir job --output translated.docx
python scripts/office_pipeline.py status --job-dir job
```

Fill each worklist unit's `translation`, preserving IDs, source text and `job_identity`. Batch files
can contain any subset of `translation_units`; merge saves accepted decisions and returns only items
needing repair. Small jobs can edit the default worklist and finalize directly. Image decisions use
the selected adapter's contract. This skill does not call a translation API: the assistant translates
the worklist using the supplied terminology and context.

Repeated preparation preserves accepted and unsubmitted work. Finalization reuses completed stages
only while source, decisions and output match. Original sources are never overwritten. Existing
adapter commands remain compatible; ordinary jobs should use the shared entry.

- Word writes by paragraph location, supporting contextual translations of identical words.
- Excel monolingual translation patches original OOXML; bilingual paired rows use a separate writer.
- PowerPoint native text and declared picture replacements are written without Office; native rendering remains
  available for final visual review.

The shared entry now exports bounded pending batches with matching terminology (24,000 source/context
characters by default). Each format writes and verifies a private candidate before the entry atomically
publishes the deliverable, preserving any previous output on validation failure. Delivery reports separate
adapter execution time from whole-session elapsed time; elapsed time also includes model work, waits and
user pauses. Use the active image tool's current interface and accept harmless cosmetic differences,
while repairing actual missing labels, changed technical values or unreadable output.

Excel and PowerPoint complex text without a handler is preserved with explicit limitations. Formula-dependent labels may be
retained. Macro-enabled and encrypted inputs remain unsupported. Unit tests establish deterministic
preservation and recovery behavior, not semantic translation quality.

Architecture: [design](docs/superpowers/specs/2026-09-11-office-translation-refactor-design.md),
[plan](docs/superpowers/plans/2026-09-11-office-translation-refactor.md).
