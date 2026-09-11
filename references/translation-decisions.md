# Translation decisions

## Required execution flow

Read the selected adapter and this reference before translating. Use its documented shared entrypoint:
`prepare` → translate/review a batch → `merge` → repair rejected items → `finalize`.
The documented small-job shortcut (fill the default worklist, then finalize) is valid because finalize
performs merge itself. Complete any adapter-required image or visual review when requested by the
pipeline. After each merge, continue with pending items in the same turn, then finalize and deliver.
A batch boundary or saved progress is not a stopping condition. Pause only for a user interruption
or an actual blocker requiring input/access; report progress without ending the task otherwise.
Resume accepted work; do not restart the whole job to repair individual decisions.

Executors may edit translation decisions in the worklist or a batch JSON, including supported image
decisions. The pipeline owns manifests, source identity, working files, completion flags, stage caches
and verification/delivery reports. Do not hand-edit these artifacts to force completion, clear errors,
or claim review. Translation helpers may produce batch decisions; they must not replace extraction,
native writeback, verification or the supported state transitions. Legacy adapter commands are for
diagnosis, not a way to evade a rejected shared-pipeline decision.

If prepare fails or times out, diagnose the reported failure and rerun prepare with the same job.
Do not merge or finalize incomplete preparation. If a completed prepare lacks the matched glossary,
use the targeted terminology lookup below; do not invent glossary results or completion evidence.
Preserve successful work when translation is interrupted, and leave failed units pending. A workflow defect found
during a test must be repaired in the reusable skill; patching that test's output alone is insufficient.

Deliver only the output returned by a successful finalize, after required reviews and known content
issues are resolved. Use the current report, not a stale delivery flag. Disclose unresolved limitations
allowed by the adapter. Actual linguistic review is the executor's responsibility: adding a boolean
or a generic retention reason does not prove it occurred. These rules apply to helper scripts and
delegated executors as well as the primary executor. User instructions take precedence.

## Translate and review decisions

Use the current model's native translation capability for every batch, with the supplied context and
matched glossary. Do not send document content to third-party translation services, websites, APIs,
local third-party translation engines or browser-based translators. Do not use them for drafts,
fallbacks, retries or terminology lookup. This prohibition applies even when such a service appears
faster or the current model translation is interrupted; resume the pending model batches instead.
All-uppercase text, short labels, TOC entries and repeated headings are language, not automatically
codes. Preserve verified models, standards and units within translated phrases.

Use the Skill's cement-industry reference `水泥专业名词中英对照.md` through the matched
`relevant-glossary.json` subset. If that subset is missing or unavailable, search the shared terminology
file for the batch's ambiguous equipment terms and continue from those matches. Do not fabricate a
completed preparation record or treat missing terminology as approval for unchecked translation. In cement equipment
context, `Fans` means 风机, `Feeders` means 给料机/喂料机 and `Air slides` means 空气输送斜槽;
choose the term for the actual equipment, not a general-language dictionary sense.

Before merging a batch, review its headings, short labels and ambiguous equipment names in context,
and confirm complete thoughts and all lines were translated. Review each unique term/context once;
reuse reviewed wording for matching contexts. Fix the affected units rather than restarting the job.

Read source text and context from the supplied worklist. Submit compact decisions containing the
unchanged top-level `job_identity` and `translation_units` entries with `id` and `translation`;
include `status` and `reason` for explicit retention. `source` is optional: omit it instead of retyping
the English text, tabs or spaces. If included, it must match exactly. For example:
`{"job_identity":"<copy from worklist>","translation_units":[{"id":1,"translation":"译文"}]}`.
Word batches omit neighboring snippets already visible as adjacent units in the same batch; read
those units together. Batch-edge context and style metadata remain available. Preserve technical
tokens and repeated values, but do not insert untranslated prose merely to satisfy a suspected
identifier misclassification; diagnose that specific rejection. A rejection does not request another whole batch: use the returned
IDs and the refreshed worklist to repair only affected entries. Read the JSON readiness result before
finalizing; a successful merge command may still contain rejected decisions.

Fill `translation` with an actual translation. To keep an ambiguous brand, acronym or required source
label unchanged, submit `status: "retain"` and a specific `reason` identifying why it belongs unchanged
in this target document. Do not generate blanket "reviewed" reasons. Obvious numeric codes and units
may remain unchanged without claiming human review. A failed translation request is pending work:
save successful decisions, retry only failures, and never substitute the source as a successful result.

The shared merge checks Chinese-target English-only tab/newline segments, including changed casing or
punctuation. Suspect segments return for translation or explicit retention; checks preserve standard
codes and quantities. This heuristic is not a full language detector, cannot reliably find inline
mixed-language omissions, and does not validate technical meaning. Other language pairs also require
the same model review. `ready`/`deliver`, native opening and zero heuristic findings establish only
their respective checks; never describe them as proof of zero omissions or professional accuracy.

Report limitations actually found, and distinguish translated units, retained identifiers, image/object
text and paragraph occurrences. Do not convert a flagged-unit count into a percentage of pages or text.
