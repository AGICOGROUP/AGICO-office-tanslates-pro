#!/usr/bin/env python3
"""Fast, read-only DOCX preflight for the Word translation pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"
TEXT_PART = re.compile(r"word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$")
PROTECTED_TOKEN = re.compile(
    r"https?://\S+|www\.\S+|\b\d+(?:[.,]\d+)?\s*(?:%|°C|kW|MW|V|kV|A|mA|Pa|kPa|MPa|"
    r"mm|cm|m|km|kg|t|t/h|m[³3]/h|Nm[³3]/min|rpm|r/min)\b|\b[A-Z][A-Z0-9._/-]*\d[A-Z0-9._/-]*\b",
    re.IGNORECASE,
)
SAFE_FIELD_COMMANDS = {"PAGE", "NUMPAGES", "DATE", "TIME", "CREATEDATE", "SAVEDATE", "FILENAME", "AUTHOR"}


def paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag in {f"{W}t", f"{W}tab", f"{W}br", f"{W}cr"}:
            if node.tag == f"{W}t":
                pieces.append(node.text or "")
            elif node.tag == f"{W}tab":
                pieces.append("\t")
            else:
                pieces.append("\n")
    return "".join(pieces).strip()


def analyze(path: Path) -> dict:
    raw = path.read_bytes()
    occurrences: list[dict] = []
    unique_texts: list[str] = []
    seen: set[str] = set()
    protected_tokens: list[dict] = []
    reasons: set[str] = set()
    section_count = 0
    table_count = 0
    field_codes: list[dict] = []

    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise ValueError("OOXML package does not contain word/document.xml")

            media = sorted(name for name in names if name.startswith("word/media/") and not name.endswith("/"))
            if any(name.startswith("word/charts/") for name in names):
                reasons.add("charts")

            for part_name in sorted(name for name in names if TEXT_PART.fullmatch(name)):
                root = ET.fromstring(archive.read(part_name))
                if part_name == "word/comments.xml" and next(root.iter(f"{W}comment"), None) is not None:
                    reasons.add("comments")
                if part_name in {"word/footnotes.xml", "word/endnotes.xml"}:
                    note_tag = "footnote" if "footnotes" in part_name else "endnote"
                    has_real_note = any(
                        int(node.attrib.get(f"{W}id", "-1")) >= 1 for node in root.iter(f"{W}{note_tag}")
                    )
                    if has_real_note:
                        reasons.add(note_tag + "s")
                if any(next(root.iter(f"{W}{tag}"), None) is not None for tag in ("ins", "del", "moveFrom", "moveTo")):
                    reasons.add("tracked_changes")
                part_field_codes = [
                    (node.text or "").strip() for node in root.iter(f"{W}instrText") if (node.text or "").strip()
                ]
                part_field_codes.extend(
                    (node.attrib.get(f"{W}instr") or "").strip()
                    for node in root.iter(f"{W}fldSimple")
                    if (node.attrib.get(f"{W}instr") or "").strip()
                )
                for code in part_field_codes:
                    command = code.split(maxsplit=1)[0].upper() if code else ""
                    field_codes.append({"part": part_name, "code": code, "command": command})
                    if command not in SAFE_FIELD_COMMANDS:
                        reasons.add("complex_fields")
                if next(root.iter(f"{W}txbxContent"), None) is not None:
                    reasons.add("text_boxes")
                if next(root.iter(f"{W}anchor"), None) is not None:
                    reasons.add("floating_objects")

                if part_name == "word/document.xml":
                    section_count = sum(1 for _ in root.iter(f"{W}sectPr"))
                    tables = list(root.iter(f"{W}tbl"))
                    table_count = len(tables)
                    if any(sum(1 for _ in table.iter(f"{W}tbl")) > 1 for table in tables):
                        reasons.add("nested_tables")
                    for cols in root.iter(f"{W}cols"):
                        count = int(cols.attrib.get(f"{W}num", "1"))
                        if count > 1:
                            reasons.add("multi_column_sections")

                for index, paragraph in enumerate(root.iter(f"{W}p"), start=1):
                    text = paragraph_text(paragraph)
                    if not text:
                        continue
                    occurrences.append({"part": part_name, "paragraph": index, "text": text})
                    if text not in seen:
                        seen.add(text)
                        unique_texts.append(text)
                    tokens = PROTECTED_TOKEN.findall(text)
                    if tokens:
                        protected_tokens.append({"part": part_name, "paragraph": index, "tokens": tokens})
    except (BadZipFile, ET.ParseError, OSError, ValueError) as exc:
        raise ValueError(f"Cannot analyze DOCX: {exc}") from exc

    return {
        "source": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
        "path": "complex" if reasons else "fast",
        "complex_reasons": sorted(reasons),
        "section_count": section_count,
        "table_count": table_count,
        "media_count": len(media),
        "needs_image_triage": bool(media),
        "text_occurrence_count": len(occurrences),
        "unique_text_count": len(unique_texts),
        "unique_texts": unique_texts,
        "occurrences": occurrences,
        "protected_tokens": protected_tokens,
        "field_codes": field_codes,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    try:
        report = analyze(args.docx)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        summary = {
            "path": report["path"],
            "complex_reasons": report["complex_reasons"],
            "text_occurrence_count": report["text_occurrence_count"],
            "unique_text_count": report["unique_text_count"],
            "table_count": report["table_count"],
            "media_count": report["media_count"],
            "output": str(args.output.resolve()),
        }
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
