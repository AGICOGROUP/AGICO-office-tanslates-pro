# PowerPoint lightweight manifest schema

The UTF-8 manifest stores source identity, target language, native text occurrences, reusable
translation units, unique image groups.

Every native occurrence retains its source text, translation-unit ID, slide, shape, paragraph,
role, context, and protected tokens. Every translation unit retains source text, translation,
context, protected tokens, and occurrence count.

Image text follows only [GPT image editing](../../../references/image-translation.md).
Historical overlay records are not accepted as a method for new translations. Each image group uses
one `decision`: `skip_target` (the image already carries the target language), `skip_unclear`
(genuinely unreadable, with a specific reason), or `localized` (the image was edited and is
re-inserted by the replacement writer). Readable untranslated
labels stay pending until edited and inserted; retention needs a specific reason.

A `localized` group records the approved edit in `replacement_path` (absolute, existing file) and
`replacement_sha256`, plus `source_pixel_width` and `source_pixel_height`. The writer fits the edit to
those exact source dimensions and exchanges only the group's `media_paths`, so the picture shape and
every unrelated part stay unchanged. Never record a decision for an image that was not actually
edited and written.

Each embedded object uses one `status`:

- `preserved_untranslated`: default; retain its binary content and preview image unchanged, emit a warning, and continue.
- `pending_native_handler`: use only when the user explicitly requests translation inside the object; delivery remains blocked.
- `translated`: the requested native-object translation completed successfully.

A removed stale preview keeps no entry. No status describes an object that no longer ships, so delete
the entry and record it in the job's `baseline-amendment.json` through
`scripts/ppt_repairs.py amend-baseline`. Leaving it as `preserved_untranslated` warns about content that
is gone; `pending_native_handler` would block a delivery that is in fact complete. Remove an object only
when its legacy preview paints source-language artwork over an already translated slide; keep and
disclose the object when its preview is the slide's own content.
