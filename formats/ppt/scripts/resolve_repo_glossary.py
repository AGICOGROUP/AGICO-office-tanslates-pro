#!/usr/bin/env python3
"""Resolve the repository-wide cement terminology reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


GLOSSARY_RELATIVE_PATH = Path("references") / "水泥专业名词中英对照.md"


def resolve_glossary(repo_root: str | Path | None = None) -> dict:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    glossary = (root / GLOSSARY_RELATIVE_PATH).resolve()
    return {"exists": glossary.is_file(), "path": str(glossary)}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root; inferred when omitted")
    args = parser.parse_args()
    report = resolve_glossary(args.repo_root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
