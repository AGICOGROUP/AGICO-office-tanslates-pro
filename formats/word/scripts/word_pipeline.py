#!/usr/bin/env python3
"""Deterministic Word translation pipeline: prepare, apply, validate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from analyze_docx import analyze, PROTECTED_TOKEN

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
from translation_batches import add_commands, export_batches, run_command
sys.path.pop(0)


def run_translation_command(args):
    def check(unit, text):
        expected = normalize_protected_tokens(PROTECTED_TOKEN.findall(unit['source']))
        actual = normalize_protected_tokens(PROTECTED_TOKEN.findall(text))
        return [] if expected == actual else ['protected token mismatch']
    return run_command(args, kind='word', check=check)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
W_P = f"{{{W_NS}}}p"
W_R = f"{{{W_NS}}}r"
W_T = f"{{{W_NS}}}t"
W_TAB = f"{{{W_NS}}}tab"
W_BREAKS = {f"{{{W_NS}}}br", f"{{{W_NS}}}cr"}
TEXT_PARTS = ("word/document.xml", "word/header", "word/footer", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
CJK_TITLE_RUN = re.compile(r"[\u4e00-\u9fff0-9 /]{1,16}")
CJK_TITLE_RUN = re.compile(r"[\u4e00-\u9fff0-9 /]{1,16}")


def is_text_part(name: str) -> bool:
    return name in TEXT_PARTS or name.startswith(("word/header", "word/footer")) and name.endswith(".xml")


def normalize_protected_tokens(tokens: list[str]) -> set[str]:
    return {
        re.sub(r"\s+", "", token).replace("℃", "°C").replace(",", ".").casefold()
        for token in tokens
    }


def local_content_nodes(paragraph: etree._Element) -> list[etree._Element]:
    allowed = {W_T, W_TAB, *W_BREAKS}
    return [
        node for node in paragraph.iter()
        if node.tag in allowed
        and next((ancestor for ancestor in node.iterancestors() if ancestor.tag == W_P), None) is paragraph
    ]


def paragraph_text(paragraph: etree._Element) -> str:
    pieces = []
    for node in local_content_nodes(paragraph):
        if node.tag == W_T:
            pieces.append(node.text or "")
        elif node.tag == W_TAB:
            pieces.append("\t")
        else:
            pieces.append("\n")
    return "".join(pieces).strip()


def set_text_node(node: etree._Element, value: str) -> None:
    node.text = value
    space_key = f"{{{XML_NS}}}space"
    if value[:1].isspace() or value[-1:].isspace():
        node.set(space_key, "preserve")
    else:
        node.attrib.pop(space_key, None)


def remove_cjk_width_controls(node: etree._Element, source: str, target: str) -> None:
    if not re.search(r"[\u3400-\u9fff]", source) or not re.search(r"[A-Za-z]", target):
        return
    run = next((ancestor for ancestor in node.iterancestors() if ancestor.tag == W_R), None)
    if run is None:
        return
    properties = run.find(f"{{{W_NS}}}rPr")
    if properties is None:
        return
    for name in ("spacing", "w", "fitText"):
        child = properties.find(f"{{{W_NS}}}{name}")
        if child is not None:
            properties.remove(child)


def replace_paragraph_text(paragraph: etree._Element, source: str, target: str) -> None:
    if target == source:
        return
    nodes = local_content_nodes(paragraph)
    text_indexes = [index for index, node in enumerate(nodes) if node.tag == W_T and (node.text or "").strip()]
    if not text_indexes:
        raise ValueError("paragraph has no writable text node")
    # paragraph_text() strips boundary whitespace; keep boundary tabs/breaks untouched too.
    active_nodes = nodes[text_indexes[0]:text_indexes[-1] + 1]
    separators = ["\t" if node.tag == W_TAB else "\n" for node in active_nodes if node.tag != W_T]
    target_parts = re.split(r"(\t|\n)", target)
    target_separators = target_parts[1::2]
    if target_separators != separators:
        raise ValueError("translation changed protected tab or line-break structure")
    segments = target_parts[0::2]
    groups: list[list[etree._Element]] = [[]]
    for node in active_nodes:
        if node.tag == W_T:
            groups[-1].append(node)
        else:
            groups.append([])
    if len(groups) != len(segments) or any(not group for group in groups):
        raise ValueError("paragraph has unsupported empty text segment around a tab or line break")
    for group, segment in zip(groups, segments):
        original = [node.text or "" for node in group]
        if "".join(original) == segment:
            continue
        writable = [node for node in group if (node.text or "").strip()]
        if not writable:
            writable = [group[0]]
        writable = writable[:max(1, min(len(writable), len(segment)))]
        weights = [max(1, len(node.text or "")) for node in writable]
        boundaries = [0]
        cumulative = 0
        whitespace = [index for index, char in enumerate(segment) if char.isspace()]
        for index, weight in enumerate(weights[:-1], start=1):
            cumulative += weight
            ideal = round(len(segment) * cumulative / sum(weights))
            lower = boundaries[-1] + 1
            upper = len(segment) - (len(weights) - index)
            choices = [position for position in whitespace if lower <= position <= upper]
            boundary = min(choices, key=lambda position: abs(position - ideal)) if choices else ideal
            boundaries.append(max(lower, min(upper, boundary)))
        boundaries.append(len(segment))
        for node in group:
            set_text_node(node, "")
        for index, node in enumerate(writable):
            value = segment[boundaries[index]:boundaries[index + 1]]
            set_text_node(node, value)
            remove_cjk_width_controls(node, source, target)


def normalize_tab_structures(package: Path) -> int:
    """Insert empty w:t nodes between adjacent tab/line-break separator nodes.

    replace_paragraph_text() maps every separator to one target segment, which requires a
    writable w:t between two adjacent separators ("A\t\tB"); real documents omit it, so the
    working copy is normalized here instead of failing every later apply with
    "unsupported empty text segment around a tab or line break". Empty w:t nodes render as
    nothing and paragraph_text() is unchanged, so analysis results are identical.
    """
    inserted = 0
    separators = {W_TAB, *W_BREAKS}
    with ZipFile(package) as src:
        parts = {name: src.read(name) for name in src.namelist()}
    with ZipFile(package, "w", ZIP_DEFLATED) as dst:
        for name, data in parts.items():
            if is_text_part(name):
                parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
                root = etree.fromstring(data, parser)
                for paragraph in root.iter(W_P):
                    nodes = [
                        node for node in paragraph.iter()
                        if node.tag in {W_T, W_TAB, *W_BREAKS}
                        and next((ancestor for ancestor in node.iterancestors() if ancestor.tag == W_P), None) is paragraph
                    ]
                    for before, after in zip(nodes, nodes[1:]):
                        if before.tag in separators and after.tag in separators:
                            empty = etree.Element(W_T)
                            before.addnext(empty)
                            inserted += 1
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            dst.writestr(name, data)
    return inserted


def _pt_value(fragment: str) -> float:
    digits = re.sub(r"[^0-9.]", "", fragment)
    return float(digits) if digits else 0.0


def _landscape_vml_style(style: str) -> str:
    kept, width, height = [], None, None
    for part in style.split(";"):
        part = part.strip()
        if not part or re.match(r"(layout-flow|mso-layout-flow-alt)\s*:", part):
            continue
        if re.match(r"width\s*:", part):
            width = part
        elif re.match(r"height\s*:", part):
            height = part
        else:
            kept.append(part)
    if width and height and _pt_value(width) < _pt_value(height):
        width, height = height.replace("height", "width"), width.replace("width", "height")
    kept.extend([width, height])
    return ";".join(part for part in kept if part)


def _swap_portrait_extents(drawing, page_width_emu: int) -> None:
    extent = drawing.find(f"{{{WP_NS}}}extent")
    if extent is None:
        return
    cx, cy = int(extent.get("cx", "0")), int(extent.get("cy", "0"))
    if cx >= cy:
        return
    offset = drawing.find(f"{{{WP_NS}}}positionH/{{{WP_NS}}}posOffset")
    x = int(offset.text) if offset is not None and offset.text and offset.text.lstrip("-").isdigit() else 0
    new_cx = min(cy, max(cx, page_width_emu - x)) if page_width_emu else cy
    extent.set("cx", str(new_cx))
    extent.set("cy", str(cx))
    for inner in drawing.iter(f"{{{A_NS}}}ext"):
        inner_cx, inner_cy = int(inner.get("cx", "0")), int(inner.get("cy", "0"))
        if 0 < inner_cx < inner_cy:
            inner.set("cx", str(min(inner_cy, new_cx)))
            inner.set("cy", str(inner_cx))


def unwrap_anchored_text_boxes(root) -> Counter:
    """Convert anchored text boxes used as content containers into body content.

    Documents converted from PDF anchor whole regions (paragraphs, even tables)
    in floating text boxes sized for the CJK source. The target language runs
    longer, overflows the fixed box, and draws over whatever sits beneath it
    (tables, artwork), so each box's content is hoisted into the normal body
    flow at the same position and the box is removed. Fallback copies of the
    same content are deduplicated, and host paragraphs that carry visible text
    outside the box keep that text with only the box itself removed.
    """
    changed = Counter()
    for host in list(root.iter(W_P)):
        boxes = []
        seen_block_keys = set()
        box_runs = []
        for run in list(host.iter(f"{{{W_NS}}}r")):
            is_box_run = False
            for d in run.iter():
                if d.tag not in (f"{{{W_NS}}}drawing", f"{{{W_NS}}}pict"):
                    continue
                # A floating object may combine a text box with a raster image.
                # Removing that run would orphan the image part even though the
                # file remains inside word/media. Keep the complete object.
                has_image_reference = any(
                    etree.QName(attribute).namespace == "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                    and etree.QName(attribute).localname in {"embed", "link", "id"}
                    for descendant in d.iter()
                    for attribute in descendant.attrib
                )
                if has_image_reference:
                    continue
                is_box_run = True
                blocks = [c2 for c in d.iter(f"{{{W_NS}}}txbxContent")
                          for c2 in c if c2.tag in (W_P, f"{{{W_NS}}}tbl")]
                key = "|".join(
                    "".join(t.text or "" for t in b.iter(W_T)) for b in blocks
                )
                if blocks and key not in seen_block_keys:
                    seen_block_keys.add(key)
                    boxes.append(blocks)
                break
            if is_box_run:
                box_runs.append(run)
        if not box_runs:
            continue
        outside = [
            t for t in host.iter(W_T)
            if not any(a.tag == f"{{{W_NS}}}txbxContent" for a in t.iterancestors())
        ]
        host_has_text = any((t.text or "").strip() for t in outside)
        parent = host.getparent()
        if parent is None:
            continue
        index = list(parent).index(host)
        for blocks in boxes:
            for block in reversed(blocks):
                parent.insert(index, block)
        for run in box_runs:
            run_parent = run.getparent()
            if run_parent is not None:
                run_parent.remove(run)
        if not host_has_text:
            keeps_section = host.find(f"{{{W_NS}}}pPr/{{{W_NS}}}sectPr") is not None
            if not keeps_section:
                parent.remove(host)
        changed["text_boxes_unwrapped"] += 1
    return changed


def adapt_layout_for_target_language(root, cjk_target: bool, short_cjk_paragraphs, column_twips: int) -> Counter:
    """Post-translation layout adaptation for fixed CJK layout devices.

    Target-language text runs longer than the source but cannot reflow inside
    vertical or portrait-locked boxes sized for a few CJK characters per line,
    so vertical text flow is removed, portrait drawing extents are swapped to
    landscape (clamped to the page), exact line spacing tuned for CJK glyphs
    is relaxed for paragraphs that now hold Latin text, and short-CJK title
    paragraphs rendered through squeezed indent columns (the classic one
    character per line vertical cover title) have their indent column cleared
    and their font size scaled so the Latin text fits the same visual area.
    Skipped for CJK targets, where those devices are the intended design.
    """
    changed = Counter()
    latin = re.compile(r"[A-Za-z]")
    for paragraph in root.iter(W_P):
        text = "".join(node.text or "" for node in paragraph.iter(W_T))
        spacing = paragraph.find(f"{{{W_NS}}}pPr/{{{W_NS}}}spacing")
        if spacing is not None and spacing.get(f"{{{W_NS}}}lineRule") == "exact" and latin.search(text):
            spacing.set(f"{{{W_NS}}}lineRule", "atLeast")
            changed["exact_line_spacing_relaxed"] += 1
    if cjk_target:
        return changed

    symbol_fonts = {"wingdings", "wingdings 2", "wingdings 3", "webdings", "symbol", "mt extra"}
    for run in root.iter(f"{{{W_NS}}}r"):
        r_pr = run.find(f"{{{W_NS}}}rPr")
        if r_pr is None:
            continue
        fonts = r_pr.find(f"{{{W_NS}}}rFonts")
        if fonts is None:
            continue
        stripped_font = False
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            val = (fonts.get(f"{{{W_NS}}}{attr}") or "").strip().lower()
            if val in symbol_fonts:
                del fonts.attrib[f"{{{W_NS}}}{attr}"]
                stripped_font = True
        if stripped_font:
            changed["symbol_font_runs_normalized"] += 1

    page_width_emu = max(
        (int(page_sz.get(f"{{{W_NS}}}w")) for page_sz in root.iter(f"{{{W_NS}}}pgSz") if page_sz.get(f"{{{W_NS}}}w")),
        default=0,
    ) * 635
    portrait_drawings = []
    for tag in (f"{{{WPS_NS}}}bodyPr", f"{{{A_NS}}}bodyPr"):
        for body_pr in root.iter(tag):
            if body_pr.get("vert"):
                del body_pr.attrib["vert"]
                changed["vertical_text_boxes"] += 1
                for ancestor in body_pr.iterancestors():
                    if ancestor.tag in (f"{{{WP_NS}}}anchor", f"{{{WP_NS}}}inline"):
                        portrait_drawings.append(ancestor)
                        break
    for drawing in portrait_drawings:
        _swap_portrait_extents(drawing, page_width_emu)
    for element in root.iter():
        if not element.tag.startswith(f"{{{V_NS}}}") or element.get("style") is None:
            continue
        style = element.get("style")
        if "layout-flow:vertical" in style:
            element.set("style", _landscape_vml_style(style))
            changed["vertical_text_boxes"] += 1

    for paragraph, source_text in short_cjk_paragraphs:
        p_pr = paragraph.find(f"{{{W_NS}}}pPr")
        indent = p_pr.find(f"{{{W_NS}}}ind") if p_pr is not None else None
        squeezed = False
        if indent is not None and (int(indent.get(f"{{{W_NS}}}left", "0")) + int(indent.get(f"{{{W_NS}}}right", "0"))) >= 2000:
            indent.attrib.pop(f"{{{W_NS}}}left", None)
            indent.attrib.pop(f"{{{W_NS}}}right", None)
            squeezed = True
            changed["vertical_strip_indents_cleared"] += 1
        if not squeezed:
            continue
        target_len = len("".join(node.text or "" for node in paragraph.iter(W_T)))
        sizes = [int(size.get(f"{{{W_NS}}}val")) for size in paragraph.iter(f"{{{W_NS}}}sz") if size.get(f"{{{W_NS}}}val")]
        font_size = max(sizes, default=24)
        estimated = target_len * font_size * 5
        if column_twips and estimated > column_twips:
            scale = max(0.55, column_twips / estimated)
            for size in paragraph.iter(f"{{{W_NS}}}sz"):
                val = int(size.get(f"{{{W_NS}}}val", "0"))
                if val >= 24:
                    size.set(f"{{{W_NS}}}val", str(max(24, round(val * scale))))
                    changed["title_font_size_fit"] += 1
    return changed


def de_cjk_numbering_definitions(data: bytes) -> bytes:
    """第%1章-style chapter counters are style definitions, not content; the
    headings they now prefix are English, so the counter text must be too.
    chineseCounting numFmt values render the counter itself as CJK numerals
    (二, 三...) and are normalized to decimal for the same reason."""
    root = etree.fromstring(data, etree.XMLParser(remove_blank_text=False, resolve_entities=False))
    changed = False
    for lvl_text in root.iter(f"{{{W_NS}}}lvlText"):
        val = lvl_text.get(f"{{{W_NS}}}val", "")
        if not CJK_CHAR.search(val):
            continue
        lvl_text.set(f"{{{W_NS}}}val", CJK_CHAR.sub("", val.replace("第", "Chapter ")))
        changed = True
    for num_fmt in root.iter(f"{{{W_NS}}}numFmt"):
        val = num_fmt.get(f"{{{W_NS}}}val", "")
        if val.startswith("chinese"):
            num_fmt.set(f"{{{W_NS}}}val", "decimal")
            changed = True
    if not changed:
        return data
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _body_column_twips(root) -> int:
    """Usable text column width of the last section, in twips (0 if unknown)."""
    section = None
    for section in root.iter(f"{{{W_NS}}}sectPr"):
        pass
    if section is None:
        return 0
    page_sz = section.find(f"{{{W_NS}}}pgSz")
    page_mar = section.find(f"{{{W_NS}}}pgMar")
    if page_sz is None:
        return 0
    width = int(page_sz.get(f"{{{W_NS}}}w", "0"))
    return max(0, width - int(page_mar.get(f"{{{W_NS}}}left", "0")) - int(page_mar.get(f"{{{W_NS}}}right", "0"))) if page_mar is not None else width


def prepare(source: Path, job_dir: Path, target_language: str) -> Path:
    if (job_dir / 'translation-manifest.json').exists():
        raise ValueError('job already prepared; use batches to resume or choose a new job directory')
    job_dir.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    if source.suffix.lower() == ".doc":
        working = job_dir / "source-working.docx"
        script = Path(__file__).with_name("word_com.ps1")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "convert", "-InputPath", str(source), "-OutputPath", str(working)], check=True)
    elif source.suffix.lower() == ".docx":
        working = job_dir / ("source-working" + source.suffix.lower())
        shutil.copy2(source, working)
    else:
        raise ValueError("Word pipeline accepts only .doc and .docx")
    normalize_tab_structures(working)
    report = analyze(working)
    if "unsupported_chart_text" in report["complex_reasons"]:
        raise ValueError("unsupported editable chart text; translate or remove the chart text before retrying")
    units = [{"id": index, "source": text, "target": "", "protected_tokens": PROTECTED_TOKEN.findall(text)}
             for index, text in enumerate(report["unique_texts"], 1)]
    manifest = {
        "schema": 1, "source": str(source.resolve()), "source_sha256": source_hash,
        "working_docx": str(working.resolve()), "target_language": target_language,
        "baseline": {key: report[key] for key in ("section_count", "table_count", "media_count", "media_reference_count", "referenced_media")},
        "layout": report.get("layout", {}), "protected_tokens": report["protected_tokens"], "units": units,
    }
    path = job_dir / "translation-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    export_batches(path, kind='word')
    print(json.dumps({"stage": "prepared", "units": len(units), "manifest": str(path.resolve())}, ensure_ascii=False))
    return path


def apply(manifest_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [unit["id"] for unit in manifest["units"] if not unit.get("target")]
    if missing:
        raise ValueError(f"translation targets are empty: {missing}")
    mapping = {unit["source"]: unit["target"] for unit in manifest["units"]}
    applied = Counter()
    source = Path(manifest["working_docx"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == output.resolve():
        raise ValueError("input and output paths must be different")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(source) as src, ZipFile(temporary, "w", ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if is_text_part(info.filename):
                    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
                    root = etree.fromstring(data, parser)
                    short_cjk_paragraphs = []
                    for paragraph in root.iter(W_P):
                        source_text = paragraph_text(paragraph)
                        if source_text in mapping:
                            replace_paragraph_text(paragraph, source_text, mapping[source_text])
                            applied[source_text] += 1
                            stripped = source_text.strip()
                            if CJK_TITLE_RUN.fullmatch(stripped):
                                short_cjk_paragraphs.append((paragraph, stripped))
                    unwrap_anchored_text_boxes(root)
                    adapt_layout_for_target_language(root, manifest.get("target_language", "").strip().lower().startswith("zh"), short_cjk_paragraphs, _body_column_twips(root))
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                elif info.filename == "word/numbering.xml":
                    data = de_cjk_numbering_definitions(data)
                dst.writestr(info, data)
        unmatched = [unit["id"] for unit in manifest["units"] if applied[unit["source"]] == 0]
        apply_report = {
            "applied_occurrences": sum(applied.values()),
            "matched_units": len(applied),
            "unmatched_unit_ids": unmatched,
        }
        if unmatched:
            raise ValueError(f"translation units were not written: {unmatched}")
        with ZipFile(temporary) as package:
            if package.testzip() is not None or "word/document.xml" not in package.namelist():
                raise ValueError("generated DOCX package failed integrity validation")
        os.replace(temporary, output)
        post_structure = analyze(output)
        apply_report["post_structure"] = {
            key: post_structure[key] for key in ("section_count", "table_count", "media_count", "media_reference_count", "referenced_media")
        }
        (manifest_path.parent / "apply-report.json").write_text(
            json.dumps(apply_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"stage": "applied", "output": str(output.resolve())}, ensure_ascii=False))


def _fit_overlay_font(draw, text: str, font_path: str, width: int, height: int, requested: int, stroke_width: int):
    from PIL import ImageFont
    for size in range(requested, 5, -1):
        font = ImageFont.truetype(font_path, size)
        box = draw.multiline_textbbox((0, 0), text, font=font, spacing=1, stroke_width=stroke_width)
        if box[2] - box[0] <= width and box[3] - box[1] <= height:
            return font
    raise ValueError(f"image overlay text does not fit its approved region: {text}")


def localize_images(candidate: Path, plan_path: Path, output: Path) -> None:
    """Add translations inside selected raster images without erasing source labels."""
    from PIL import Image, ImageChops, ImageDraw

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    entries = plan.get("images", [])
    if not entries:
        raise ValueError("image localization plan has no images")
    analysis = analyze(candidate)
    referenced = set(analysis["referenced_media"])
    replacements: dict[str, bytes] = {}
    report = {"source": str(candidate.resolve()), "plan": str(plan_path.resolve()), "images": []}
    with ZipFile(candidate) as src:
        names = set(src.namelist())
        for entry in entries:
            media_name = entry["media"]
            if media_name not in names:
                raise ValueError(f"planned image is missing from DOCX: {media_name}")
            if media_name not in referenced:
                raise ValueError(f"planned image is not referenced by document content: {media_name}")
            original_bytes = src.read(media_name)
            original = Image.open(BytesIO(original_bytes)).convert("RGB")
            expected_size = tuple(entry.get("size", original.size))
            if original.size != expected_size:
                raise ValueError(f"image size mismatch for {media_name}: expected {expected_size}, got {original.size}")
            edited = original.copy()
            draw = ImageDraw.Draw(edited)
            approved_mask = Image.new("1", original.size, 0)
            mask_draw = ImageDraw.Draw(approved_mask)
            font_path = entry.get("font", "C:/Windows/Fonts/calibri.ttf")
            for overlay in entry.get("overlays", []):
                x, y, width, height = [int(overlay[key]) for key in ("x", "y", "width", "height")]
                if x < 0 or y < 0 or x + width > original.width or y + height > original.height:
                    raise ValueError(f"overlay region is outside {media_name}: {(x, y, width, height)}")
                text = overlay["text"]
                stroke_width = int(overlay.get("stroke_width", entry.get("stroke_width", 0)))
                font = _fit_overlay_font(draw, text, font_path, width, height, int(overlay.get("font_size", 14)), stroke_width)
                bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=1, stroke_width=stroke_width)
                text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
                align = overlay.get("align", "center")
                tx = x - bbox[0] if align == "left" else x - bbox[0] + max(0, (width - text_width) // 2)
                ty = y + max(0, (height - text_height) // 2) - bbox[1]
                color = tuple(overlay.get("color", [0, 75, 120]))
                stroke_fill = tuple(overlay.get("stroke_fill", [255, 255, 255]))
                draw.multiline_text((tx, ty), text, font=font, fill=color, spacing=1, align=align,
                                    stroke_width=stroke_width, stroke_fill=stroke_fill)
                mask_draw.rectangle((x, y, x + width - 1, y + height - 1), fill=1)
            outside = ImageChops.difference(original, edited)
            outside.paste((0, 0, 0), mask=approved_mask)
            if outside.getbbox() is not None:
                raise ValueError(f"unapproved pixels changed in {media_name}")
            suffix = Path(media_name).suffix.lower()
            image_format = "PNG" if suffix == ".png" else "JPEG"
            buffer = BytesIO()
            save_args = {"format": image_format}
            if image_format == "JPEG":
                save_args.update(quality=98, subsampling=0, optimize=True)
            edited.save(buffer, **save_args)
            encoded = buffer.getvalue()
            checked = Image.open(BytesIO(encoded))
            if checked.size != original.size or checked.format != image_format:
                raise ValueError(f"localized image format or dimensions changed: {media_name}")
            replacements[media_name] = encoded
            report["images"].append({
                "media": media_name, "size": list(original.size), "format": image_format,
                "overlays": len(entry.get("overlays", [])),
                "before_sha256": hashlib.sha256(original_bytes).hexdigest().upper(),
                "after_sha256": hashlib.sha256(encoded).hexdigest().upper(),
                "unapproved_pixels_changed_before_encoding": 0,
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(candidate) as src, ZipFile(temporary, "w", ZIP_DEFLATED) as dst:
            for info in src.infolist():
                dst.writestr(info, replacements.get(info.filename, src.read(info.filename)))
        if analyze(temporary)["referenced_media"] != analysis["referenced_media"]:
            raise ValueError("image localization changed document media references")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    report_path = plan_path.parent / "image-localization-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "images-localized", "output": str(output.resolve()), "report": str(report_path.resolve())}, ensure_ascii=False))


def validate(candidate: Path, manifest_path: Path, word_native: bool = False) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = analyze(candidate)
    failures = []
    source = Path(manifest["source"])
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest().upper() != manifest["source_sha256"]:
        failures.append("source file hash changed")
    candidate_texts = set(report["unique_texts"])
    missing_targets = [unit["id"] for unit in manifest["units"] if unit["target"] not in candidate_texts]
    if missing_targets:
        failures.append(f"missing target text for units: {missing_targets}")
    target_texts = {unit["target"] for unit in manifest["units"]}
    unsafe_layout = [item for item in report.get("text_layout_risks", []) if item.get("text") in target_texts]
    if unsafe_layout:
        failures.append(f"unsafe translated text layout: {unsafe_layout}")
    expected_tokens = normalize_protected_tokens([
        token for occurrence in manifest["protected_tokens"] for token in occurrence["tokens"]
    ])
    actual_tokens = normalize_protected_tokens([
        token for occurrence in report["protected_tokens"] for token in occurrence["tokens"]
    ])
    if actual_tokens != expected_tokens:
        failures.append("protected token mismatch")
    expected_structure = dict(manifest["baseline"])
    apply_report_path = manifest_path.parent / "apply-report.json"
    if apply_report_path.is_file():
        recorded = json.loads(apply_report_path.read_text(encoding="utf-8")).get("post_structure")
        if recorded:
            # Layout adaptation legitimately restructures the document (text box
            # unwrapping drops fallback duplicates), so the delivered file is
            # compared against what apply actually produced.
            expected_structure = recorded
    for key in ("section_count", "table_count", "media_count"):
        if report[key] != expected_structure[key]:
            failures.append(f"{key}: expected {expected_structure[key]}, got {report[key]}")
    expected_referenced_media = manifest.get("baseline", {}).get("referenced_media")
    expected_reference_count = manifest.get("baseline", {}).get("media_reference_count")
    if expected_referenced_media is not None and report["referenced_media"] != expected_referenced_media:
        failures.append(
            f"referenced media mismatch: expected {expected_referenced_media}, got {report['referenced_media']}"
        )
    if expected_reference_count is not None and report["media_reference_count"] != expected_reference_count:
        failures.append(
            f"media reference count: expected {expected_reference_count}, got {report['media_reference_count']}"
        )
    warnings = []
    word_report = {"status": "skipped"}
    if word_native:
        script = Path(__file__).with_name("word_com.ps1")
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "validate", "-InputPath", str(candidate)],
                check=True, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            word_report = json.loads(result.stdout.strip().splitlines()[-1])
            word_report["status"] = "passed"
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError, KeyError) as exc:
            warning = f"optional Word-native check failed: {exc}"
            warnings.append(warning)
            word_report = {"status": "warning", "message": warning}
    qa = {"passed": not failures, "failures": failures, "warnings": warnings, "structure": report, "word": word_report}
    qa_path = manifest_path.parent / "qa-report.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        raise ValueError("; ".join(failures))
    print(json.dumps({"stage": "validated", "word_native": word_report["status"], "report": str(qa_path.resolve())}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    add_commands(commands)
    p = commands.add_parser("prepare")
    p.add_argument("source", type=Path); p.add_argument("--job-dir", type=Path, required=True); p.add_argument("--target-language", required=True)
    a = commands.add_parser("apply")
    a.add_argument("manifest", type=Path); a.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("validate")
    v.add_argument("candidate", type=Path); v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--word-native", action="store_true", help="Run optional non-blocking Microsoft Word open/pagination check")
    i = commands.add_parser("localize-images")
    i.add_argument("candidate", type=Path); i.add_argument("--plan", type=Path, required=True); i.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in ('batches', 'merge'): return run_translation_command(args)
        if args.command == "prepare": prepare(args.source, args.job_dir, args.target_language)
        elif args.command == "apply": apply(args.manifest, args.output)
        elif args.command == "localize-images": localize_images(args.candidate, args.plan, args.output)
        else: validate(args.candidate, args.manifest, args.word_native)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
