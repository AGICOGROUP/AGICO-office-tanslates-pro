# PowerPoint lightweight manifest schema

The UTF-8 manifest stores source identity, target language, native text occurrences, reusable
translation units, unique image groups, and editable overlays.

Every native occurrence retains its source text, translation-unit ID, slide, shape, paragraph,
role, context, and protected tokens. Every translation unit retains source text, translation,
context, protected tokens, and occurrence count.

Each unique image group uses exactly one `decision`:

- `skip_target`: target-language text is already visible; `overlay_ids` must be empty.
- `skip_unclear`: text is unclear; `overlay_ids` must be empty.
- `overlay`: clear single-language text; `overlay_ids` must reference editable
  `bilingual_below` overlays and `preserve_source_image` must be true.

Each embedded object uses one `status`:

- `preserved_untranslated`: default; retain its binary content and preview image unchanged, emit a warning, and continue.
- `pending_native_handler`: use only when the user explicitly requests translation inside the object; delivery remains blocked.
- `translated`: the requested native-object translation completed successfully.
