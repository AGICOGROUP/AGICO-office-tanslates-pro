# Quality gates

## Translation

- Manifest coverage is 100%.
- No blank target fields exist.
- Target fields contain no unexpected CJK characters.
- Terminology matches the job glossary.
- Every source match from `references/cement-terminology.md` uses the selected
  table translation; model-generated terminology is allowed only for misses.
- Numbers, units, model codes, standards, URLs, and warning levels are preserved.
- Tables, lists, cross-references, headings, captions, and repeated UI labels are
  all translated.

## Structure

- Page count, MediaBox/CropBox dimensions, and rotation match the source.
- Images, small diagrams, buttons, arrows, bullets, and background graphics
  remain at their original positions unless a validated fit-failure adjustment
  moves or proportionally shrinks a source image into verified whitespace.
- If source text is selectable/copyable, translated text is also
  selectable/copyable and the output has native text-show operations.
- Native-text pages are not replaced by full-page raster images.
- Original source text does not survive invisibly under translated overlays.
- Image-label translations are embedded PDF text, not burned into low-resolution
  diagrams.
- Pages outside approved image edits have identical content streams.
- Flattened mode is forbidden in this native/mixed route.

## Visual

- Render every page after the final edit.
- Check a contact sheet for all pages.
- Require `unreviewed_images: 0`; every original XObject, logo, and icon has an
  explicit review decision.
- Require `untranslated_clear_image_labels: 0`.
- Require `logo_review_complete: true`.
- Require `header_footer_high_resolution_review_complete: true`.
- Require `text_overlap_failures: []`; any detected or visible overlap blocks
  delivery.
- Inspect dense tables, warnings, diagrams, screenshots, covers, contents,
  headers, footers, and the final page at full size.
- Mixed text colors and colored UI labels match the source.
- Table rules survive and text stays inside the correct cell.
- Same-level headings and body roles use consistent size and weight.
- Require each page typography group's target weight to match the dominant
  corresponding source evidence. Preserve exceptional emphasis as `special`
  runs; numbering and heading roles may not invent bold.
- Require header/footer source-size and visual-weight parity.
- Require no native body paragraph below `max(9.5 pt, 60% of source size)`;
  translation tightening is mandatory before a smaller fallback is allowed.
- Source-centered text remains centered within tolerance; wide symmetric body
  lines are not misclassified as titles.
- Each reconstructed paragraph uses one fitted font size across all lines.
- Heading/body/table roles are classified from source typography and reading
  structure, not from absolute font size alone.
- Body text does not intersect protected image geometry; synthetic continuation
  slots through images are forbidden.
- Every table cell is rendered once after cross-cell fragments are segmented
  and aggregated; exact line metrics must keep all text inside the cell.
- Reject clipped, overlapping, missing, garbled, invisible, or low-contrast text.
- Use vision/OCR on image-heavy pages to find source-language residue.
- Every clear source-language label in embedded images is translated unless it
  belongs to a strictly proven complete bilingual image preserved unchanged.
- Reject `preserve_confirm` for clear informational captions or readable labels;
  confirmed preservation requires an allowed `preserve_reason` for unreadable,
  logo/seal, signature/stamp, or protected legal-document content.
- A preserved bilingual image has complete Chinese/English pair evidence,
  zero unmatched Chinese labels, and an unchanged original asset hash.
- Every newly translated image label is extractable/selectable from the final
  PDF; unchanged bilingual assets are exempt.
- For engineering diagrams, pixels outside approved text regions are identical
  to the source and process/structure lines are not blurred or covered.
- Every text-bearing image has an explicit source type and localization method.
- Difference images and 50% alpha overlays are generated and reviewed for every
  modified image.
- Declared engineering-line anchors pass continuity checks; ambiguous topology
  is preserved and recorded as `[CONFIRM]` rather than invented.
- Generative image editing, when required, produces only a local text-free clean
  base; final English remains embedded PDF vector text.
- Reject opaque white blocks that hide any drawing content.
- Within each page, major titles, minor titles, and body text each have one
  verified font family, size, and weight. Any space-driven body reduction is
  applied uniformly to the full body group.
- Image placement changes require a recorded readable-size fit failure,
  unchanged aspect ratio, approved whitespace at the vacated region, and zero
  collisions or unapproved changes.
- Numbered section depth controls heading hierarchy. Decimal measurements and
  punctuated prose cannot become headings, and wrapped heading continuations
  cannot fall back to body styling.

## Evidence

The final QA report must include:

- source and output SHA-256, plus a visual-review candidate SHA-256 equal to the
  exact reviewed output;
- page count and geometry comparison;
- translated block count and coverage;
- extractable source-language residue count and pages;
- pages requiring image-text review;
- selectable-text page coverage and representative copy/paste checks;
- approved image-text regions and unexpected pixel-change counts;
- fallback font fitting and critical role-scale violations;
- source/target bold mismatches, header/footer size mismatches, and body-floor
  violations;
- protected-anchor and restored-character counts;
- visual-review status and corrected page list.
- unreviewed-image count, untranslated clear image-label count, logo-review
  status, header/footer high-resolution review status, and overlap failures.
- image-route coverage, translated/preserved/confirm counts, unreported-confirm
  count, structural-review status, difference-review status, and anchored-line
  failures.

Automated checks do not replace visual review. Do not use
`--visual-review-complete` until every page has actually been reviewed.
