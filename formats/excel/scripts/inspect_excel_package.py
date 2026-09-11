#!/usr/bin/env python3
"""Inspect Excel OOXML risk features and group image occurrences by content hash."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import sys
import tempfile
from collections import Counter
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
SHEET_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"


def _is_invisible_rectangle(shape: ET.Element) -> bool:
    """Recognize explicit legacy placeholders, never infer invisibility from size.

    Missing paint properties may inherit a theme. Hidden Office paint caches and
    creation IDs do not render; unknown extensions still require normal inspection.
    """
    if shape.get("textlink") or any(
        (node.text or "").strip() for node in shape.findall(f".//{{{DRAWING_NS}}}t")
    ):
        return False
    props = shape.find(f"{{{SHEET_DRAWING_NS}}}spPr")
    if props is None:
        return False
    geom = props.find(f"{{{DRAWING_NS}}}prstGeom")
    if geom is None or geom.get("prst") != "rect":
        return False
    if props.find(f"{{{DRAWING_NS}}}noFill") is None:
        return False
    line = props.find(f"{{{DRAWING_NS}}}ln")
    if line is None or line.find(f"{{{DRAWING_NS}}}noFill") is None:
        return False
    metadata_extensions = {
        ('{FF2B5EF4-FFF2-40B4-BE49-F238E27FC236}',
         '{http://schemas.microsoft.com/office/drawing/2014/main}creationId'),
        ('{909E8E84-426E-40DD-AFC4-6F175D3DCCD1}',
         '{http://schemas.microsoft.com/office/drawing/2010/main}hiddenFill'),
        ('{91240B29-F687-4F45-9708-019B960494DF}',
         '{http://schemas.microsoft.com/office/drawing/2010/main}hiddenLine'),
    }
    pending = [shape]
    while pending:
        node = pending.pop()
        if node.tag == f'{{{DRAWING_NS}}}extLst':
            for extension in node:
                if (extension.tag != f'{{{DRAWING_NS}}}ext' or not len(extension)
                        or any((extension.get('uri', '').upper(), child.tag)
                               not in metadata_extensions for child in extension)):
                    return False
            # These subtrees store inactive paint or identity, not visible content.
            continue
        local = node.tag.rsplit("}", 1)[-1]
        if local in {"solidFill", "gradFill", "blipFill", "pattFill", "grpFill",
                     "effectDag", "scene3d", "sp3d", "extLst"}:
            return False
        if local == "effectLst" and len(node):
            return False
        if local == "effectRef" and node.get("idx") != "0":
            return False
        pending.extend(node)
    return True


def _drawing_shape_counts(archive: ZipFile) -> tuple[int, int]:
    meaningful = decorative = 0
    for name in archive.namelist():
        if not name.startswith("xl/drawings/") or not name.endswith(".xml"):
            continue
        root = ET.fromstring(archive.read(name))
        meaningful += sum(
            len(root.findall(f".//{{{SHEET_DRAWING_NS}}}{tag}"))
            for tag in ("cxnSp", "graphicFrame", "contentPart")
        )
        for shape in root.findall(f".//{{{SHEET_DRAWING_NS}}}sp"):
            if _is_invisible_rectangle(shape):
                decorative += 1
                continue
            text = "".join(node.text or "" for node in shape.findall(f".//{{{DRAWING_NS}}}t")).strip()
            extent = shape.find(f".//{{{DRAWING_NS}}}ext")
            width = int(extent.attrib.get("cx", "0")) if extent is not None else 0
            height = int(extent.attrib.get("cy", "0")) if extent is not None else 0
            # 12700 EMU is one point. A sub-2-point dimension is normally a legacy border fragment.
            if text or (width >= 25400 and height >= 25400):
                meaningful += 1
            else:
                decorative += 1
    return meaningful, decorative


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
            meaningful_drawings, decorative_drawings = _drawing_shape_counts(archive)
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
                "meaningful_drawing_count": meaningful_drawings,
                "decorative_drawing_count": decorative_drawings,
                "image_occurrence_count": sum(item["occurrence_count"] for item in images),
                "unique_image_count": len(images),
            }
            return {"features": features, "images": images}
    except BadZipFile as exc:
        raise ValueError("unsupported or corrupt Excel OOXML package") from exc


def apply_image_replacements(path: Path, manifest: dict) -> dict:
    from PIL import Image
    localized = [item for item in manifest.get("images", []) if item.get("status") == "localized"]
    with ZipFile(path) as archive:
        originals = {hashlib.sha256(archive.read(name)).hexdigest(): archive.read(name)
                     for name in archive.namelist() if name.startswith("xl/media/")}
    replacements = {}
    for item in localized:
        digest = item["sha256"]
        replacement = Path(item.get("replacement_path", ""))
        if digest not in originals or not replacement.is_file():
            raise ValueError("localized image requires its source asset and replacement file")
        data = replacement.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != item.get("replacement_sha256") or actual_hash == digest:
            raise ValueError("localized image replacement hash is changed or identical to source")
        with Image.open(io.BytesIO(originals[digest])) as before, Image.open(io.BytesIO(data)) as after:
            before.load(); after.load()
            if before.format not in {"PNG", "JPEG"} or before.format != after.format or before.size != after.size:
                raise ValueError("localized image must preserve PNG/JPEG format and pixel dimensions")
        replacements[digest] = data
    descriptor, temporary_name = tempfile.mkstemp(prefix=".images-", suffix=".xlsx", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(path) as source, ZipFile(temporary, "w") as target:
            target.comment = source.comment
            for entry in source.infolist():
                data = source.read(entry.filename)
                if entry.filename.startswith("xl/media/"):
                    data = replacements.get(hashlib.sha256(data).hexdigest(), data)
                target.writestr(entry, data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"replaced_images": len(replacements)}


def verify_image_manifest(report: dict, manifest: dict) -> None:
    expected = Counter()
    actual = Counter()
    for item in manifest.get("images", []):
        digest = item.get("replacement_sha256") if item.get("status") == "localized" else item.get("sha256")
        if not digest:
            raise ValueError("localized image has no replacement hash")
        expected[digest] += max(1, len(item.get("occurrences", [])))
    for item in report.get("images", []):
        actual[item["sha256"]] += item["occurrence_count"]
    if expected - actual:
        raise ValueError("expected image bytes or image occurrences are missing from output")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--extract-dir", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply-images", type=Path)
    actions.add_argument("--verify-images", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.apply_images:
            report = apply_image_replacements(args.source, json.loads(args.apply_images.read_text(encoding="utf-8")))
        else:
            report = inspect_package(args.source, args.extract_dir)
            if args.verify_images:
                verify_image_manifest(report, json.loads(args.verify_images.read_text(encoding="utf-8")))
    except (OSError, ValueError, ET.ParseError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
