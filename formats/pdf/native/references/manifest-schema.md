# Translation manifest schema v2

`manifest.json` is UTF-8 JSON. Each page records geometry, detected table cells,
and stable translation blocks.

Each block contains:

- `id`: stable `pNNNN-bNNNN` identifier
- `bbox`: source coordinates `[x0, top, x1, bottom]`
- `source_text`: visible source text
- `translation`: model-produced target text
- `characters`: per-character text, bounding box, font, size, color, and
  translatable/protected flags
- `runs`: contiguous mixed-style spans
- `lines`: line boxes, characters, runs, and table-cell segments
- `role`: document-level typography role
- `style`: source font, source size, role size, color, weight, alignment, and
  rotation
- optional `source_bold_override`: reviewed source-render evidence used only
  when the PDF font metadata does not expose the visible weight
- optional `render_translation_override`: meaning-preserving concise wording
  used to satisfy a verified layout/readability constraint without changing the
  stable source block or its full translation record
- optional `heading_continuation`: reviewed evidence that a short block is the
  wrapped continuation of the immediately preceding numbered heading

Rules:

- Never change IDs, source text, page geometry, or source hash after translation
  begins.
- Only write translated prose to `translation`.
- Never use `source_bold_override` as a semantic-title shortcut. It requires a
  direct source-render comparison for that exact block.
- Use `render_translation_override` only after normal paragraph fitting fails at
  the readable source-relative font floor.
- Use `heading_continuation: true` when source extraction splits one logical
  heading across blocks and automatic lowercase-continuation evidence is absent.
- Keep product names, codes, units, formulas, URLs, and UI tokens intact.
- A batch must retain the same block IDs and source text as the manifest.
- `merge` rejects unknown IDs, changed source text, blank targets, and unexpected
  source-language residue.
- Schema v1 manifests remain usable during `apply`: the pipeline enriches them
  from the verified source PDF before rendering.
