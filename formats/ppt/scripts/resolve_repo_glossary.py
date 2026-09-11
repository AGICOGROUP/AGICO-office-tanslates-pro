#!/usr/bin/env python3
"""Resolve the repository-wide cement terminology reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from glossary import GLOSSARY_RELATIVE_PATH, lookup_terms, parse_glossary, relevant_entries, resolve_glossary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root; inferred when omitted")
    parser.add_argument("--text", action="append", default=[])
    parser.add_argument("--texts-json", type=Path)
    parser.add_argument("--target-language", default="en")
    args = parser.parse_args()
    texts = list(args.text)
    if args.texts_json:
        loaded = json.loads(args.texts_json.read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, list) or any(not isinstance(item, str) for item in loaded):
            parser.error("--texts-json must contain an array of strings")
        texts.extend(loaded)
    report = lookup_terms(texts, args.repo_root, args.target_language) if texts else resolve_glossary(args.repo_root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
