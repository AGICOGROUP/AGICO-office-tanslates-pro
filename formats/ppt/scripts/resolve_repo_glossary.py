#!/usr/bin/env python3
"""Resolve the repository-wide cement terminology reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable


GLOSSARY_RELATIVE_PATH = Path("references") / "水泥专业名词中英对照.md"


def resolve_glossary(repo_root: str | Path | None = None) -> dict:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    glossary = (root / GLOSSARY_RELATIVE_PATH).resolve()
    return {"exists": glossary.is_file(), "path": str(glossary)}


def parse_glossary(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or not cells[1]:
            continue
        source, target = cells[0], cells[1]
        if source in {"中文", "中文术语"} or target.lower() == "english":
            continue
        if all(character in "-: " for character in source + target):
            continue
        if not any("\u3400" <= character <= "\u9fff" for character in source):
            continue
        key = (source, target)
        if key not in seen:
            seen.add(key)
            entries.append({"source": source, "target": target})
    return entries


def relevant_entries(text: str, entries: Iterable[dict[str, str]]) -> list[dict]:
    normalized = text.strip()
    exact = [entry for entry in entries if entry["source"] == normalized]
    if exact:
        return [{**entry, "match_type": "exact", "offset": 0} for entry in exact[:1]]

    candidates: list[tuple[int, int, dict[str, str]]] = []
    for entry in entries:
        start = normalized.find(entry["source"])
        if start >= 0:
            candidates.append((start, start + len(entry["source"]), entry))
    candidates.sort(key=lambda item: (-(item[1] - item[0]), item[0], item[2]["source"]))
    selected: list[tuple[int, int, dict[str, str]]] = []
    for start, end, entry in candidates:
        if any(start < chosen_end and end > chosen_start for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, entry))
    selected.sort(key=lambda item: item[0])
    return [
        {**entry, "match_type": "contained", "offset": start}
        for start, _end, entry in selected
    ]


def lookup_terms(
    texts: list[str], repo_root: str | Path | None = None
) -> dict:
    resolved = resolve_glossary(repo_root)
    if not resolved["exists"]:
        return {
            **resolved,
            "glossary_entries": 0,
            "texts": len(texts),
            "matched_entries": [],
        }
    glossary_text = Path(resolved["path"]).read_text(encoding="utf-8-sig")
    entries = parse_glossary(glossary_text)
    matches_by_key: dict[tuple[str, str], dict] = {}
    for text_index, text in enumerate(texts):
        for match in relevant_entries(text, entries):
            key = (match["source"], match["target"])
            record = matches_by_key.setdefault(
                key,
                {
                    "source": match["source"],
                    "target": match["target"],
                    "match_type": match["match_type"],
                    "text_indices": [],
                },
            )
            record["text_indices"].append(text_index)
            if match["match_type"] == "exact":
                record["match_type"] = "exact"
    return {
        **resolved,
        "glossary_entries": len(entries),
        "texts": len(texts),
        "matched_entries": list(matches_by_key.values()),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root; inferred when omitted")
    parser.add_argument("--text", action="append", default=[])
    parser.add_argument("--texts-json", type=Path)
    args = parser.parse_args()
    texts = list(args.text)
    if args.texts_json:
        loaded = json.loads(args.texts_json.read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, list) or any(not isinstance(item, str) for item in loaded):
            parser.error("--texts-json must contain an array of strings")
        texts.extend(loaded)
    report = lookup_terms(texts, args.repo_root) if texts else resolve_glossary(args.repo_root)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
