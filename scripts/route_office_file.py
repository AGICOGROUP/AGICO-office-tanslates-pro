#!/usr/bin/env python3
"""Detect a supported Word, Excel, or PowerPoint file and select its adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
EXTENSIONS = {
    ".doc": ("word", True), ".docx": ("word", False),
    ".xls": ("excel", True), ".xlsx": ("excel", False),
    ".ppt": ("ppt", True), ".pptx": ("ppt", False),
}


def report(
    *,
    format_name: str | None = None,
    detection: str | None = None,
    extension_mismatch: bool = False,
    requires_conversion: bool = False,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "format": format_name,
        "adapter": f"formats/{format_name}/SKILL.md" if format_name else None,
        "detection": detection,
        "extension_mismatch": extension_mismatch,
        "requires_conversion": requires_conversion,
        "error": error,
    }


def route(source: Path) -> tuple[int, dict[str, object]]:
    if not source.is_file():
        return 2, report(error="source file not found")

    suffix = source.suffix.lower()
    route_info = EXTENSIONS.get(suffix)
    if not route_info:
        return 2, report(error=f"unsupported file extension: {suffix or '<none>'}")
    format_name, requires_conversion = route_info
    return 0, report(
        format_name=format_name,
        detection="extension",
        requires_conversion=requires_conversion,
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
