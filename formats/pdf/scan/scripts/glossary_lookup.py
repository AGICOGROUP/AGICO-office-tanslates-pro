from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_GLOSSARY = Path(__file__).resolve().parents[1] / "references" / "cement-terminology.md"


def parse_glossary(path: Path) -> tuple[dict[str, dict], dict[str, list[str]]]:
    entries: dict[str, dict] = {}
    history: dict[str, list[str]] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        source, translation = cells[0], cells[1]
        if (
            not source
            or not translation
            or source == "中文术语"
            or set(source) <= {"-", ":", " "}
            or set(translation) <= {"-", ":", " "}
        ):
            continue
        history.setdefault(source, []).append(translation)
        entries[source] = {
            "source": source,
            "translation": translation,
            "line": line_number,
        }
    return entries, history


def scan_text(text: str, entries: dict[str, dict]) -> list[dict]:
    occupied: list[tuple[int, int]] = []
    matches: list[dict] = []
    for source in sorted(entries, key=lambda value: (-len(value), value)):
        start = text.find(source)
        while start >= 0:
            end = start + len(source)
            if not any(start < right and end > left for left, right in occupied):
                matches.append({**entries[source], "start": start, "end": end})
                occupied.append((start, end))
            start = text.find(source, start + 1)
    return sorted(matches, key=lambda item: (item["start"], -len(item["source"])))


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the bundled cement terminology table")
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lookup = subparsers.add_parser("lookup")
    lookup.add_argument("term")
    scan = subparsers.add_parser("scan")
    scan.add_argument("text")
    args = parser.parse_args()

    entries, history = parse_glossary(args.glossary)
    if args.command == "lookup":
        term = args.term.strip()
        entry = entries.get(term)
        if entry is None:
            print(json.dumps({"found": False, "source": term}, ensure_ascii=False))
            raise SystemExit(4)
        alternatives = list(dict.fromkeys(history[term]))
        print(
            json.dumps(
                {"found": True, **entry, "alternatives": alternatives},
                ensure_ascii=False,
            )
        )
        return

    print(
        json.dumps(
            {"matches": scan_text(args.text, entries)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
