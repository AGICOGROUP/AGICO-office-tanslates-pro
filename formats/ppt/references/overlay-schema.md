# PowerPoint editable image overlay

An `overlay` image decision references one or more editable PowerPoint overlays. Each overlay uses:

- unique `id` and `kind: office_overlay`;
- `localization_mode: bilingual_below`;
- non-empty `source_text` and `translation`;
- normalized `source_region` and a non-overlapping target `region` immediately below it;
- `background.mode: transparent`;
- slide number, host shape ID, stable region ID, and readable text styling.

The host image stays unchanged. `skip_target` and `skip_unclear` create no overlays.
