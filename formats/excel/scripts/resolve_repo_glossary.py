#!/usr/bin/env python3
"""Resolve the repository-wide cement terminology reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


GLOSSARY_RELATIVE_PATH = Path("references") / "水泥专业名词中英对照.md"


def count_glossary_entries(text: str) -> int:
    entries = 0
    expected_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or not cells[1]:
            continue
        first = cells[0].lower()
        second = cells[1].lower()
        if first in {"中文", "中文术语", "chinese"} and second in {"英文", "英文术语", "english"}:
            expected_table = True
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if not expected_table:
            continue
        if any("\u4e00" <= char <= "\u9fff" for char in cells[0]) and any(char.isascii() and char.isalpha() for char in cells[1]):
            entries += 1
    return entries


def resolve_glossary(repo_root: str | Path | None = None) -> dict:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    glossary = (root / GLOSSARY_RELATIVE_PATH).resolve()
    if not glossary.is_file():
        return {"exists": False, "valid": False, "path": str(glossary), "entries": 0, "error": "glossary file not found"}
    try:
        text = glossary.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"exists": True, "valid": False, "path": str(glossary), "entries": 0, "error": str(exc)}
    entries = count_glossary_entries(text)
    valid = bool(text.strip()) and entries > 0
    return {
        "exists": True,
        "valid": valid,
        "path": str(glossary),
        "entries": entries,
        "error": None if valid else "glossary must contain at least one Markdown table entry",
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root; inferred when omitted")
    args = parser.parse_args()
    report = resolve_glossary(args.repo_root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
