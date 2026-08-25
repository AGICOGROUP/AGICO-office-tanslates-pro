#!/usr/bin/env python3
"""Bilingual overlay: add Chinese translations beside source text in a PDF.

Reads a translations JSON file (array of placement records) and overlays each
translation as a new selectable text layer on the source PDF. The source
content streams, images, graphics, and existing text are never modified.

Each translation record:
  {
    "page": 0,                      # 0-based page index
    "source": "PLANO DE...",        # original text (for reference, not rendered)
    "translation": "检验和...",     # Chinese text to insert
    "x": 227.2,                     # top-left x in PDF points
    "y": 106.0,                     # top-left y in PDF points (y-down)
    "fontsize": 7,                  # optional, default 6.8
    "max_width": 120,               # optional auto-wrap threshold in points
    "align": "left",                # optional: left|center|right
    "color": [0.15, 0.25, 0.55]     # optional RGB 0-1
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf as fitz

# Defaults
DEFAULT_FONT_SIZE = 6.8
DEFAULT_COLOR = (0.15, 0.25, 0.55)  # dark blue-gray
DEFAULT_FONT_NAME = "SimHei"
DEFAULT_FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"

# Global font cache (fitz.Font objects are expensive to create)
_font_cache: dict[str, fitz.Font] = {}


def get_font(fontfile: str) -> fitz.Font:
    """Return a cached fitz.Font for the given file path."""
    if fontfile not in _font_cache:
        _font_cache[fontfile] = fitz.Font(fontfile=fontfile)
    return _font_cache[fontfile]


def text_width(text: str, fontfile: str, fontsize: float) -> float:
    """Measure the rendered width of text at the given font size."""
    font = get_font(fontfile)
    return font.text_length(text, fontsize=fontsize)


def wrap_cjk(text: str, fontfile: str, fontsize: float, max_width: float) -> list[str]:
    """Wrap text to fit within max_width, character by character.

    Works for CJK text where any character can be a break point. For
    mixed Latin/CJK, breaks at the last character that still fits.
    """
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if text_width(candidate, fontfile, fontsize) > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def place_translation(
    page: fitz.Page,
    text: str,
    x: float,
    y: float,
    fontsize: float = DEFAULT_FONT_SIZE,
    color: tuple = DEFAULT_COLOR,
    max_width: float | None = None,
    align: str = "left",
    fontname: str = DEFAULT_FONT_NAME,
    fontfile: str = DEFAULT_FONT_PATH,
) -> float:
    """Place one translation block on the page. Returns total height used."""
    if not text:
        return 0.0

    page.insert_font(fontname=fontname, fontfile=fontfile)
    tw = text_width(text, fontfile, fontsize)

    if max_width and tw > max_width:
        lines = wrap_cjk(text, fontfile, fontsize, max_width)
    else:
        lines = [text]

    line_height = fontsize * 1.35
    total_height = len(lines) * line_height

    for i, line in enumerate(lines):
        ly = y + i * line_height
        lx = x
        if align == "center":
            lx = x - text_width(line, fontfile, fontsize) / 2
        elif align == "right":
            lx = x - text_width(line, fontfile, fontsize)

        page.insert_text(
            (lx, ly + fontsize),  # baseline offset
            line,
            fontname=fontname,
            fontfile=fontfile,
            fontsize=fontsize,
            color=color,
            overlay=True,
        )

    return total_height


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source PDF file")
    parser.add_argument(
        "--translations", "-t", type=Path, required=True,
        help="JSON file with translation placement records",
    )
    parser.add_argument(
        "--output", "-o", type=Path, required=True,
        help="Output bilingual PDF path",
    )
    parser.add_argument(
        "--font-file", type=Path, default=Path(DEFAULT_FONT_PATH),
        help=f"CJK font file (default: {DEFAULT_FONT_PATH})",
    )
    parser.add_argument(
        "--font-name", default=DEFAULT_FONT_NAME,
        help=f"Font name registered in PDF (default: {DEFAULT_FONT_NAME})",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"Error: source not found: {args.source}", file=sys.stderr)
        return 2
    if not args.translations.is_file():
        print(f"Error: translations file not found: {args.translations}", file=sys.stderr)
        return 2
    if not args.font_file.is_file():
        print(f"Error: font file not found: {args.font_file}", file=sys.stderr)
        return 2

    records = json.loads(args.translations.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        print("Error: translations file must be a JSON array", file=sys.stderr)
        return 2

    # Group records by page for efficient processing
    by_page: dict[int, list[dict]] = {}
    for rec in records:
        page_idx = rec.get("page", 0)
        by_page.setdefault(page_idx, []).append(rec)

    doc = fitz.open(args.source)

    # Validate page indices
    for page_idx in by_page:
        if page_idx < 0 or page_idx >= doc.page_count:
            print(f"Error: page index {page_idx} out of range (0-{doc.page_count - 1})", file=sys.stderr)
            doc.close()
            return 2

    fontfile = str(args.font_file)
    fontname = args.font_name

    for page_idx, page_records in by_page.items():
        page = doc[page_idx]
        page.insert_font(fontname=fontname, fontfile=fontfile)

        for rec in page_records:
            translation = rec.get("translation", "")
            if not translation:
                continue

            place_translation(
                page=page,
                text=translation,
                x=float(rec.get("x", 0)),
                y=float(rec.get("y", 0)),
                fontsize=float(rec.get("fontsize", DEFAULT_FONT_SIZE)),
                color=tuple(rec.get("color", DEFAULT_COLOR)),
                max_width=rec.get("max_width"),
                align=rec.get("align", "left"),
                fontname=fontname,
                fontfile=fontfile,
            )

    page_count = doc.page_count
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(args.output), deflate=True, garbage=4)
    doc.close()

    size_kb = args.output.stat().st_size / 1024
    print(f"Bilingual PDF generated: {args.output}")
    print(f"Size: {size_kb:.1f} KB | Pages: {page_count} | Translations placed: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
