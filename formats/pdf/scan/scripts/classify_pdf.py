from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader


def classify(path: str | Path, native_char_threshold: int = 1) -> dict:
    source = Path(path).resolve()
    reader = PdfReader(str(source))
    chars_by_page = [len("".join((page.extract_text() or "").split())) for page in reader.pages]
    native_pages = [index + 1 for index, count in enumerate(chars_by_page) if count >= native_char_threshold]
    rotated_pages = [
        index + 1
        for index, page in enumerate(reader.pages)
        if int(page.get("/Rotate", 0) or 0) % 360
    ]
    if rotated_pages:
        route = "normalize-rotation-first"
    else:
        route = "scan-only" if not native_pages else "mixed-or-native"
    return {
        "source": str(source),
        "page_count": len(reader.pages),
        "native_char_counts": chars_by_page,
        "native_text_pages": native_pages,
        "rotated_pages": rotated_pages,
        "route": route,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a PDF before choosing the scan-only route")
    parser.add_argument("--source", required=True)
    parser.add_argument("--threshold", type=int, default=1)
    args = parser.parse_args()
    report = classify(args.source, args.threshold)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["route"] != "scan-only":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
