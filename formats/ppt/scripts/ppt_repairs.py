"""Deterministic repairs for a verified PowerPoint translation package.

Every subcommand rewrites only the parts it is asked to change and copies every other
part byte-for-byte from the input package, because `ppt_pipeline.py verify` compares all
non-slide package parts against the recorded working source and rejects any other change.

Subcommands
  scan-text          byte-level probe for source-language text still present in package parts
  strip-ole-preview  remove a stale legacy OLE/VML preview that hides a translated slide
  amend-baseline     record the removal as an explicit working-source amendment for the job
  fit-text           tighten paragraph leading so translated text clears the slide frame
  measure-fit        measure rendered ink extent and suggest a leading percentage
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable

from lxml import etree

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

CONTENT_TYPES = "[Content_Types].xml"
TEXT_PARTS = re.compile(r"\.(xml|rels|vml)$", re.IGNORECASE)
PREVIEW_SUFFIXES = {".emf", ".wmf", ".png", ".jpeg", ".jpg", ".gif", ".bmp"}
# Compressed raster payloads match arbitrary CJK byte pairs by chance, so probing them is noise.
RASTER_SUFFIXES = {".png", ".jpeg", ".jpg", ".gif", ".bmp", ".tif", ".tiff"}


class RepairError(RuntimeError):
    """Raised when a repair cannot be applied safely."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_parts(path: Path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as package:
        return [(item.filename, package.read(item.filename)) for item in package.infolist()]


def write_parts(path: Path, parts: Iterable[tuple[str, bytes]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in parts:
            package.writestr(name, data)
    tmp.replace(path)


def slide_names(index: int) -> tuple[str, str]:
    return f"ppt/slides/slide{index}.xml", f"ppt/slides/_rels/slide{index}.xml.rels"


def resolve_target(base_dir: str, target: str) -> str:
    if target.startswith("../"):
        resolved = str(Path(base_dir).parent / target[3:])
    elif target.startswith("/"):
        resolved = target[1:]
    else:
        resolved = str(Path(base_dir) / target)
    resolved = resolved.replace("\\", "/")
    while "/./" in resolved:
        resolved = resolved.replace("/./", "/")
    return resolved


def rels_targets(package: dict[str, bytes], rels_name: str) -> dict[str, str]:
    """Map relationship id -> resolved package part for one .rels part."""
    if rels_name not in package:
        return {}
    base_dir = rels_name.rsplit("/_rels/", 1)[0]
    root = etree.fromstring(package[rels_name])
    found: dict[str, str] = {}
    for node in root.findall(REL + "Relationship"):
        if node.get("TargetMode") == "External":
            continue
        found[node.get("Id")] = resolve_target(base_dir, node.get("Target", ""))
    return found


def vml_rels_name(vml_part: str) -> str:
    """Companion .rels part of a VML drawing; built textually so separators stay POSIX."""
    folder, _, name = vml_part.rpartition("/")
    return f"{folder}/_rels/{name}.rels"


def referenced_vml_parts(package: dict[str, bytes], exclude: str = "") -> set[str]:
    """VML drawings that other slides still point at, outwith the slide being repaired."""
    used: set[str] = set()
    for name in package:
        if name == exclude or not name.startswith("ppt/slides/_rels/") or not name.endswith(".rels"):
            continue
        used.update(target for target in rels_targets(package, name).values()
                    if target.endswith(".vml"))
    return used


# --------------------------------------------------------------------------- scan-text


def command_scan_text(args: argparse.Namespace) -> int:
    probes = [probe for probe in args.probe if probe]
    if not probes:
        raise RepairError("scan-text needs at least one --probe")
    report = []
    for name, data in read_parts(args.package):
        if not args.include_xml and TEXT_PARTS.search(name):
            continue
        if not args.include_raster and Path(name).suffix.lower() in RASTER_SUFFIXES:
            continue
        hits = []
        for probe in probes:
            for label, encoding in (("utf-16-le", "utf-16-le"), ("utf-8", "utf-8")):
                count = data.count(probe.encode(encoding))
                if count:
                    hits.append({"probe": probe, "encoding": label, "count": count})
        if hits:
            report.append({"part": name, "bytes": len(data), "sha256": sha256(data), "hits": hits})
    print(json.dumps({"package": str(args.package), "probes": probes,
                      "parts_with_source_text": report}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ strip-ole-preview


def command_strip_ole_preview(args: argparse.Namespace) -> int:
    parts = read_parts(args.output)
    package = dict(parts)
    slide_part, slide_rels = slide_names(args.slide)
    if slide_part not in package:
        raise RepairError(f"{slide_part} not found in {args.output}")

    root = etree.fromstring(package[slide_part])
    tree = root.find(f"{P}cSld/{P}spTree")
    if tree is None:
        raise RepairError(f"{slide_part}: no spTree")

    anchor = None
    for child in tree:
        if any(nv.get("id") == str(args.shape_id) for nv in child.iter(P + "cNvPr")):
            anchor = child
            break
    if anchor is None:
        raise RepairError(f"shape {args.shape_id} not found on slide {args.slide}")

    slide_map = rels_targets(package, slide_rels)
    rel_ids = set()
    ole_like = False
    for element in anchor.iter():
        if element.tag.endswith("}oleObj") or element.tag.endswith("}OLEObject"):
            ole_like = True
        for key, value in element.attrib.items():
            if key.startswith(RID) or key.endswith("}relid"):
                rel_ids.add(value)

    removed: set[str] = set()
    queue = [slide_map[rid] for rid in rel_ids if rid in slide_map]

    # A legacy OLE shape renders its preview through a separate VML drawing that the slide
    # references but the shape XML does not name, so pull in the unreferenced VML chain too.
    if ole_like:
        still_used = referenced_vml_parts(package, exclude=slide_rels)
        for target in slide_map.values():
            if target.endswith(".vml") and target not in still_used:
                queue.append(target)

    while queue:
        part = queue.pop()
        if part in removed or part not in package:
            continue
        removed.add(part)
        if part.endswith(".vml"):
            rels_name = vml_rels_name(part)
            if rels_name in package:
                removed.add(rels_name)
                queue.extend(rels_targets(package, rels_name).values())
        elif Path(part).suffix.lower() in PREVIEW_SUFFIXES:
            pass  # preview media belongs to the removed object

    if ole_like and not removed:
        raise RepairError("no OLE parts resolved; pass --only-parts explicitly")

    prog_id = ""
    for element in anchor.iter():
        if element.tag.endswith("}OLEObject") or element.tag.endswith("}oleObj"):
            prog_id = element.get("ProgID") or element.get("progId") or prog_id
    if not prog_id:
        # A legacy VML shape carries the ProgID when the slide XML only holds a picture.
        for name in sorted(removed):
            if name.endswith(".vml"):
                for element in etree.fromstring(package[name]).iter():
                    if element.tag.endswith("}OLEObject"):
                        prog_id = element.get("ProgID", "") or prog_id

    if args.protect and (set(args.protect) & removed):
        raise RepairError(f"refusing to remove protected parts: {sorted(set(args.protect) & removed)}")

    report = {
        "package": str(args.output),
        "slide": args.slide,
        "shape_id": str(args.shape_id),
        "shape_name": anchor.find(f"{P}nvGraphicFramePr/{P}cNvPr") is not None and
                      (anchor.find(f"{P}nvGraphicFramePr/{P}cNvPr").get("name", "")),
        "prog_id": prog_id,
        "element_removed": etree.QName(anchor).localname,
        "ole_like": ole_like,
        "removed_parts": [{"part": name, "bytes": len(package[name]),
                           "sha256": sha256(package[name])} for name in sorted(removed)],
        "removed_relationship_ids": sorted(rel_ids),
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False))
        return 0

    # Slide: drop the whole container so neither the OLE path nor its picture fallback
    # can re-render the untranslated preview.
    tree.remove(anchor)

    # Slide relationships: drop entries that pointed at removed parts.
    if slide_rels in package:
        rels_root = etree.fromstring(package[slide_rels])
        dropped = []
        for node in list(rels_root.findall(REL + "Relationship")):
            if slide_map.get(node.get("Id")) in removed:
                dropped.append(node.get("Id"))
                rels_root.remove(node)
        package[slide_rels] = etree.tostring(rels_root, xml_declaration=True,
                                             encoding="UTF-8", standalone=True)
        report["removed_relationship_ids"] = dropped

    # Content types: drop overrides for removed parts; defaults stay untouched.
    if CONTENT_TYPES in package:
        ct_root = etree.fromstring(package[CONTENT_TYPES])
        overrides = []
        for node in list(ct_root.findall(CT + "Override")):
            part_name = (node.get("PartName") or "").lstrip("/")
            if part_name in removed:
                overrides.append(part_name)
                ct_root.remove(node)
        package[CONTENT_TYPES] = etree.tostring(ct_root, xml_declaration=True,
                                                encoding="UTF-8", standalone=True)
        report["removed_content_type_overrides"] = overrides

    package[slide_part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                         standalone=True)
    write_parts(args.output, [(name, package[name]) for name, _ in parts if name not in removed])
    report["output_sha256"] = sha256(Path(args.output).read_bytes())
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


# -------------------------------------------------------------------- amend-baseline


def command_amend_baseline(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    removed = [item["part"] for item in report.get("removed_parts", [])]
    if not removed:
        raise RepairError("amendment report lists no removed parts")

    inventory_path = Path(args.job_dir) / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    original = Path(args.working_source or inventory["working_source_path"])
    amended = Path(args.amended or (original.parent / "working-source-amended.pptx"))
    deck = dict(read_parts(args.deck))

    structural = {CONTENT_TYPES, slide_names(report["slide"])[1]}
    parts = []
    for name, data in read_parts(original):
        if name in removed:
            continue
        parts.append((name, deck.get(name, data) if name in structural else data))
    write_parts(amended, parts)

    inventory["working_source_path"] = str(amended)
    inventory["working_source_sha256"] = sha256(amended.read_bytes())
    inventory["baseline_amendment"] = {
        "reason": args.reason,
        "original_working_source": {"path": str(original), "sha256": sha256(original.read_bytes())},
        "amended_working_source": {"path": str(amended), "sha256": sha256(amended.read_bytes())},
        "deck": str(args.deck),
        "removed_parts": report.get("removed_parts", []),
        "removed_embedded_objects": report.get("removed_embedded_objects", []),
        "deltas_allowed_by_verify": sorted(structural | {slide_names(report["slide"])[0]}),
    }
    inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    amendment = Path(args.job_dir) / "baseline-amendment.json"
    amendment.write_text(json.dumps(inventory["baseline_amendment"], ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(json.dumps({"amended_working_source": str(amended),
                      "sha256": inventory["working_source_sha256"],
                      "removed_parts": len(removed),
                      "amendment": str(amendment)}, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------------- fit-text


def _paragraphs(slide_bytes: bytes, shape_id: str) -> tuple[etree._Element, list]:
    root = etree.fromstring(slide_bytes)
    for shape in root.iter(P + "sp"):
        nv = shape.find(f"{P}nvSpPr/{P}cNvPr")
        if nv is not None and nv.get("id") == str(shape_id):
            body = shape.find(f"{P}txBody")
            if body is None:
                raise RepairError(f"shape {shape_id} has no text body")
            return root, body.findall(A + "p")
    raise RepairError(f"shape {shape_id} not found")


def command_fit_text(args: argparse.Namespace) -> int:
    parts = read_parts(args.output)
    package = dict(parts)
    leading = [int(value) for value in str(args.leading).split(",")]
    slide_part, _ = slide_names(args.slide)
    root, paragraphs = _paragraphs(package[slide_part], args.shape_id)

    before, after = [], []
    for index, paragraph in enumerate(paragraphs):
        percent = leading[min(index, len(leading) - 1)]
        if percent < 40 or percent > 400:
            raise RepairError(f"leading out of range: {percent}")
        pPr = paragraph.find(A + "pPr")
        if pPr is None:
            pPr = etree.Element(A + "pPr")
            paragraph.insert(0, pPr)
        node = pPr.find(A + "lnSpc")
        if node is None:
            node = etree.Element(A + "lnSpc")
            pPr.insert(0, node)  # schema order: lnSpc is the first pPr child
        existing = node.find(A + "spcPct")
        before.append(existing.get("val") if existing is not None else None)
        for child in list(node):
            node.remove(child)
        etree.SubElement(node, A + "spcPct").set("val", str(percent * 1000))
        after.append(str(percent * 1000))

    package[slide_part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                         standalone=True)
    write_parts(args.output, [(name, package[name]) for name, _ in parts])
    print(json.dumps({"package": str(args.output), "slide": args.slide,
                      "shape_id": str(args.shape_id), "leading_before": before,
                      "leading_after": after,
                      "output_sha256": sha256(Path(args.output).read_bytes())},
                     ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------- measure-fit


def command_measure_fit(args: argparse.Namespace) -> int:
    import numpy as np
    from PIL import Image

    image = Image.open(args.render).convert("L")
    width, height = image.size
    window = np.asarray(image, dtype=np.int16)[:, int(width * args.x0):int(width * args.x1)]
    rows = ((window < args.dark).sum(axis=1) > args.min_pixels) | \
           ((window > args.light).sum(axis=1) > args.min_pixels)
    index = np.nonzero(rows)[0]
    if not len(index):
        raise RepairError("no text rows detected in the requested window")
    scale = args.slide_height / height
    ink_bottom = int((index.max() + 1) * scale)
    result = {
        "render": str(args.render),
        "ink_top_emu": int(index.min() * scale),
        "ink_bottom_emu": ink_bottom,
        "slide_height_emu": args.slide_height,
        "clears_frame": ink_bottom <= args.target_emu,
    }
    if args.box_top_emu:
        span = ink_bottom - args.box_top_emu
        wanted = args.target_emu - args.box_top_emu
        result["needed_scale"] = round(wanted / span, 3)
        if args.current_leading:
            result["suggested_leading_percent"] = max(
                40, int(args.current_leading * wanted / span) - 2)
    print(json.dumps(result, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------------------ cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan-text", help="probe packages for residual source-language text")
    scan.add_argument("--package", type=Path, required=True)
    scan.add_argument("--probe", action="append", default=[],
                      help="source-language word to look for; repeatable")
    scan.add_argument("--include-xml", action="store_true")
    scan.add_argument("--include-raster", action="store_true",
                      help="also probe compressed raster media (results are unreliable)")
    scan.set_defaults(func=command_scan_text)

    strip = sub.add_parser("strip-ole-preview", help="remove a stale legacy OLE preview")
    strip.add_argument("--output", type=Path, required=True)
    strip.add_argument("--slide", type=int, required=True)
    strip.add_argument("--shape-id", required=True)
    strip.add_argument("--report", type=Path)
    strip.add_argument("--protect", action="append", default=[],
                       help="part name that must never be removed; repeatable")
    strip.add_argument("--dry-run", action="store_true")
    strip.set_defaults(func=command_strip_ole_preview)

    amend = sub.add_parser("amend-baseline", help="record the removal in the job baseline")
    amend.add_argument("--job-dir", type=Path, required=True)
    amend.add_argument("--deck", type=Path, required=True)
    amend.add_argument("--report", type=Path, required=True)
    amend.add_argument("--working-source", type=Path)
    amend.add_argument("--amended", type=Path)
    amend.add_argument("--reason", required=True)
    amend.set_defaults(func=command_amend_baseline)

    fit = sub.add_parser("fit-text", help="tighten paragraph leading on one shape")
    fit.add_argument("--output", type=Path, required=True)
    fit.add_argument("--slide", type=int, required=True)
    fit.add_argument("--shape-id", required=True)
    fit.add_argument("--leading", required=True,
                     help="leading percentage, comma separated per paragraph (e.g. 90 or 105,115)")
    fit.set_defaults(func=command_fit_text)

    measure = sub.add_parser("measure-fit", help="measure rendered ink extent")
    measure.add_argument("--render", type=Path, required=True)
    measure.add_argument("--x0", type=float, default=0.0)
    measure.add_argument("--x1", type=float, default=1.0)
    measure.add_argument("--slide-height", type=int, default=6858000)
    measure.add_argument("--box-top-emu", type=int)
    measure.add_argument("--target-emu", type=int, default=6200000)
    measure.add_argument("--current-leading", type=int)
    measure.add_argument("--dark", type=int, default=90)
    measure.add_argument("--light", type=int, default=235)
    measure.add_argument("--min-pixels", type=int, default=25)
    measure.set_defaults(func=command_measure_fit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RepairError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
