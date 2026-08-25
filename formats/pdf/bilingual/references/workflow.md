# Bilingual Overlay Workflow

## End-to-end procedure

### Step 1 — Route the PDF

Run the project's standard router to confirm the PDF contains selectable native
text:

```powershell
python formats/pdf/scripts/route_pdf_file.py <source.pdf>
```

If the router returns `scan-only`, the PDF has no selectable text. You have two
options:
- OCR the PDF first to obtain text coordinates, then use this skill with the
  OCR'd layout.
- Use `formats/pdf/scan/SKILL.md` for replacement translation instead.

If the router returns `native-text` or `mixed`, proceed to Step 2.

### Step 2 — Inspect the layout

```powershell
python formats/pdf/bilingual/scripts/inspect_layout.py <source.pdf> --output <job>/layout.json
```

Review the JSON output to understand:
- Page dimensions and orientation (portrait vs. landscape).
- The bounding box of every text span.
- Font families and sizes used in the source.
- Which spans are body text, headers, table headers, table cells, labels.
- Available whitespace around each span (gaps between spans, margins, empty
  cells).

### Step 3 — Build the translation packet

Create `<job>/translations.json` as an array of placement records:

```json
[
  {
    "page": 0,
    "source": "PLANO DE INSPEÇÃO E TESTES",
    "translation": "检验和试验计划",
    "x": 227.2,
    "y": 106,
    "fontsize": 7
  },
  {
    "page": 1,
    "source": "Ensaio de tração",
    "translation": "拉伸试验",
    "x": 171.1,
    "y": 296,
    "fontsize": 6
  }
]
```

#### How to choose coordinates

For each source span, examine its bbox `[x0, y0, x1, y1]` and find the nearest
whitespace:

1. **Right side**: if there is a gap between `x1` and the next column border or
   the right margin, place the translation starting at `x = x1 + 5`.
2. **Below**: if the row has vertical space below `y1` before the next row,
   place at `x = x0`, `y = y1 + 2`.
3. **Adjacent empty cell**: for table layouts with empty columns, place inside
   the empty cell's bbox.
4. **Margin footnote**: if no in-cell space exists, place a numbered marker
   next to the source and the full translation in the page margin.

The `x, y` in the record are the top-left corner of the translation text (in
PDF points, origin top-left, y increases downward).

#### How to choose font size

- Title translations: 80–100% of source title size.
- Body text: 70–90% of source body size.
- Table headers: 70–85% of source header size.
- Table cell content: 60–80% of source cell size.
- Minimum readable size: 5pt. If text doesn't fit at 5pt, shorten the
  translation wording.

#### How to choose max_width

Set `max_width` when the available horizontal space is limited (e.g., a narrow
table column). The script auto-wraps CJK text character-by-character to stay
within this width. Leave `max_width` unset for single-line labels in open
whitespace.

### Step 4 — Apply the overlay

```powershell
python formats/pdf/bilingual/scripts/bilingual_overlay.py `
  <source.pdf> `
  --translations <job>/translations.json `
  --output <job>/bilingual-output.pdf `
  --font-file C:\Windows\Fonts\simhei.ttf
```

### Step 5 — Render and verify

Render every page to a PNG at 2× zoom:

```powershell
python -c "import fitz; d=fitz.open('<job>/bilingual-output.pdf'); [p.get_pixmap(matrix=fitz.Matrix(2,2)).save(f'<job>/preview_{i+1}.png') for i,p in enumerate(d)]"
```

Inspect each rendered page for:
- Source text unchanged and selectable.
- Chinese translations readable and correctly placed.
- No overlap with source text, borders, or images.
- No missing glyphs (tofu boxes).
- Consistent font sizes within each role group.

### Step 6 — Iterate if needed

If a translation overlaps or doesn't fit:
1. Adjust the `x`, `y`, `fontsize`, or `max_width` in `translations.json`.
2. Re-run Step 4.
3. Re-render and verify again.

The source PDF is never modified, so iteration is safe and fast.
