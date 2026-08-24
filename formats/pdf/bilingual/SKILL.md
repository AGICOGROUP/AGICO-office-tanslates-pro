---
name: translate-pdf-bilingual-overlay
description: >-
  Use when the user wants to keep the original text visible and add Chinese
  translation beside it in the surrounding whitespace, producing a bilingual
  dual-language PDF. Triggers on phrases like "保留原文加翻译", "双语版",
  "bilingual", "中英对照", "原文后面加中文", "在空白处加翻译",
  "dual-language PDF". Do NOT use this skill when the user wants the original
  text replaced by translation — for replacement use the native or scan adapter
  instead. This skill overlays translation as a new text layer while preserving
  every source pixel, text block, table grid, image, and graphic unchanged.
---

# Bilingual Overlay PDF Translation

## Purpose

Produce a bilingual PDF where the source-language original remains fully
visible and selectable, and the Chinese translation is placed beside it in
available whitespace. This is fundamentally different from replacement
translation: nothing in the source is removed, overwritten, or flattened.

Use this skill when the user explicitly wants both languages visible
side by side in the same document.

## When to use this skill vs. the native/scan adapters

| User intent | Adapter |
|---|---|
| Replace source text with translation | `formats/pdf/native/SKILL.md` or `formats/pdf/scan/SKILL.md` |
| Keep source text, add translation beside it | **this skill** |

Never run this skill and a replacement adapter on the same output. The two
goals are mutually exclusive: replacement adapters remove source text
operators; this skill preserves them.

## Prerequisites

- PyMuPDF (`fitz`) 1.24+ installed.
- A CJK TrueType font available on the system. The skill defaults to
  `C:\Windows\Fonts\simhei.ttf` (SimHei / 黑体). Override via `--font-file`.
  `simsun.ttc` and `msyh.ttc` also work.
- Source PDF must contain selectable native text. For scan-only PDFs, run OCR
  first to obtain text coordinates, then use this skill with the OCR'd layout.

## Workflow

### 1. Inspect the source layout

Run the layout inspector to extract every text span with its bounding box,
font, and size:

```powershell
python formats/pdf/bilingual/scripts/inspect_layout.py <source.pdf> --output <job>/layout.json
```

Review the JSON output. Each entry contains `page`, `bbox` (x0, y0, x1, y1),
`text`, `font`, and `size`. Identify which spans need translation and note the
available whitespace around each one (gap to the next span, margin, or empty
table cell).

### 2. Build the translation packet

Create a translations JSON file mapping each text span to its Chinese
translation and the coordinates where the translation should be placed:

```json
[
  {
    "page": 0,
    "source": "PLANO DE INSPEÇÃO E TESTES",
    "translation": "检验和试验计划",
    "x": 227.2,
    "y": 106,
    "fontsize": 7
  }
]
```

- `x`, `y` — top-left point where the Chinese text begins (in PDF points,
  origin top-left, y-down).
- `fontsize` — override per-block; omit to use the default (6.8).
- Optional fields: `max_width` (auto-wrap threshold), `align` (`left` |
  `center` | `right`), `color` (RGB 0–1 tuple).

Translate every visible source-language block: body text, table headers,
table cells, headers, footers, labels, abbreviations, and revision history.
Translate by engineering context, not word-by-word. Preserve numbers, units,
standards, model codes, and formulas untranslated.

### 3. Apply the bilingual overlay

```powershell
python formats/pdf/bilingual/scripts/bilingual_overlay.py `
  <source.pdf> `
  --translations <job>/translations.json `
  --output <job>/bilingual-output.pdf `
  --font-file <path-to-cjk-font>
```

The script:
- Opens the source PDF without modifying any existing content stream.
- Inserts the CJK font on every page.
- Places each translation as a new selectable text layer at the specified
  coordinates.
- Auto-wraps text that exceeds `max_width`.
- Saves with deflate compression and garbage collection.

### 4. Verify the output

Render every page to an image and visually inspect:

```powershell
python -c "import fitz; d=fitz.open('<job>/bilingual-output.pdf'); [p.get_pixmap(matrix=fitz.Matrix(2,2)).save(f'<job>/preview_{i+1}.png') for i,p in enumerate(d)]"
```

Check each page for:
- Source text is unchanged and still selectable.
- Chinese translations are readable and correctly placed in whitespace.
- No translation overlaps source text, table borders, or images.
- No clipping or missing glyphs (tofu boxes □).
- Font sizes are consistent within each role group (headers, body, labels).

## Translation placement guidelines

Place Chinese translations using these priorities, in order:

1. **Right of the source span** — when there is horizontal whitespace to the
   right of the original text. Use a slightly smaller font size (70–90% of
   source) so the translation fits without crowding.
2. **Below the source span** — when vertical whitespace exists in the same
   cell or margin area. Use 60–80% of source size.
3. **In an adjacent empty cell** — for tables with empty columns or rows.
4. **In the page margin** — when no in-cell space is available, place a
   numbered footnote in the margin and link it to the source block.

Never place translation text on top of source text, on table borders, on
images, or on vector graphics lines.

## Font and color conventions

- **Font**: SimHei (黑体) by default for readability at small sizes. Use
  SimSun (宋体) for body text that must match a serif source.
- **Color**: Dark blue-gray `(0.15, 0.25, 0.55)` to visually distinguish
  translation from source black text without being intrusive.
- **Size hierarchy**: Match source roles — title translations use the largest
  size, body text smaller, table cell labels smallest. Keep one size per role
  group per page.

## Acceptance gates

Deliver only when every gate passes:

1. Source text remains visible, selectable, and unchanged on every page.
2. Every visible source-language block has a Chinese translation placed in
   nearby whitespace.
3. No translation overlaps source text, table borders, images, or vector
   graphics.
4. Page count, page size, rotation, and all non-text pixels match the source.
5. Chinese text uses an embedded CJK font — no missing-glyph boxes.
6. Font sizes are consistent within each role group on each page.
7. Numbers, units, standards, and model codes are preserved untranslated.
8. Rendered preview of every page passes visual inspection.

## Failure policy

- If a translation does not fit in available whitespace, reduce font size
  (floor: 5pt) or shorten the translation wording before relocating.
- If no whitespace exists near a source block, place a numbered footnote in
  the page margin.
- Never delete or modify source content to make room for translations.
- Never generate translations for unreadable text — record it as a
  `[CONFIRM]` item.
