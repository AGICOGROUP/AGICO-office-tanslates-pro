#!/usr/bin/env python3
"""Apply an ordered translation manifest to editable PowerPoint OOXML text."""

from __future__ import annotations

import argparse
import copy
import html
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from lxml import etree as LET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
CONTAINER_NAMES = {"sp", "graphicFrame", "cxnSp", "pic"}
SHAPE_RE = re.compile(
    r"<p:(?P<kind>sp|graphicFrame|cxnSp)(?:\s[^>]*)?>.*?</p:(?P=kind)>",
    re.DOTALL,
)
PARAGRAPH_RE = re.compile(r"<a:p(?:\s[^>]*)?>.*?</a:p>", re.DOTALL)
TEXT_RE = re.compile(r"(<a:t(?:\s[^>]*)?>)(.*?)(</a:t>)", re.DOTALL)
BREAK_SPLIT_RE = re.compile(
    r"(<a:br(?:\s[^>]*)?(?:/>|>.*?</a:br>))", re.DOTALL
)


class OoxmlError(RuntimeError):
    pass


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_text(text: str) -> str:
    return re.sub(r"[\r\n\v]+$", "", text).strip()


def register_source_namespaces(xml_bytes: bytes) -> None:
    for _, namespace in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = namespace
        if prefix != "xml":
            ET.register_namespace(prefix or "", uri)


def paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for element in paragraph.iter():
        if element.tag == f"{{{A_NS}}}t":
            parts.append(element.text or "")
        elif element.tag == f"{{{A_NS}}}br":
            parts.append("\v")
    return "".join(parts)


def paragraph_text_groups(paragraph: ET.Element) -> list[list[ET.Element]]:
    groups: list[list[ET.Element]] = [[]]
    for element in paragraph.iter():
        if element.tag == f"{{{A_NS}}}br":
            groups.append([])
        elif element.tag == f"{{{A_NS}}}t":
            groups[-1].append(element)
    return groups


def set_text_node(node: ET.Element, value: str) -> None:
    node.text = value
    space_key = f"{{{XML_NS}}}space"
    if value[:1].isspace() or value[-1:].isspace():
        node.set(space_key, "preserve")
    else:
        node.attrib.pop(space_key, None)


def replace_paragraph_text(paragraph: ET.Element, translation: str) -> None:
    groups = paragraph_text_groups(paragraph)
    all_nodes = [node for group in groups for node in group]
    if not all_nodes:
        raise OoxmlError("target paragraph contains no editable <a:t> text node")

    segments = re.split(r"\r\n|\r|\n|\v", translation)
    if len(segments) == len(groups) and all(groups):
        for group, segment in zip(groups, segments):
            set_text_node(group[0], segment)
            for node in group[1:]:
                set_text_node(node, "")
        return

    set_text_node(all_nodes[0], " ".join(segment for segment in segments if segment))
    for node in all_nodes[1:]:
        set_text_node(node, "")


def find_shape(root: ET.Element, shape_id: int) -> ET.Element | None:
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for c_nv_pr in root.iter(f"{{{P_NS}}}cNvPr"):
        if int(c_nv_pr.attrib.get("id", "-1")) != shape_id:
            continue
        current = c_nv_pr
        while current in parent_map:
            current = parent_map[current]
            if local_name(current.tag) in CONTAINER_NAMES:
                return current
    return None


def raw_paragraph_text(paragraph_xml: str) -> str:
    parts = BREAK_SPLIT_RE.split(paragraph_xml)
    text: list[str] = []
    for index, part in enumerate(parts):
        if index % 2:
            text.append("\v")
            continue
        text.extend(html.unescape(match.group(2)) for match in TEXT_RE.finditer(part))
    return "".join(text)


def replace_text_nodes(fragment: str, value: str) -> str:
    matches = list(TEXT_RE.finditer(fragment))
    if not matches:
        raise OoxmlError("target paragraph contains no editable <a:t> text node")
    escaped_value = escape(value)
    pieces: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        pieces.append(fragment[cursor : match.start()])
        replacement = escaped_value if index == 0 else ""
        opening = re.sub(r"\s+xml:space=([\"']).*?\1", "", match.group(1))
        if index == 0 and (value[:1].isspace() or value[-1:].isspace()):
            opening = opening[:-1] + ' xml:space="preserve">'
        pieces.append(opening + replacement + match.group(3))
        cursor = match.end()
    pieces.append(fragment[cursor:])
    updated = "".join(pieces)
    if re.search(r"[A-Za-z]", value):
        updated = re.sub(
            r"(<a:rPr\b[^>]*?)\s+spc=([\"'])-\d+\2",
            r"\1",
            updated,
            count=1,
        )
    return updated


def replace_raw_paragraph_text(paragraph_xml: str, translation: str) -> str:
    segments = re.split(r"\r\n|\r|\n|\v", translation)
    parts = BREAK_SPLIT_RE.split(paragraph_xml)
    text_group_indices = list(range(0, len(parts), 2))

    if len(segments) == len(text_group_indices) and all(
        TEXT_RE.search(parts[index]) for index in text_group_indices
    ):
        for index, segment in zip(text_group_indices, segments):
            parts[index] = replace_text_nodes(parts[index], segment)
        return "".join(parts)

    return replace_text_nodes(
        paragraph_xml, " ".join(segment for segment in segments if segment)
    )


def find_raw_shape(xml_text: str, shape_id: int) -> re.Match[str] | None:
    id_pattern = re.compile(
        rf"<p:cNvPr\b[^>]*\bid=(?P<quote>[\"']){shape_id}(?P=quote)(?:\s|/|>)"
    )
    for match in SHAPE_RE.finditer(xml_text):
        if id_pattern.search(match.group(0)):
            return match
    return None


def apply_items_to_slide(xml_bytes: bytes, items: list[dict]) -> bytes:
    xml_text = xml_bytes.decode("utf-8-sig")
    by_shape: dict[int, list[dict]] = {}
    for item in items:
        by_shape.setdefault(int(item["shape_id"]), []).append(item)

    for shape_id, shape_items in by_shape.items():
        shape_match = find_raw_shape(xml_text, shape_id)
        if shape_match is None:
            raise OoxmlError(f"shape id {shape_id} not found")
        shape_xml = shape_match.group(0)
        paragraphs = list(PARAGRAPH_RE.finditer(shape_xml))
        for item in sorted(
            shape_items,
            key=lambda value: int(
                value.get("package_paragraph_index", value["paragraph_index"])
            ),
            reverse=True,
        ):
            paragraph_index = int(
                item.get("package_paragraph_index", item["paragraph_index"])
            )
            if paragraph_index < 1 or paragraph_index > len(paragraphs):
                raise OoxmlError(
                    f"{item['id']}: paragraph {paragraph_index} not found"
                )
            paragraph_match = paragraphs[paragraph_index - 1]
            paragraph_xml = paragraph_match.group(0)
            actual = normalize_text(raw_paragraph_text(paragraph_xml))
            expected = normalize_text(str(item["source_text"]))
            if actual != expected:
                raise OoxmlError(
                    f"{item['id']}: source text mismatch; expected {expected!r}, got {actual!r}"
                )
            translation = str(item.get("translation", ""))
            if not translation.strip():
                raise OoxmlError(f"{item['id']}: empty translation")
            updated_paragraph = replace_raw_paragraph_text(paragraph_xml, translation)
            shape_xml = (
                shape_xml[: paragraph_match.start()]
                + updated_paragraph
                + shape_xml[paragraph_match.end() :]
            )
            paragraphs = list(PARAGRAPH_RE.finditer(shape_xml))

        xml_text = (
            xml_text[: shape_match.start()]
            + shape_xml
            + xml_text[shape_match.end() :]
        )

    result = xml_text.encode("utf-8")
    try:
        ET.fromstring(result)
    except ET.ParseError as exc:
        raise OoxmlError(f"translation produced invalid slide XML: {exc}") from exc
    return result


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OoxmlError(f"cannot read manifest {path}: {exc}") from exc
    if manifest.get("schema_version") != 2:
        raise OoxmlError("manifest schema_version must be 2")
    if not isinstance(manifest.get("occurrences"), list):
        raise OoxmlError("manifest contains no occurrences array")
    if not isinstance(manifest.get("translation_units"), list):
        raise OoxmlError("manifest contains no translation_units array")
    return manifest


def overlay_shape(root: ET.Element, overlay: dict, shape_id: int) -> bytes:
    """Create one editable shape without serializing or modifying its host."""
    label = f"overlay {overlay.get('id', '<missing>')}"
    try:
        if not overlay.get("id") or overlay.get("kind") != "office_overlay":
            raise ValueError("requires an id and kind office_overlay")
        if overlay.get("localization_mode") != "bilingual_below":
            raise ValueError("requires bilingual_below localization")
        if overlay.get("background", {}).get("mode") != "transparent":
            raise ValueError("bilingual overlays require a transparent background")
        translation = overlay.get("translation", "")
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError("translation is empty")
        host_id = int(overlay["location"]["host_shape_id"])
        host = find_shape(root, host_id)
        if host is None:
            raise ValueError(f"host shape {host_id} not found; choose an existing image shape")
        parents = {child: parent for parent in root.iter() for child in parent}
        if parents.get(host) is None or parents[host].tag != f"{{{P_NS}}}spTree":
            raise ValueError("grouped hosts are unsupported; use an ungrouped image host")
        if host.find(f".//{{{A_NS}}}blip") is None:
            raise ValueError("host contains no image")
        transform = host.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        if transform is None:
            raise ValueError("host has no explicit image transform; provide an ungrouped image")
        if int(transform.get("rot", "0")) % 21600000:
            raise ValueError("rotated host is unsupported; use an unrotated image")
        if any(transform.get(key, "0") not in {"0", "false"} for key in ("flipH", "flipV")):
            raise ValueError("flipped host is unsupported; use an unflipped image")
        offset, extent = transform.find(f"{{{A_NS}}}off"), transform.find(f"{{{A_NS}}}ext")
        if offset is None or extent is None:
            raise ValueError("host has incomplete geometry")
        host_x, host_y = int(offset.get("x")), int(offset.get("y"))
        host_w, host_h = int(extent.get("cx")), int(extent.get("cy"))
        if min(host_w, host_h) <= 0:
            raise ValueError("host has nonpositive dimensions")
        regions = {}
        for region_name in ("source_region", "region"):
            region = overlay[region_name]
            values = [region[key] for key in ("x", "y", "w", "h")]
            if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
                raise ValueError(f"{region_name} must contain finite normalized coordinates")
            x, y, w, h = values
            if x < 0 or y < 0 or min(w, h) <= 0 or x + w > 1.000000001 or y + h > 1.000000001:
                raise ValueError(f"{region_name} lies outside its host; adjust the region")
            regions[region_name] = values
        sx, sy, sw, sh = regions["source_region"]
        x, y, w, h = regions["region"]
        if y < sy + sh - 1e-9:
            raise ValueError("translation region must be below the source label")
        style = overlay["style"]
        size = style["font_size_pt"]
        if type(size) not in (int, float) or not math.isfinite(size) or not 1 <= size <= 4000:
            raise ValueError("font_size_pt must be between 1 and 4000")
        if not isinstance(style.get("bold"), bool) or not str(style.get("font_name", "")).strip():
            raise ValueError("font_name and boolean bold are required")
        color = style["text_rgb"]
        if not isinstance(color, str) or not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
            raise ValueError("text_rgb must be a six-digit RGB value")
        align = {"left": "l", "center": "ctr", "right": "r"}[style["align"]]

        def child(parent, namespace, tag, **attributes):
            return LET.SubElement(parent, f"{{{namespace}}}{tag}", {key: str(value) for key, value in attributes.items()})

        shape = LET.Element(f"{{{P_NS}}}sp", nsmap={"p": P_NS, "a": A_NS})
        nv = child(shape, P_NS, "nvSpPr")
        child(nv, P_NS, "cNvPr", id=shape_id, name="office-translate-overlay:" + overlay["id"])
        child(nv, P_NS, "cNvSpPr", txBox="1")
        child(nv, P_NS, "nvPr")
        properties = child(shape, P_NS, "spPr")
        transform = child(properties, A_NS, "xfrm")
        child(transform, A_NS, "off", x=round(host_x + x * host_w), y=round(host_y + y * host_h))
        child(transform, A_NS, "ext", cx=max(1, round(w * host_w)), cy=max(1, round(h * host_h)))
        child(child(properties, A_NS, "prstGeom", prst="rect"), A_NS, "avLst")
        child(properties, A_NS, "noFill")
        child(child(properties, A_NS, "ln"), A_NS, "noFill")
        body = child(shape, P_NS, "txBody")
        body_properties = child(body, A_NS, "bodyPr", wrap="square", lIns=0, tIns=0, rIns=0, bIns=0, anchor="t")
        child(body_properties, A_NS, "noAutofit")
        child(body, A_NS, "lstStyle")
        for line in re.split(r"\r\n|\r|\n|\v", translation):
            paragraph = child(body, A_NS, "p")
            child(paragraph, A_NS, "pPr", algn=align)
            run = child(paragraph, A_NS, "r")
            run_properties = child(run, A_NS, "rPr", sz=round(size * 100), b=int(style["bold"]))
            child(child(run_properties, A_NS, "solidFill"), A_NS, "srgbClr", val=color.upper())
            for script in ("latin", "ea", "cs"):
                child(run_properties, A_NS, script, typeface=style["font_name"])
            node = child(run, A_NS, "t")
            node.text = line
            if line[:1].isspace() or line[-1:].isspace():
                node.set(f"{{{XML_NS}}}space", "preserve")
        return LET.tostring(shape, encoding="utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        raise OoxmlError(f"{label}: {exc}") from exc


def apply_overlays_to_slide(xml_bytes: bytes, overlays: list[dict]) -> bytes:
    root = ET.fromstring(xml_bytes)
    next_id = max((int(node.get("id", "0")) for node in root.iter(f"{{{P_NS}}}cNvPr")), default=0) + 1
    existing_names = {node.get("name") for node in root.iter(f"{{{P_NS}}}cNvPr")}
    shapes = []
    for overlay in overlays:
        if "office-translate-overlay:" + str(overlay.get("id")) in existing_names:
            raise OoxmlError(f"overlay {overlay['id']}: already exists; apply to the working source")
        shapes.append(overlay_shape(root, overlay, next_id))
        next_id += 1
    # Insert before the tree's extension list, which OOXML requires to be last.
    match = re.search(rb"<p:spTree\b[^>]*>(.*?)</p:spTree\s*>", xml_bytes, re.DOTALL)
    if match is None:
        raise OoxmlError("overlay slide requires a p:spTree element")
    tree = LET.fromstring(xml_bytes).find(f".//{{{P_NS}}}spTree")
    insertion = match.end(1)
    if tree is not None and len(tree) and tree[-1].tag == f"{{{P_NS}}}extLst":
        insertion = xml_bytes.rfind(b"<p:extLst", match.start(1), insertion)
        if insertion < 0:
            raise OoxmlError("cannot locate slide shape-tree extension list")
    result = xml_bytes[:insertion] + b"".join(shapes) + xml_bytes[insertion:]
    ET.fromstring(result)
    return result


def apply_manifest(input_path: Path, manifest_path: Path, output_path: Path) -> dict:
    if input_path.resolve() == output_path.resolve():
        raise OoxmlError("refusing to overwrite the source presentation")
    if not input_path.is_file():
        raise OoxmlError(f"input file not found: {input_path}")

    manifest = load_manifest(manifest_path)
    protected_paths = [manifest_path]
    for key in ("source_path", "working_source_path"):
        if manifest.get(key):
            protected_paths.append(Path(manifest[key]))
    if any(output_path.resolve() == path.resolve() or
           (output_path.exists() and path.exists() and os.path.samefile(output_path, path))
           for path in [input_path, *protected_paths]):
        raise OoxmlError("refusing to overwrite the source, working source, or manifest")
    units: dict[str, dict] = {}
    for unit in manifest["translation_units"]:
        unit_id = str(unit.get("id", ""))
        if not unit_id or unit_id in units:
            raise OoxmlError(f"invalid or duplicate translation unit id: {unit_id!r}")
        translation = str(unit.get("translation", ""))
        if not translation.strip():
            raise OoxmlError(f"translation unit {unit_id!r} has an empty translation")
        units[unit_id] = unit

    items_by_slide: dict[int, list[dict]] = {}
    for occurrence in manifest["occurrences"]:
        unit_id = str(occurrence.get("translation_unit_id", ""))
        unit = units.get(unit_id)
        if unit is None:
            raise OoxmlError(
                f"{occurrence.get('id', 'unknown')}: unknown translation unit {unit_id!r}"
            )
        if str(occurrence.get("source_text", "")) != str(unit.get("source_text", "")):
            raise OoxmlError(
                f"{occurrence.get('id', 'unknown')}: source text differs from translation unit"
            )
        resolved = dict(occurrence)
        resolved["translation"] = unit["translation"]
        items_by_slide.setdefault(int(resolved["slide_index"]), []).append(resolved)

    overlays_by_slide: dict[int, list[dict]] = {}
    overlay_ids = set()
    for overlay in manifest.get("overlays", []):
        label = overlay.get("id", "<missing>")
        if label in overlay_ids:
            raise OoxmlError(f"overlay {label}: duplicate id")
        overlay_ids.add(label)
        try:
            slide_index = int(overlay["location"]["page_or_slide"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OoxmlError(f"overlay {label}: invalid slide location") from exc
        overlays_by_slide.setdefault(slide_index, []).append(overlay)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    replaced = 0
    with zipfile.ZipFile(input_path, "r") as source:
        source_entries = source.infolist()
        source_names = {entry.filename for entry in source_entries}
        expected_slides = {
            f"ppt/slides/slide{slide_index}.xml" for slide_index in items_by_slide.keys() | overlays_by_slide.keys()
        }
        missing_slides = sorted(expected_slides - source_names)
        if missing_slides:
            raise OoxmlError(f"missing slide XML: {', '.join(missing_slides)}")

        fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary, "w", allowZip64=True) as target:
                target.comment = source.comment
                for entry in source_entries:
                    payload = source.read(entry.filename)
                    match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", entry.filename)
                    if match:
                        slide_index = int(match.group(1))
                        slide_items = items_by_slide.get(slide_index)
                        if slide_items:
                            payload = apply_items_to_slide(payload, slide_items)
                            replaced += len(slide_items)
                        slide_overlays = overlays_by_slide.get(slide_index)
                        if slide_overlays:
                            payload = apply_overlays_to_slide(payload, slide_overlays)
                    target.writestr(copy.copy(entry), payload)
            temporary.replace(output_path)
        finally:
            temporary.unlink(missing_ok=True)

    return {
        "occurrences": len(manifest["occurrences"]),
        "translation_units": len(manifest["translation_units"]),
        "replaced": replaced,
        "image_overlays": sum(map(len, overlays_by_slide.values())),
        "preserved_parts": manifest.get("preserved_parts", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--input", required=True, type=Path)
    apply_parser.add_argument("--manifest", required=True, type=Path)
    apply_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        summary = apply_manifest(args.input, args.manifest, args.output)
    except (OoxmlError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"OOXML error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
