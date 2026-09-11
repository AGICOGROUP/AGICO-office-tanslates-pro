#!/usr/bin/env python3
"""Return only repository glossary rows relevant to an Excel manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from glossary import lookup_terms, parse_glossary


def parse_rows(text: str) -> list[dict]:
    return parse_glossary(text)


def query(repo_root: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = list(dict.fromkeys(str(unit.get("source", "")) for unit in manifest.get("translation_units", [])))
    result = lookup_terms(sources, repo_root, manifest.get("target_language", "en"))
    return {"glossary": result["path"], "source_units": len(sources),
            "matched_entries": len(result["matched_entries"]), "entries": result["matched_entries"]}


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
