"""Shared, source-matched cement terminology lookup for all Office adapters."""
from __future__ import annotations

import json
from pathlib import Path
import re

GLOSSARY_RELATIVE_PATH = Path("references") / "水泥专业名词中英对照.md"


def resolve_glossary(repo_root=None) -> dict:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[1]
    glossary = root / GLOSSARY_RELATIVE_PATH
    return {"exists": glossary.is_file(), "path": str(glossary)}


def parse_glossary(text: str) -> list[dict]:
    entries, seen = [], set()
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        metadata = re.search(r"<!--\s*(\{.*?\})\s*-->", line)
        notes = json.loads(metadata.group(1)) if metadata else {}
        clean = re.sub(r"<!--.*?-->", "", line)
        cells = [cell.strip() for cell in clean.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[1] or cells[0] in {"中文", "中文术语"}:
            continue
        if not re.search(r"[\u3400-\u9fff]", cells[0]):
            continue
        key = tuple(cells[:2])
        if key in seen:
            continue
        seen.add(key)
        entry = {"source": cells[0], "target": cells[1]}
        for field in ("aliases", "context"):
            if notes.get(field):
                entry[field] = notes[field]
        entries.append(entry)
    return entries


def relevant_entries(text: str, entries) -> list[dict]:
    normalized = text.strip()
    exact = [entry for entry in entries if entry["source"].casefold() == normalized.casefold()]
    if exact:
        return [{key: value for key, value in {**entry, "match_type": "exact", "offset": 0}.items()
                 if key != "_pattern"} for entry in exact]
    candidates = []
    for entry in entries:
        term = entry["source"]
        pattern = entry.get("_pattern")
        if pattern is None:
            expression = re.escape(term)
            if term.isascii():
                expression = r"(?<![A-Za-z0-9])" + expression + r"(?![A-Za-z0-9])"
            pattern = re.compile(expression, re.IGNORECASE)
        for match in pattern.finditer(normalized):
            candidates.append((match.start(), match.end(), entry))
    candidates.sort(key=lambda item: (-(item[1] - item[0]), item[0], item[2]["source"]))
    selected = []
    for start, end, entry in candidates:
        if any(start < right and end > left and (start, end) != (left, right) for left, right, _ in selected):
            continue
        selected.append((start, end, entry))
    selected.sort(key=lambda item: item[0])
    return [{key: value for key, value in {**entry, "match_type": "contained", "offset": start}.items()
             if key != "_pattern"} for start, _, entry in selected]


def lookup_terms(texts: list[str], repo_root=None, target_language: str = "en") -> dict:
    resolved = resolve_glossary(repo_root)
    entries = parse_glossary(Path(resolved["path"]).read_text(encoding="utf-8-sig")) if resolved["exists"] else []
    reverse = bool(re.match(r"^(?:zh(?:[-_]|$)|chinese\b|中文|简体中文|繁体中文)", target_language.strip(), re.IGNORECASE))
    candidates = entries
    if reverse:
        candidates = []
        for entry in entries:
            for english in dict.fromkeys([entry["target"], *entry.get("aliases", [])]):
                candidates.append({**entry, "source": english, "target": entry["source"]})
    compiled = []
    for entry in candidates:
        expression = re.escape(entry["source"])
        if entry["source"].isascii():
            expression = r"(?<![A-Za-z0-9])" + expression + r"(?![A-Za-z0-9])"
        compiled.append({**entry, "_pattern": re.compile(expression, re.IGNORECASE)})
    matches = {}
    for index, text in enumerate(texts):
        for match in relevant_entries(text, compiled):
            key = (match["source"], match["target"])
            record = matches.setdefault(key, {key: value for key, value in match.items() if key != "offset"})
            indices = record.setdefault("text_indices", [])
            if index not in indices:
                indices.append(index)
            if match["match_type"] == "exact":
                record["match_type"] = "exact"
    return {**resolved, "glossary_entries": len(entries), "texts": len(texts),
            "target_language": target_language, "matched_entries": list(matches.values())}
