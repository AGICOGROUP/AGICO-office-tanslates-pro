# Compact translation work

The Word adapter retains the full glossary, image review, layout adaptations, apply, and final validate rules. Batching is an input/output optimization, not a replacement quality gate.

`prepare` creates the immutable-source manifest and `translation-worklist.json`, a compact index of pending batch files. Read the index and listed files in order, not the full manifest. Preserve the original paragraph order and all supplied context. Carry consistent terminology across batches. The default is at most 80 units or 12,000 source characters per batch; one paragraph is never split. These limits are workload bounds, not semantic boundaries; read neighboring batches when context is ambiguous.

Use the selected adapter's entry point:

```text
python scripts/word_pipeline.py batches --job-dir <job>
python scripts/word_pipeline.py merge --job-dir <job> --responses <responses.json>
python scripts/word_pipeline.py batches --job-dir <job> --ids 12 15
```

Response JSON (Word IDs are numbers; copy the job_id from the batch):

```json
{"job_id":"<batch job_id>","translations":[{"id":12,"translation":"Equipment List"}]}
```

Never repeat source text, paths, hashes, XML locations or the full manifest in a translation response. A response may cover one or several batches. Use JSON files, not task-specific Python scripts. Submit valid portions immediately. `merge` saves successful items atomically, leaves rejected items unchanged, emits `translation-merge-report.json`, and refreshes the pending index. Exit code 2 means some decisions need repair; successful decisions are already saved. Unknown/duplicate IDs or a foreign job_id reject the entire response before mutation.

After interruption, run `batches`; do not rerun `prepare` (it refuses to overwrite an existing manifest). Translate only remaining items. When the latest merge report links `translation-retry.json`, use that index for rejected IDs, including failed corrections to already-completed items; do not use an old retry file absent from the latest report. For a targeted correction, use `--ids`; completed items include `previous_translation`. Return that exact previous_translation with the new translation to explicitly authorize replacement. Conflicting stale responses never silently overwrite completed work. Keep tabs/newlines and protected tokens; merge reports errors per ID. The checks are deterministic fidelity checks, not a semantic translation review.

After all text is merged, perform the same image review, `apply`, and `validate` as before. Text batches do not translate or approve images. For a correction discovered by final review, merge just the affected IDs, then rerun apply and the full final validation. Do not infer delivery readiness from pending_count alone. Existing direct-manifest jobs remain supported.
