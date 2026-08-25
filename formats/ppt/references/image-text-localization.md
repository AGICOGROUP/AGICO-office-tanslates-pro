# PowerPoint image-text localization

## Screen unique media only

Use `inventory.json.image_groups`. Review each SHA-256 group once and apply the decision to all
recorded slide/shape occurrences. Skip the image workflow entirely when no media groups exist.

- `retain`: logo, photograph, no source-language text, or text that must remain unchanged.
- `localize`: clear source-language labels that the user expects translated.
- `manual_review`: uncertain reading or unsafe repair area.

Do not export and review identical image occurrences separately.

## Localization method

1. Prefer native PowerPoint text when it exists.
2. On a verified uniform semantic-free background, remove only the source glyph region with
   `scripts/make_text_patch.py` and add a transparent editable text box.
3. Where text touches linework, borders, gradients, texture, arrows, or equipment, use a lossless
   local repair patch that restores every non-text pixel.
4. Preserve unsafe regions and record manual review instead of guessing.

Preserve crop, aspect ratio, anchors, z-order, numbers, units, tags, arrows, process lines, symbols,
equipment, and flow direction. Require zero changed pixels outside approved source-text masks.
