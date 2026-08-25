#!/usr/bin/env python3
"""Return only repository glossary rows relevant to an Excel manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


GLOSSARY = Path("references") / "水泥专业名词中英对照.md"


def parse_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or all(set(cell) <= {"-", ":"} for cell in cells[:2]):
            continue
        if cells[0].lower() in {"中文术语", "chinese", "source"}:
            continue
        if cells[0] and cells[1]:
            rows.append({"source": cells[0], "target": cells[1]})
    return rows


def query(repo_root: Path, manifest_path: Path) -> dict:
    glossary_path = repo_root / GLOSSARY
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {str(unit.get("source", "")) for unit in manifest.get("translation_units", [])}
    rows = parse_rows(glossary_path.read_text(encoding="utf-8"))
    matches = [row for row in rows if any(row["source"] in source for source in sources)]
    matches.sort(key=lambda row: next(i for i, item in enumerate(rows) if item == row))
    return {
        "glossary": str(glossary_path.resolve()),
        "source_units": len(sources),
        "matched_entries": len(matches),
        "entries": matches,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = query(args.repo_root.resolve(), args.manifest.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
