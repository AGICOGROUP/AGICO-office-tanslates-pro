#!/usr/bin/env python3
"""Inspect Excel OOXML risk features and group image occurrences by content hash."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _rels_path(part: str) -> str:
    path = PurePosixPath(part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _resolve_target(owner_part: str, target: str) -> str:
    normalized = target.replace("\\", "/")
    if normalized.startswith("/"):
        return posixpath.normpath(normalized.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner_part), normalized))


def _relationships(archive: ZipFile, owner_part: str) -> dict[str, dict[str, str]]:
    rels_path = _rels_path(owner_part)
    if rels_path not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read(rels_path))
    relationships: dict[str, dict[str, str]] = {}
    for node in root.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        rel_id = node.attrib.get("Id")
        target = node.attrib.get("Target")
        if not rel_id or not target or node.attrib.get("TargetMode", "Internal") != "Internal":
            continue
        relationships[rel_id] = {
            "type": node.attrib.get("Type", ""),
            "target": _resolve_target(owner_part, target),
        }
    return relationships


def _sheet_parts(archive: ZipFile) -> list[tuple[str, str]]:
    workbook_part = "xl/workbook.xml"
    if workbook_part not in archive.namelist():
        raise ValueError("missing xl/workbook.xml")
    workbook = ET.fromstring(archive.read(workbook_part))
    rels = _relationships(archive, workbook_part)
    sheets: list[tuple[str, str]] = []
    for node in workbook.findall(f".//{{{SPREADSHEET_NS}}}sheet"):
        rel_id = node.attrib.get(f"{{{DOCUMENT_REL_NS}}}id")
        relationship = rels.get(rel_id or "")
        if relationship and relationship["type"].endswith("/worksheet"):
            sheets.append((node.attrib.get("name", ""), relationship["target"]))
    return sheets


def _image_occurrences(archive: ZipFile) -> dict[str, list[dict[str, str]]]:
    occurrences: dict[str, list[dict[str, str]]] = {}
    relationship_attribute = f"{{{DOCUMENT_REL_NS}}}embed"
    for sheet_name, sheet_part in _sheet_parts(archive):
        sheet_rels = _relationships(archive, sheet_part)
        drawing_parts = [
            relationship["target"]
            for relationship in sheet_rels.values()
            if relationship["type"].endswith("/drawing")
        ]
        for drawing_part in drawing_parts:
            if drawing_part not in archive.namelist():
                continue
            drawing_rels = _relationships(archive, drawing_part)
            drawing_root = ET.fromstring(archive.read(drawing_part))
            for node in drawing_root.iter():
                rel_id = node.attrib.get(relationship_attribute)
                relationship = drawing_rels.get(rel_id or "")
                if not relationship or not relationship["type"].endswith("/image"):
                    continue
                media_path = relationship["target"]
                occurrences.setdefault(media_path, []).append(
                    {
                        "sheet": sheet_name,
                        "location": f"{sheet_name}#{drawing_part}:{rel_id}",
                    }
                )
    return occurrences


def inspect_package(path: str | Path, extract_dir: str | Path | None = None) -> dict:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"file not found: {source}")
    try:
        with ZipFile(source) as archive:
            names = set(archive.namelist())
            occurrences_by_path = _image_occurrences(archive)
            media_paths = sorted(name for name in names if name.startswith("xl/media/") and not name.endswith("/"))
            groups: dict[str, dict] = {}
            for media_path in media_paths:
                data = archive.read(media_path)
                digest = hashlib.sha256(data).hexdigest()
                group = groups.setdefault(
                    digest,
                    {
                        "sha256": digest,
                        "media_path": media_path,
                        "extension": Path(media_path).suffix.lower(),
                        "occurrences": [],
                        "sheets": set(),
                        "data": data,
                    },
                )
                occurrences = occurrences_by_path.get(media_path) or [
                    {"sheet": "", "location": f"package:{media_path}"}
                ]
                group["occurrences"].extend(item["location"] for item in occurrences)
                group["sheets"].update(item["sheet"] for item in occurrences if item["sheet"])

            extraction_root = Path(extract_dir) if extract_dir is not None else None
            if extraction_root is not None:
                extraction_root.mkdir(parents=True, exist_ok=True)

            images = []
            for digest in sorted(groups):
                group = groups[digest]
                extracted_path = None
                if extraction_root is not None:
                    suffix = group["extension"] or ".bin"
                    destination = extraction_root / f"{digest}{suffix}"
                    destination.write_bytes(group["data"])
                    extracted_path = str(destination)
                images.append(
                    {
                        "sha256": digest,
                        "media_path": group["media_path"],
                        "extension": group["extension"],
                        "occurrence_count": len(group["occurrences"]),
                        "occurrences": group["occurrences"],
                        "sheets": sorted(group["sheets"]),
                        "extracted_path": extracted_path,
                    }
                )

            features = {
                "has_vba": "xl/vbaProject.bin" in names,
                "chart_count": sum(name.startswith("xl/charts/") and name.endswith(".xml") for name in names),
                "comment_count": sum(name.startswith("xl/comments") and name.endswith(".xml") for name in names),
                "external_link_count": sum(name.startswith("xl/externalLinks/") and name.endswith(".xml") for name in names),
                "table_count": sum(name.startswith("xl/tables/") and name.endswith(".xml") for name in names),
                "drawing_count": sum(name.startswith("xl/drawings/") and name.endswith(".xml") for name in names),
                "image_occurrence_count": sum(item["occurrence_count"] for item in images),
                "unique_image_count": len(images),
            }
            return {"features": features, "images": images}
    except BadZipFile as exc:
        raise ValueError("unsupported or corrupt Excel OOXML package") from exc


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--extract-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = inspect_package(args.source, args.extract_dir)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
