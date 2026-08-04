#!/usr/bin/env python3
"""Detect an Office container and select exactly one translation adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile


CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
OOXML_MARKERS = {
    "word": "word/document.xml",
    "excel": "xl/workbook.xml",
    "ppt": "ppt/presentation.xml",
}
OOXML_EXTENSIONS = {
    "word": {".docx", ".docm"},
    "excel": {".xlsx", ".xlsm"},
    "ppt": {".pptx", ".pptm"},
}
LEGACY_EXTENSIONS = {".doc": "word", ".xls": "excel", ".ppt": "ppt"}


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
    try:
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as archive:
                entries = set(archive.namelist())
            matches = [name for name, marker in OOXML_MARKERS.items() if marker in entries]
            if len(matches) > 1:
                return 2, report(
                    detection="ooxml-signature",
                    error="ambiguous OOXML package contains markers for multiple Office formats",
                )
            if not matches:
                return 2, report(
                    detection="zip-signature",
                    error="unsupported ZIP package: no recognized Office document marker",
                )
            format_name = matches[0]
            mismatch = suffix not in OOXML_EXTENSIONS[format_name]
            if mismatch:
                return 2, report(
                    format_name=format_name,
                    detection="ooxml-signature",
                    extension_mismatch=True,
                    error=f"file extension {suffix or '<none>'} does not match detected {format_name} package",
                )
            return 0, report(format_name=format_name, detection="ooxml-signature")

        with source.open("rb") as stream:
            signature = stream.read(len(CFB_SIGNATURE))
        if signature == CFB_SIGNATURE:
            format_name = LEGACY_EXTENSIONS.get(suffix)
            if not format_name:
                return 2, report(
                    detection="cfb-signature",
                    extension_mismatch=True,
                    error=f"unsupported or missing legacy Office extension: {suffix or '<none>'}",
                )
            return 0, report(
                format_name=format_name,
                detection="cfb-signature+extension",
                requires_conversion=True,
            )
    except (OSError, zipfile.BadZipFile) as exc:
        return 2, report(error=f"cannot inspect source: {exc}")

    return 2, report(error="unsupported or corrupt Office file signature")


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
