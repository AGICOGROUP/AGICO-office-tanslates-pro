#!/usr/bin/env python3
"""Inspect a PDF's text layout: extract every text span with bbox, font, size.

Outputs a JSON array of span records suitable for building a bilingual
translation packet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf as fitz


def inspect(source: Path) -> list[dict]:
    """Return a list of text-span dicts for every page in the PDF."""
    doc = fitz.open(source)
    spans: list[dict] = []
    for page_idx, page in enumerate(doc):
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                # Image block — record its bbox for reference
                spans.append({
                    "page": page_idx,
                    "type": "image",
                    "bbox": [round(x, 1) for x in block["bbox"]],
                    "text": "",
                })
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    spans.append({
                        "page": page_idx,
                        "type": "text",
                        "bbox": [round(x, 1) for x in span["bbox"]],
                        "text": text,
                        "font": span.get("font", ""),
                        "size": round(span.get("size", 0), 1),
                        "flags": span.get("flags", 0),
                    })
    doc.close()
    return spans


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source PDF file")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output JSON file (default: stdout)",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(json.dumps({"error": "source file not found"}), file=sys.stderr)
        return 2

    spans = inspect(args.source)
    output_text = json.dumps(spans, ensure_ascii=False, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
        print(f"Layout written to {args.output} ({len(spans)} spans)", file=sys.stderr)
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
