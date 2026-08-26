#!/usr/bin/env python3
"""Inspect a PowerPoint OOXML package once for text, media, and risk."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
UNSUPPORTED_TEXT_PARTS = (
    "ppt/charts/",
    "ppt/diagrams/",
    "ppt/notesSlides/",
    "ppt/slideMasters/",
)
PROTECTED_RE = re.compile(
    r"(?:https?://\S+|\b[A-Z]{1,8}[-/]?\d[\w./-]*\b|\b\d+(?:[.,]\d+)?\s*(?:%|mm|cm|m|km|kg|t|kW|MW|V|kV|Hz|°C)\b)",
    re.IGNORECASE,
)


class InspectionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def xml_contains_human_text(payload: bytes) -> bool:
    root = ET.fromstring(payload)
    return any(
        node.text and any(character.isalpha() for character in node.text)
        for node in root.iter()
        if local_name(node.tag) in {"t", "v"}
    )


def package_has_vba(package: ZipFile, names: set[str]) -> bool:
    if any(name.casefold().endswith("/vbaproject.bin") for name in names):
        return True
    content_types = package.read("[Content_Types].xml").lower() if "[Content_Types].xml" in names else b""
    return b"macroenabled" in content_types or b"vbaproject" in content_types


def paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for element in paragraph.iter():
        if element.tag == f"{{{A_NS}}}t":
            parts.append(element.text or "")
        elif element.tag == f"{{{A_NS}}}br":
            parts.append("\v")
    return "".join(parts).strip()


def shape_role(shape: ET.Element, name: str) -> str:
    if shape.find(f".//{{{A_NS}}}tbl") is not None:
        return "table"
    placeholder = shape.find(f".//{{{P_NS}}}ph")
    placeholder_type = "" if placeholder is None else placeholder.attrib.get("type", "")
    if placeholder_type in {"title", "ctrTitle", "subTitle"} or "title" in name.lower():
        return "title"
    return "body"


def extract_slide_occurrences(slide_xml: bytes, slide_index: int) -> list[dict]:
    root = ET.fromstring(slide_xml)
    occurrences: list[dict] = []
    container_names = {"sp", "graphicFrame", "cxnSp"}
    for shape in root.iter():
        if local_name(shape.tag) not in container_names:
            continue
        identity = shape.find(f".//{{{P_NS}}}cNvPr")
        if identity is None:
            continue
        shape_id = int(identity.attrib.get("id", "0"))
        shape_name = identity.attrib.get("name", "")
        role = shape_role(shape, shape_name)
        if role == "table":
            table = shape.find(f".//{{{A_NS}}}tbl")
            if table is None:
                continue
            package_indices = {
                id(paragraph): index
                for index, paragraph in enumerate(
                    shape.findall(f".//{{{A_NS}}}p"), start=1
                )
            }
            for row_index, row in enumerate(
                table.findall(f"{{{A_NS}}}tr"), start=1
            ):
                for column_index, cell in enumerate(
                    row.findall(f"{{{A_NS}}}tc"), start=1
                ):
                    for paragraph_index, paragraph in enumerate(
                        cell.findall(f".//{{{A_NS}}}p"), start=1
                    ):
                        text = paragraph_text(paragraph)
                        if not text:
                            continue
                        occurrences.append(
                            {
                                "id": (
                                    f"ppt/slide:{slide_index}/shape:{shape_id}"
                                    f"/cell:{row_index}:{column_index}"
                                    f"/paragraph:{paragraph_index}"
                                ),
                                "kind": "ppt_table_cell",
                                "source_text": text,
                                "slide_index": slide_index,
                                "shape_id": shape_id,
                                "row": row_index,
                                "column": column_index,
                                "paragraph_index": paragraph_index,
                                "package_paragraph_index": package_indices[id(paragraph)],
                                "role": role,
                                "shape_name": shape_name,
                                "context_signature": (
                                    f"table:r{row_index}:c{column_index}"
                                ),
                                "protected_tokens": PROTECTED_RE.findall(text),
                            }
                        )
            continue
        for paragraph_index, paragraph in enumerate(
            shape.findall(f".//{{{A_NS}}}p"), start=1
        ):
            text = paragraph_text(paragraph)
            if not text:
                continue
            occurrences.append(
                {
                    "id": f"ppt/slide:{slide_index}/shape:{shape_id}/paragraph:{paragraph_index}",
                    "kind": "ppt_paragraph",
                    "source_text": text,
                    "slide_index": slide_index,
                    "shape_id": shape_id,
                    "paragraph_index": paragraph_index,
                    "role": role,
                    "shape_name": shape_name,
                    "context_signature": role,
                    "protected_tokens": PROTECTED_RE.findall(text),
                }
            )
    return occurrences


def relationship_targets(package: ZipFile, slide_name: str) -> dict[str, str]:
    slide_path = PurePosixPath(slide_name)
    rels_name = str(slide_path.parent / "_rels" / f"{slide_path.name}.rels")
    if rels_name not in package.namelist():
        return {}
    root = ET.fromstring(package.read(rels_name))
    targets: dict[str, str] = {}
    for relationship in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        rel_type = relationship.attrib.get("Type", "")
        if not rel_type.endswith("/image"):
            continue
        target = PurePosixPath(relationship.attrib["Target"])
        resolved = str(PurePosixPath(*slide_path.parent.parts, *target.parts))
        parts: list[str] = []
        for part in PurePosixPath(resolved).parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        targets[relationship.attrib["Id"]] = "/".join(parts)
    return targets


def extract_slide_images(
    package: ZipFile, slide_name: str, slide_index: int
) -> list[dict]:
    root = ET.fromstring(package.read(slide_name))
    targets = relationship_targets(package, slide_name)
    occurrences: list[dict] = []
    shape_tree = root.find(f".//{{{P_NS}}}spTree")
    if shape_tree is None:
        return occurrences
    for container in list(shape_tree):
        if container.find(f".//{{{P_NS}}}oleObj") is not None:
            continue
        identity = container.find(f".//{{{P_NS}}}cNvPr")
        if identity is None:
            continue
        for blip in container.findall(f".//{{{A_NS}}}blip"):
            relationship_id = blip.attrib.get(f"{{{R_NS}}}embed", "")
            media_path = targets.get(relationship_id)
            if media_path and media_path in package.namelist():
                occurrences.append(
                    {
                        "slide_index": slide_index,
                        "shape_id": int(identity.attrib.get("id", "0")),
                        "shape_name": identity.attrib.get("name", ""),
                        "media_path": media_path,
                    }
                )
    return occurrences


def extract_slide_embedded_objects(
    package: ZipFile, slide_name: str, slide_index: int
) -> list[dict]:
    root = ET.fromstring(package.read(slide_name))
    slide_path = PurePosixPath(slide_name)
    rels_name = str(slide_path.parent / "_rels" / f"{slide_path.name}.rels")
    relationships: dict[str, tuple[str, str]] = {}
    if rels_name in package.namelist():
        rel_root = ET.fromstring(package.read(rels_name))
        for relationship in rel_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            target = PurePosixPath(relationship.attrib["Target"])
            combined = PurePosixPath(*slide_path.parent.parts, *target.parts)
            parts: list[str] = []
            for part in combined.parts:
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            relationships[relationship.attrib["Id"]] = (
                relationship.attrib.get("Type", ""),
                "/".join(parts),
            )

    objects: list[dict] = []
    shape_tree = root.find(f".//{{{P_NS}}}spTree")
    if shape_tree is None:
        return objects
    image_targets = relationship_targets(package, slide_name)
    for container in list(shape_tree):
        ole_object = container.find(f".//{{{P_NS}}}oleObj")
        identity = container.find(f".//{{{P_NS}}}cNvPr")
        if ole_object is None or identity is None:
            continue
        relationship_id = ole_object.attrib.get(f"{{{R_NS}}}id", "")
        relationship_type, embedding_path = relationships.get(relationship_id, ("", ""))
        if not relationship_type.endswith("/oleObject"):
            continue
        preview_paths = []
        for blip in container.findall(f".//{{{A_NS}}}blip"):
            preview = image_targets.get(blip.attrib.get(f"{{{R_NS}}}embed", ""))
            if preview and preview not in preview_paths:
                preview_paths.append(preview)
        objects.append({
            "slide_index": slide_index,
            "shape_id": int(identity.attrib.get("id", "0")),
            "shape_name": identity.attrib.get("name", ""),
            "prog_id": ole_object.attrib.get("progId", ""),
            "embedding_path": embedding_path,
            "preview_media_paths": preview_paths,
            "text_capability": "embedded_editable_object",
        })
    return objects


def inspect_package(input_path: str | Path) -> dict:
    path = Path(input_path).resolve()
    if not path.is_file():
        raise InspectionError(f"input file not found: {path}")
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            if package_has_vba(package, names):
                raise InspectionError("macro-enabled PowerPoint package is not supported")
            slide_entries = sorted(
                (
                    (int(match.group(1)), name)
                    for name in names
                    if (match := SLIDE_RE.fullmatch(name))
                ),
                key=lambda item: item[0],
            )
            if not slide_entries:
                raise InspectionError("package contains no PowerPoint slides")
            unsupported_text = sorted(
                name
                for name in names
                if name.endswith(".xml")
                and name.startswith(UNSUPPORTED_TEXT_PARTS)
                and xml_contains_human_text(package.read(name))
            )
            if unsupported_text:
                raise InspectionError(
                    "unsupported editable text parts: " + ", ".join(unsupported_text)
                )
            occurrences: list[dict] = []
            image_by_hash: dict[str, dict] = {}
            embedded_objects: list[dict] = []
            for slide_index, slide_name in slide_entries:
                payload = package.read(slide_name)
                occurrences.extend(extract_slide_occurrences(payload, slide_index))
                embedded_objects.extend(
                    extract_slide_embedded_objects(package, slide_name, slide_index)
                )
                for image in extract_slide_images(package, slide_name, slide_index):
                    data = package.read(image["media_path"])
                    digest = sha256(data).hexdigest()
                    group = image_by_hash.setdefault(
                        digest,
                        {
                            "sha256": digest,
                            "bytes": len(data),
                            "media_paths": [],
                            "occurrences": [],
                            "decision": "pending",
                        },
                    )
                    if image["media_path"] not in group["media_paths"]:
                        group["media_paths"].append(image["media_path"])
                    group["occurrences"].append(image)
    except (BadZipFile, ET.ParseError, KeyError) as exc:
        raise InspectionError(f"cannot inspect PowerPoint package: {exc}") from exc

    return {
        "schema_version": 1,
        "source_file": path.name,
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "slides": [{"index": index, "part": name} for index, name in slide_entries],
        "occurrences": occurrences,
        "image_groups": list(image_by_hash.values()),
        "embedded_objects": embedded_objects,
        "metrics": {
            "package_passes": 1,
            "slide_count": len(slide_entries),
            "text_occurrence_count": len(occurrences),
            "image_occurrence_count": sum(
                len(group["occurrences"]) for group in image_by_hash.values()
            ),
            "unique_image_count": len(image_by_hash),
            "embedded_object_count": len(embedded_objects),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = inspect_package(args.input)
    except InspectionError as exc:
        print(f"inspection error: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
