# PowerPoint lightweight manifest schema

The UTF-8 manifest stores source identity, target language, native text occurrences, reusable
translation units, unique image groups.

Every native occurrence retains its source text, translation-unit ID, slide, shape, paragraph,
role, context, and protected tokens. Every translation unit retains source text, translation,
context, protected tokens, and occurrence count.

Image text follows only [GPT image editing](../../../references/image-translation.md).
Historical overlay records are not accepted as a method for new translations. Preserve source
identity and record actual generated-image paths/hashes using the replacement writer schema.
Do not invent a successful decision before that writer is implemented. Readable untranslated
labels stay pending until edited and inserted; retention needs a specific reason.

Each embedded object uses one `status`:

- `preserved_untranslated`: default; retain its binary content and preview image unchanged, emit a warning, and continue.
- `pending_native_handler`: use only when the user explicitly requests translation inside the object; delivery remains blocked.
- `translated`: the requested native-object translation completed successfully.
