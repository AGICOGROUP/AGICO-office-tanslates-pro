#!/usr/bin/env python3
"""Classify a PDF and select exactly one independent PDF translation skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from pypdf import PdfReader
from pypdf.errors import PdfReadError


PDF_SIGNATURE = b"%PDF-"
NATIVE_ADAPTER = "formats/pdf/native/SKILL.md"
SCAN_ADAPTER = "formats/pdf/scan/SKILL.md"


def report(
    *,
    pdf_type: str | None = None,
    adapter: str | None = None,
    page_count: int = 0,
    native_text_pages: int = 0,
    native_char_counts: list[int] | None = None,
    rotated_pages: list[int] | None = None,
    encrypted: bool = False,
    extension_mismatch: bool = False,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "format": "pdf" if pdf_type or adapter else None,
        "pdf_type": pdf_type,
        "adapter": adapter,
        "page_count": page_count,
        "native_text_pages": native_text_pages,
        "native_char_counts": native_char_counts or [],
        "rotated_pages": rotated_pages or [],
        "encrypted": encrypted,
        "extension_mismatch": extension_mismatch,
        "error": error,
    }


def route(source: Path) -> tuple[int, dict[str, object]]:
    if not source.is_file():
        return 2, report(error="source file not found")

    try:
        with source.open("rb") as stream:
            signature = stream.read(len(PDF_SIGNATURE))
    except OSError as exc:
        return 2, report(error=f"cannot inspect source: {exc}")

    if signature != PDF_SIGNATURE:
        return 2, report(error="file does not have a valid PDF signature")
    if source.suffix.lower() != ".pdf":
        return 2, report(
            extension_mismatch=True,
            error=f"file extension {source.suffix or '<none>'} does not match detected pdf container",
        )

    try:
        reader = PdfReader(source, strict=False)
        if reader.is_encrypted:
            return 2, report(encrypted=True, error="encrypted PDF requires decryption before routing")

        counts: list[int] = []
        rotated: list[int] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            counts.append(len("".join(text.split())))
            if int(page.rotation or 0) % 360:
                rotated.append(page_number)
    except (OSError, PdfReadError, ValueError, TypeError) as exc:
        return 2, report(error=f"cannot read PDF: {exc}")

    page_count = len(counts)
    if page_count == 0:
        return 2, report(error="PDF contains no pages")
    native_text_pages = sum(count > 0 for count in counts)
    if native_text_pages == 0:
        if rotated:
            return 2, report(
                pdf_type="scan-only",
                page_count=page_count,
                native_char_counts=counts,
                rotated_pages=rotated,
                error="normalize rotated scan pages before translation routing",
            )
        return 0, report(
            pdf_type="scan-only",
            adapter=SCAN_ADAPTER,
            page_count=page_count,
            native_char_counts=counts,
        )

    pdf_type = "native-text" if native_text_pages == page_count else "mixed"
    return 0, report(
        pdf_type=pdf_type,
        adapter=NATIVE_ADAPTER,
        page_count=page_count,
        native_text_pages=native_text_pages,
        native_char_counts=counts,
        rotated_pages=rotated,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    exit_code, result = route(args.source)
    print(json.dumps(result, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
