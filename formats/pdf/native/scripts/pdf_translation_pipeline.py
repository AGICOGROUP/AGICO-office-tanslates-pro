#!/usr/bin/env python3
"""Resumable, zero-account PDF translation pipeline using bundled PDF tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

import pdfplumber
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, NameObject


SCHEMA_VERSION = 2
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LIST_RE = re.compile(r"^\s*(?:[>•●▪◆◇\-]|(?:\d+\.)+\d*|\d+[.)])\s*")
DOT_LEADER_RE = re.compile(r"[.·…]{4,}")


CJK_PUNCTUATION = set("，。；：！？、（）【】《》“”‘’—－")
PROTECTED_SYMBOLS = set("→←↑↓◄►•▪■◆●○±×÷≈≤≥℃°μΩΔ%")
POSITION_SYMBOLS = set("◄►•▪■◆●○▲▼")
TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}


@dataclass(frozen=True)
class FitPolicy:
    minimum_role_scale: float = 0.82

    def accepts(self, inserted_size: float, role_size: float) -> bool:
        if role_size <= 0:
            return False
        return inserted_size / role_size >= self.minimum_role_scale


def die(message: str) -> None:
    raise SystemExit(message)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text or ""))


def rgb_from_pdf_color(value: Any) -> list[int]:
    if value is None:
        return [0, 0, 0]
    if isinstance(value, (int, float)):
        gray = max(0.0, min(1.0, float(value)))
        channel = round(gray * 255)
        return [channel, channel, channel]
    values = [float(item) for item in value]
    if len(values) == 1:
        channel = round(max(0.0, min(1.0, values[0])) * 255)
        return [channel, channel, channel]
    if len(values) == 3:
        return [round(max(0.0, min(1.0, item)) * 255) for item in values]
    if len(values) >= 4:
        c, m, y, k = [max(0.0, min(1.0, item)) for item in values[:4]]
        return [
            round(255 * (1 - min(1, c + k))),
            round(255 * (1 - min(1, m + k))),
            round(255 * (1 - min(1, y + k))),
        ]
    return [0, 0, 0]


def luminance(rgb: list[int]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def is_protected_token(token: str) -> bool:
    value = normalize_text(token)
    if not value:
        return False
    if any(symbol in value for symbol in PROTECTED_SYMBOLS):
        return True
    if re.fullmatch(r"\[[^\]]+\]", value):
        return True
    if cjk_count(value) == 0 and re.search(r"[A-Za-z0-9μΩ℃°]", value):
        return True
    return False


def is_translatable_character(text: str) -> bool:
    return bool(CJK_RE.fullmatch(text) or text in CJK_PUNCTUATION)


def character_record(char: dict[str, Any]) -> dict[str, Any]:
    text = str(char.get("text", ""))
    font = str(char.get("fontname", ""))
    rgb = rgb_from_pdf_color(char.get("non_stroking_color"))
    return {
        "text": text,
        "bbox": [
            round(float(char.get("x0", 0)), 3),
            round(float(char.get("top", 0)), 3),
            round(float(char.get("x1", 0)), 3),
            round(float(char.get("bottom", 0)), 3),
        ],
        "font": font,
        "size": round(float(char.get("size", 0)), 3),
        "color_rgb": rgb,
        "bold": "bold" in font.lower(),
        "italic": any(token in font.lower() for token in ("italic", "oblique")),
        "translatable": is_translatable_character(text),
        "protected": not is_translatable_character(text),
    }


def visible_character(char: dict[str, Any]) -> bool:
    text = str(char.get("text", ""))
    if not text.strip():
        return False
    size = float(char.get("size", 0))
    rgb = rgb_from_pdf_color(char.get("non_stroking_color"))
    return size >= 2.5 and not (luminance(rgb) > 248 and size < 7)


def style_signature(char: dict[str, Any]) -> tuple[Any, ...]:
    font = str(char.get("fontname", char.get("font", "")))
    return (
        font,
        round(float(char.get("size", 0)), 2),
        tuple(rgb_from_pdf_color(char.get("non_stroking_color")))
        if "non_stroking_color" in char
        else tuple(char.get("color_rgb", [0, 0, 0])),
        "bold" in font.lower() or bool(char.get("bold")),
        any(token in font.lower() for token in ("italic", "oblique"))
        or bool(char.get("italic")),
    )


def runs_from_characters(chars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[list[dict[str, Any]]] = []
    for char in chars:
        if not runs or style_signature(runs[-1][-1]) != style_signature(char):
            runs.append([char])
        else:
            runs[-1].append(char)
    output: list[dict[str, Any]] = []
    for run in runs:
        records = [
            item if "bbox" in item else character_record(item)
            for item in run
        ]
        first = records[0]
        output.append(
            {
                "text": "".join(item["text"] for item in records),
                "bbox": [
                    min(item["bbox"][0] for item in records),
                    min(item["bbox"][1] for item in records),
                    max(item["bbox"][2] for item in records),
                    max(item["bbox"][3] for item in records),
                ],
                "font": first["font"],
                "size": first["size"],
                "color_rgb": first["color_rgb"],
                "bold": first["bold"],
                "italic": first["italic"],
                "protected": all(item["protected"] for item in records),
            }
        )
    return output


def segment_characters(
    chars: list[dict[str, Any]], cells: list[list[float]]
) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    for char in chars:
        record = char if "bbox" in char else character_record(char)
        x0, top, x1, bottom = record["bbox"]
        center = ((x0 + x1) / 2, (top + bottom) / 2)
        cell_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if cell[0] <= center[0] <= cell[2]
                and cell[1] <= center[1] <= cell[3]
            ),
            -1,
        )
        if grouped and grouped[-1]["cell_index"] == cell_index:
            grouped[-1]["characters"].append(record)
            grouped[-1]["text"] += record["text"]
        else:
            grouped.append(
                {
                    "cell_index": cell_index,
                    "text": record["text"],
                    "characters": [record],
                }
            )
    for item in grouped:
        item["bbox"] = [
            min(char["bbox"][0] for char in item["characters"]),
            min(char["bbox"][1] for char in item["characters"]),
            max(char["bbox"][2] for char in item["characters"]),
            max(char["bbox"][3] for char in item["characters"]),
        ]
    return grouped


def resolve_role_font_sizes(
    styles: list[dict[str, Any]], scale: float = 1.0
) -> list[int]:
    role_sources: dict[str, list[float]] = {}
    for style in styles:
        role_sources.setdefault(str(style["role"]), []).append(
            float(style["source_size"])
        )
    role_targets = {
        role: max(6, round(median(sizes) * scale))
        for role, sizes in role_sources.items()
    }
    return [role_targets[str(style["role"])] for style in styles]


def plan_preserved_prefix(source: str, translation: str) -> dict[str, str]:
    match = CJK_RE.search(source)
    prefix = source[: match.start()].strip() if match else ""
    prefix = prefix.rstrip("（(").strip()
    if (
        prefix
        and is_protected_token(prefix)
        and translation.casefold().startswith(prefix.casefold())
    ):
        remainder = translation[len(prefix) :].lstrip(" \t:：-–—")
        return {"preserved_prefix": prefix, "text_to_draw": remainder}
    return {"preserved_prefix": "", "text_to_draw": translation}


def dominant_char(line: dict[str, Any]) -> dict[str, Any]:
    chars = [char for char in line.get("chars", []) if char.get("text", "").strip()]
    if not chars:
        return {}
    return max(chars, key=lambda char: max(float(char.get("width", 0)), 0.1))


def text_from_chars(chars: list[dict[str, Any]]) -> str:
    output = ""
    previous: dict[str, Any] | None = None
    for char in chars:
        text = str(char.get("text", ""))
        if previous is not None:
            gap = float(char.get("x0", 0)) - float(previous.get("x1", 0))
            reference = max(
                float(previous.get("size", 0)),
                float(char.get("size", 0)),
                1,
            )
            if gap > reference * 0.45:
                output += " "
        output += text
        previous = char
    return normalize_text(output)


def line_record(line: dict[str, Any], page_width: float) -> dict[str, Any] | None:
    raw_chars = [char for char in line.get("chars", []) if visible_character(char)]
    text = text_from_chars(raw_chars)
    if not text:
        return None
    char = dominant_char({"chars": raw_chars})
    if not char:
        return None
    size = float(char.get("size", 0))
    rgb = rgb_from_pdf_color(char.get("non_stroking_color"))
    if size < 2.5 or (luminance(rgb) > 248 and size < 7):
        return None
    font = str(char.get("fontname", ""))
    matrix = char.get("matrix", (1, 0, 0, 1, 0, 0))
    rotation = round(math.degrees(math.atan2(float(matrix[1]), float(matrix[0]))))
    rotation = rotation % 360
    x0 = min(float(item.get("x0", line["x0"])) for item in raw_chars)
    x1 = max(float(item.get("x1", line["x1"])) for item in raw_chars)
    top = min(float(item.get("top", line["top"])) for item in raw_chars)
    bottom = max(float(item.get("bottom", line["bottom"])) for item in raw_chars)
    characters = [character_record(item) for item in raw_chars]
    return {
        "text": text,
        "bbox": [x0, top, x1, bottom],
        "font": font,
        "size": size,
        "color_rgb": rgb,
        "bold": "bold" in font.lower(),
        "italic": any(token in font.lower() for token in ("italic", "oblique")),
        "align": 1 if abs(((x0 + x1) / 2) - (page_width / 2)) < page_width * 0.03 else 0,
        "rotation": rotation,
        "characters": characters,
        "runs": runs_from_characters(characters),
    }


def can_group(previous: dict[str, Any], current: dict[str, Any], page_width: float) -> bool:
    if previous["bold"] or current["bold"]:
        return False
    if DOT_LEADER_RE.search(previous["text"]) or DOT_LEADER_RE.search(current["text"]):
        return False
    if LIST_RE.match(current["text"]):
        return False
    if current["rotation"] != previous["rotation"]:
        return False
    if abs(current["size"] - previous["size"]) > 0.8:
        return False
    if tuple(current.get("color_rgb", [])) != tuple(previous.get("color_rgb", [])):
        return False
    if abs(current["bbox"][0] - previous["bbox"][0]) > 12:
        return False
    vertical_gap = current["bbox"][1] - previous["bbox"][3]
    if vertical_gap < -0.5 or vertical_gap > max(previous["size"], current["size"]) * 0.85:
        return False
    previous_width = previous["bbox"][2] - previous["bbox"][0]
    if previous_width < page_width * 0.47:
        return False
    if previous["text"].endswith(("。", "！", "？", ":", "：")):
        return False
    return True


def group_lines(lines: list[dict[str, Any]], page_width: float) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for line in lines:
        if groups and can_group(groups[-1][-1], line, page_width) and len(groups[-1]) < 8:
            groups[-1].append(line)
        else:
            groups.append([line])
    records: list[dict[str, Any]] = []
    for group in groups:
        base = group[0]
        source_text = "\n".join(item["text"] for item in group)
        characters = [
            char
            for item in group
            for char in item.get("characters", [])
        ]
        records.append(
            {
                "bbox": [
                    min(item["bbox"][0] for item in group),
                    min(item["bbox"][1] for item in group),
                    max(item["bbox"][2] for item in group),
                    max(item["bbox"][3] for item in group),
                ],
                "source_text": source_text,
                "translation": source_text if cjk_count(source_text) == 0 else "",
                "lines": [
                    {
                        "text": item["text"],
                        "bbox": item["bbox"],
                        "characters": item.get("characters", []),
                        "runs": item.get("runs", []),
                    }
                    for item in group
                ],
                "characters": characters,
                "runs": runs_from_characters(characters) if characters else [],
                "style": {
                    key: base[key]
                    for key in (
                        "font",
                        "size",
                        "color_rgb",
                        "bold",
                        "italic",
                        "align",
                        "rotation",
                    )
                },
            }
        )
    return records


def page_table_cells(page: Any) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for table_index, table in enumerate(page.find_tables()):
        for cell_index, cell in enumerate(table.cells):
            if cell is None:
                continue
            cells.append(
                {
                    "table_index": table_index,
                    "cell_index": cell_index,
                    "bbox": [round(float(value), 3) for value in cell],
                }
            )
    return cells


def page_image_boxes(page: Any) -> list[list[float]]:
    boxes: list[list[float]] = []
    for image in page.images:
        try:
            boxes.append(
                [
                    round(float(image["x0"]), 3),
                    round(float(image["top"]), 3),
                    round(float(image["x1"]), 3),
                    round(float(image["bottom"]), 3),
                ]
            )
        except (KeyError, TypeError, ValueError):
            continue
    return boxes


def page_content_bounds(page_info: dict[str, Any]) -> list[float]:
    usable = [
        block
        for block in page_info.get("blocks", [])
        if str(block.get("role", "")).startswith(("body-", "heading-"))
    ]
    if not usable:
        return [24.0, max(25.0, float(page_info.get("width", 595)) - 24.0)]
    lefts = sorted(float(block["bbox"][0]) for block in usable)
    rights = sorted(float(block["bbox"][2]) for block in usable)
    left_index = min(len(lefts) - 1, max(0, round((len(lefts) - 1) * 0.1)))
    right_index = min(len(rights) - 1, max(0, round((len(rights) - 1) * 0.9)))
    return [round(lefts[left_index], 3), round(rights[right_index], 3)]


def attach_layout_segments(
    blocks: list[dict[str, Any]], table_cells: list[dict[str, Any]]
) -> None:
    cell_boxes = [cell["bbox"] for cell in table_cells]
    for block in blocks:
        for line in block.get("lines", []):
            line["segments"] = segment_characters(
                line.get("characters", []),
                cell_boxes,
            )


def bbox_center(box: list[float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def point_in_box(point: tuple[float, float], box: list[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


HEADING_PREFIX_RE = re.compile(
    r"^(?:[一二三四五六七八九十]+[、.．]|[IVXLC]+\.\s|\d+(?:\.\d+)*[、.．]\s*)",
    re.IGNORECASE,
)
CHAPTER_HEADING_RE = re.compile(
    r"^\s*\u7b2c[\u4e00-\u9fff0-9]+\u7ae0"
)
NUMBERED_SECTION_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)+)\s*[^\d.]"
)


def semantic_heading_level(source: str) -> int | None:
    text = normalize_text(source).strip()
    if not text or DOT_LEADER_RE.search(text) or len(text) > 45:
        return None
    if CHAPTER_HEADING_RE.match(text):
        return 1
    match = NUMBERED_SECTION_HEADING_RE.match(text)
    if not match:
        return None
    return min(3, match.group(1).count(".") + 1)


def source_font_is_bold(block: dict[str, Any]) -> bool:
    if "source_bold_override" in block:
        return bool(block["source_bold_override"])
    font_names = [str(block.get("style", {}).get("font", ""))]
    font_names.extend(str(run.get("font", "")) for run in block.get("runs", []))
    joined = " ".join(font_names).casefold()
    run_bold = any(bool(run.get("bold")) for run in block.get("runs", []))
    return run_bold or any(
        token in joined
        for token in ("bold", "black", "heavy", "simhei", "heiti", "黑体")
    )


def classify_document_roles(pages: list[dict[str, Any]]) -> None:
    body_size_weights: Counter[float] = Counter()
    for page in pages:
        page_height = float(page.get("height", 842))
        table_cells = page.get("table_cells", [])
        for block in page.get("blocks", []):
            center = bbox_center(block["bbox"])
            top, bottom = float(block["bbox"][1]), float(block["bbox"][3])
            source = str(block.get("source_text", "")).strip()
            if (
                top < 60
                or bottom > page_height - 70
                or any(point_in_box(center, cell["bbox"]) for cell in table_cells)
                or source_font_is_bold(block)
                or semantic_heading_level(source) is not None
            ):
                continue
            size = float(block.get("style", {}).get("size", 9))
            if size <= 24:
                size_bucket = round(size * 2) / 2
                # Extraction fragments are not paragraphs. Weight by visible
                # reading content so numerous short table fragments cannot make
                # a smaller table font become the document's body baseline.
                source_length = len(str(block.get("source_text", "")).strip())
                body_size_weights[size_bucket] += max(1, source_length)
    document_body_size = (
        max(body_size_weights, key=lambda value: (body_size_weights[value], value))
        if body_size_weights
        else 10.0
    )

    styles: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    for page in pages:
        page_height = float(page.get("height", 842))
        table_cells = page.get("table_cells", [])
        for block in page["blocks"]:
            style = block.setdefault("style", {})
            size = float(style.get("size", 9))
            top, bottom = float(block["bbox"][1]), float(block["bbox"][3])
            center = bbox_center(block["bbox"])
            source = str(block.get("source_text", "")).strip()
            semantic_level = semantic_heading_level(source)
            source_bold = source_font_is_bold(block) or semantic_level is not None
            size_bucket = round(size * 2) / 2
            in_table = any(point_in_box(center, cell["bbox"]) for cell in table_cells)
            if in_table:
                role = f"table-{size_bucket:g}"
            elif top < 60:
                role = "running-header"
            elif bottom > page_height - 70:
                role = "footer"
            elif semantic_level is not None:
                role = f"heading-{semantic_level}-{size_bucket:g}"
                block["source_bold_override"] = True
            elif (
                source_bold
                or (size >= document_body_size * 1.25 and len(source) <= 80)
            ):
                level = 1 if size >= document_body_size * 1.5 else 2
                role = f"heading-{level}-{size_bucket:g}"
            else:
                role = f"body-{size_bucket:g}"
            block["role"] = role
            style["source_bold"] = source_bold
            style["bold"] = source_bold
            styles.append(
                {
                    "role": role,
                    "source_size": size,
                }
            )
            blocks.append(block)
    targets = resolve_role_font_sizes(styles, scale=1.0)
    for block, target in zip(blocks, targets):
        if block.get("role") in {"running-header", "footer"}:
            block["style"]["role_size"] = float(
                block["style"].get("size", target)
            )
        elif str(block.get("role", "")).startswith("heading-"):
            level = int(str(block["role"]).split("-")[1])
            minimum_gap = 2.0 if level == 1 else 1.0
            block["style"]["role_size"] = max(
                float(target), document_body_size + minimum_gap
            )
        else:
            block["style"]["role_size"] = target


def apply_document_roles(pages: list[dict[str, Any]]) -> None:
    classify_document_roles(pages)


def extract_command(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    if not source.is_file():
        die(f"Input PDF not found: {source}")
    pages: list[dict[str, Any]] = []
    total_blocks = 0
    with pdfplumber.open(source) as document:
        for page_index, page in enumerate(document.pages):
            table_cells = page_table_cells(page)
            raw_lines = page.extract_text_lines(strip=True, return_chars=True) or []
            lines = [
                record
                for line in raw_lines
                if (record := line_record(line, float(page.width))) is not None
            ]
            blocks = group_lines(lines, float(page.width))
            attach_layout_segments(blocks, table_cells)
            for index, block in enumerate(blocks, 1):
                block["id"] = f"p{page_index + 1:04d}-b{index:04d}"
                block["bbox"] = [round(value, 3) for value in block["bbox"]]
                block["style"]["size"] = round(float(block["style"]["size"]), 3)
            total_blocks += len(blocks)
            pages.append(
                {
                    "page": page_index + 1,
                    "width": round(float(page.width), 3),
                    "height": round(float(page.height), 3),
                    "rotation": int(page.rotation or 0),
                    "image_count": len(page.images),
                    "image_boxes": page_image_boxes(page),
                    "table_cells": table_cells,
                    "blocks": blocks,
                }
            )
    apply_document_roles(pages)
    for page_info in pages:
        page_info["content_bounds"] = page_content_bounds(page_info)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_file": str(source),
        "source_sha256": sha256_file(source),
        "source_language": args.source_language,
        "target_language": args.target_language,
        "rebuild_mode": "raster-safe",
        "pages": pages,
    }
    write_json(Path(args.manifest), manifest)
    print(
        json.dumps(
            {
                "pages": len(pages),
                "translatable_blocks": total_blocks,
                "cjk_characters": sum(
                    cjk_count(block["source_text"])
                    for page in pages
                    for block in page["blocks"]
                ),
            },
            ensure_ascii=False,
        )
    )


def split_command(args: argparse.Namespace) -> None:
    manifest = read_json(Path(args.manifest))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for page in manifest["pages"]:
        if not page["blocks"]:
            continue
        page_chars = sum(cjk_count(block["source_text"]) for block in page["blocks"])
        if current and (
            len(current) >= args.max_pages
            or current_chars + page_chars > args.max_cjk_characters
        ):
            batches.append(current)
            current, current_chars = [], 0
        current.append(deepcopy(page))
        current_chars += page_chars
    if current:
        batches.append(current)

    index: list[dict[str, Any]] = []
    for number, pages in enumerate(batches, 1):
        path = output_dir / f"batch-{number:03d}.json"
        if path.exists() and not args.force:
            die(f"Batch exists; use --force to overwrite: {path}")
        write_json(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "source_sha256": manifest["source_sha256"],
                "source_language": manifest["source_language"],
                "target_language": manifest["target_language"],
                "batch": number,
                "pages": pages,
            },
        )
        index.append(
            {
                "batch": number,
                "file": path.name,
                "first_page": pages[0]["page"],
                "last_page": pages[-1]["page"],
                "blocks": sum(len(page["blocks"]) for page in pages),
                "cjk_characters": sum(
                    cjk_count(block["source_text"])
                    for page in pages
                    for block in page["blocks"]
                ),
            }
        )
    write_json(output_dir / "index.json", index)
    print(json.dumps(index, ensure_ascii=False))


def manifest_blocks(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        block["id"]: block
        for page in manifest["pages"]
        for block in page["blocks"]
    }


def merge_command(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    manifest = read_json(manifest_path)
    batch = read_json(Path(args.batch))
    if manifest["source_sha256"] != batch.get("source_sha256"):
        die("Batch source hash does not match manifest.")
    destination = manifest_blocks(manifest)
    merged = 0
    for page in batch.get("pages", []):
        for block in page.get("blocks", []):
            block_id = block.get("id")
            if block_id not in destination:
                die(f"Unknown block ID: {block_id}")
            if destination[block_id]["source_text"] != block.get("source_text"):
                die(f"Source text changed for block: {block_id}")
            translation = normalize_text(str(block.get("translation", "")))
            if not translation:
                die(f"Blank translation for block: {block_id}")
            if cjk_count(translation) and not args.allow_cjk:
                die(f"Unexpected CJK residue in translation: {block_id}")
            destination[block_id]["translation"] = translation
            merged += 1
    write_json(manifest_path, manifest)
    print(json.dumps({"merged_blocks": merged}, ensure_ascii=False))


def status_command(args: argparse.Namespace) -> None:
    manifest = read_json(Path(args.manifest))
    blocks = list(manifest_blocks(manifest).values())
    completed = sum(bool(normalize_text(block.get("translation", ""))) for block in blocks)
    result = {
        "total_blocks": len(blocks),
        "completed_blocks": completed,
        "remaining_blocks": len(blocks) - completed,
        "coverage_percent": round(100 * completed / max(len(blocks), 1), 2),
    }
    print(json.dumps(result, ensure_ascii=False))
    if completed != len(blocks):
        raise SystemExit(2)


def export_translation_command(args: argparse.Namespace) -> None:
    manifest = read_json(Path(args.manifest))
    records: list[dict[str, Any]] = []
    for page in manifest["pages"]:
        blocks = page.get("blocks", [])
        for index, block in enumerate(blocks):
            records.append(
                {
                    "id": block["id"],
                    "page": page["page"],
                    "source_text": block["source_text"],
                    "translation": block.get("translation", ""),
                    "role": block.get("role", ""),
                    "context_before": blocks[index - 1]["source_text"] if index else "",
                    "context_after": blocks[index + 1]["source_text"] if index + 1 < len(blocks) else "",
                    "protected_tokens": block.get("protected_tokens", []),
                }
            )
    write_json(
        Path(args.output),
        {"source_sha256": manifest["source_sha256"], "records": records},
    )
    print(json.dumps({"records": len(records), "output": str(Path(args.output).resolve())}, ensure_ascii=False))


def merge_translation_command(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    manifest = read_json(manifest_path)
    packet = read_json(Path(args.packet))
    if packet.get("source_sha256") != manifest.get("source_sha256"):
        die("Translation packet source hash does not match manifest.")
    destination = manifest_blocks(manifest)
    merged = 0
    for record in packet.get("records", []):
        block_id = record.get("id")
        if block_id not in destination:
            die(f"Unknown block ID: {block_id}")
        if destination[block_id]["source_text"] != record.get("source_text"):
            die(f"Source text changed for block: {block_id}")
        translation = normalize_text(str(record.get("translation", "")))
        if not translation:
            die(f"Blank translation for block: {block_id}")
        if cjk_count(translation) and not args.allow_cjk:
            die(f"Unexpected CJK residue in translation: {block_id}")
        destination[block_id]["translation"] = translation
        merged += 1
    write_json(manifest_path, manifest)
    print(json.dumps({"merged_blocks": merged}, ensure_ascii=False))


def char_center_in_box(char: dict[str, Any], box: list[float], pad: float = 0.8) -> bool:
    center_x = (float(char.get("x0", 0)) + float(char.get("x1", 0))) / 2
    center_y = (float(char.get("top", 0)) + float(char.get("bottom", 0))) / 2
    return (
        box[0] - pad <= center_x <= box[2] + pad
        and box[1] - pad <= center_y <= box[3] + pad
    )


def enrich_manifest_layout(source: Path, manifest: dict[str, Any]) -> None:
    with pdfplumber.open(source) as document:
        if len(document.pages) != len(manifest["pages"]):
            die("Manifest page count does not match the source PDF.")
        for page_info, page in zip(manifest["pages"], document.pages):
            table_cells = page_table_cells(page)
            page_info["table_cells"] = table_cells
            page_info["image_boxes"] = page_image_boxes(page)
            raw_lines = page.extract_text_lines(strip=True, return_chars=True) or []
            for block in page_info["blocks"]:
                selected_raw = [
                    char
                    for char in page.chars
                    if visible_character(char)
                    and char_center_in_box(char, block["bbox"])
                ]
                characters = [character_record(char) for char in selected_raw]
                block["characters"] = characters
                block["runs"] = runs_from_characters(characters) if characters else []
                lines: list[dict[str, Any]] = []
                for raw_line in raw_lines:
                    selected = [
                        char
                        for char in raw_line.get("chars", [])
                        if visible_character(char)
                        and char_center_in_box(char, block["bbox"])
                    ]
                    if not selected:
                        continue
                    records = [character_record(char) for char in selected]
                    lines.append(
                        {
                            "text": text_from_chars(selected),
                            "bbox": [
                                min(item["bbox"][0] for item in records),
                                min(item["bbox"][1] for item in records),
                                max(item["bbox"][2] for item in records),
                                max(item["bbox"][3] for item in records),
                            ],
                            "characters": records,
                            "runs": runs_from_characters(records),
                        }
                    )
                block["lines"] = lines
            attach_layout_segments(page_info["blocks"], table_cells)
    apply_document_roles(manifest["pages"])
    for page_info in manifest["pages"]:
        page_info["content_bounds"] = page_content_bounds(page_info)


def create_textless_pdf(source: Path, destination: Path) -> None:
    reader = PdfReader(source)
    writer = PdfWriter()
    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None:
            stream = ContentStream(contents, reader)
            stream.operations = [
                (operands, operator)
                for operands, operator in stream.operations
                if operator not in TEXT_SHOW_OPERATORS
            ]
            page[NameObject("/Contents")] = stream
        writer.add_page(page)
    with destination.open("wb") as handle:
        writer.write(handle)


def render_pdf(pdf: Path, output_dir: Path, prefix: str, dpi: int) -> list[Path]:
    subprocess.run(
        [
            locate_pdftoppm(),
            "-r",
            str(dpi),
            "-png",
            str(pdf),
            str(output_dir / prefix),
        ],
        check=True,
    )
    return sorted(output_dir.glob(f"{prefix}-*.png"))


def locate_pdftoppm() -> str:
    candidates = [
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdftoppm.exe"
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    located = shutil.which("pdftoppm")
    if located:
        return located
    die("Bundled Poppler pdftoppm was not found.")


def font_file(style: dict[str, Any]) -> str:
    candidates: list[str] = []
    windows = os.environ.get("WINDIR", r"C:\Windows")
    if style.get("bold") and style.get("italic"):
        candidates.append(os.path.join(windows, "Fonts", "arialbi.ttf"))
    elif style.get("bold"):
        candidates.append(os.path.join(windows, "Fonts", "arialbd.ttf"))
    elif style.get("italic"):
        candidates.append(os.path.join(windows, "Fonts", "ariali.ttf"))
    candidates.extend(
        [
            os.path.join(windows, "Fonts", "arial.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    )
    path = next((item for item in candidates if os.path.isfile(item)), None)
    if path is None:
        die("A Latin TrueType font such as Arial or DejaVu Sans is required.")
    return path


PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "：": ":",
        "，": ",",
        "。": ".",
        "！": "!",
        "？": "?",
        "【": "[",
        "】": "]",
    }
)


def normalized_anchor_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(PUNCTUATION_TRANSLATION)).strip()


def character_groups(chars: list[dict[str, Any]]) -> list[list[tuple[int, dict[str, Any]]]]:
    groups: list[list[tuple[int, dict[str, Any]]]] = []
    for index, char in enumerate(chars):
        text = str(char.get("text", ""))
        if CJK_RE.fullmatch(text):
            continue
        if not groups:
            groups.append([(index, char)])
            continue
        previous = groups[-1][-1][1]
        gap = float(char["bbox"][0]) - float(previous["bbox"][2])
        reference = max(float(char.get("size", 0)), float(previous.get("size", 0)), 1)
        if gap <= reference * 0.8:
            groups[-1].append((index, char))
        else:
            groups.append([(index, char)])
    return groups


def group_bbox(group: list[tuple[int, dict[str, Any]]]) -> list[float]:
    return [
        min(item["bbox"][0] for _, item in group),
        min(item["bbox"][1] for _, item in group),
        max(item["bbox"][2] for _, item in group),
        max(item["bbox"][3] for _, item in group),
    ]


def line_anchor_plan(line: dict[str, Any], target: str) -> list[dict[str, Any]]:
    normalized_target = normalized_anchor_text(target)
    cursor = 0
    anchors: list[dict[str, Any]] = []
    groups = character_groups(line.get("characters", []))
    cjk_color = tuple(source_line_color(line, [0, 0, 0]))
    wide_delimiter_indices: set[int] = set()
    for index in range(len(groups) - 1):
        left_text = normalized_anchor_text("".join(item["text"] for _, item in groups[index]))
        right_text = normalized_anchor_text("".join(item["text"] for _, item in groups[index + 1]))
        left_box = group_bbox(groups[index])
        right_box = group_bbox(groups[index + 1])
        gap = right_box[0] - left_box[2]
        cjk_between = any(
            CJK_RE.fullmatch(str(char.get("text", "")))
            and left_box[2] <= float(char["bbox"][0]) <= right_box[0]
            for char in line.get("characters", [])
        )
        wide_pair = (
            (left_text == "(" and right_text == ")" and gap > 18)
            or (left_text == "[" and right_text == "]" and gap > 8)
        )
        if wide_pair and not cjk_between:
            wide_delimiter_indices.update({index, index + 1})
    for group_index, group in enumerate(groups):
        raw = "".join(item["text"] for _, item in group)
        candidate = normalized_anchor_text(raw)
        if not candidate:
            continue
        group_color = tuple(group[0][1].get("color_rgb", [0, 0, 0]))
        visual_symbol = any(symbol in candidate for symbol in POSITION_SYMBOLS)
        bracketed_ui = candidate.startswith("[") and candidate.endswith("]")
        colored_label = (
            len(candidate) >= 2
            and group_color != cjk_color
            and not bracketed_ui
        )
        searchable = (
            colored_label
            or visual_symbol
            or bracketed_ui
            or group_index in wide_delimiter_indices
        )
        if not searchable:
            continue
        found = normalized_target.casefold().find(candidate.casefold(), cursor)
        if found < 0:
            continue
        candidate_box = group_bbox(group)
        source_ratio = (
            candidate_box[0] - float(line["bbox"][0])
        ) / max(float(line["bbox"][2]) - float(line["bbox"][0]), 1)
        target_ratio = found / max(len(normalized_target), 1)
        if bracketed_ui and not (source_ratio < 0.15 and target_ratio < 0.15):
            continue
        fixed_position = visual_symbol or group_index in wide_delimiter_indices
        fixed_position = fixed_position or bracketed_ui
        if not fixed_position and abs(source_ratio - target_ratio) > 0.25:
            continue
        anchors.append(
            {
                "text": candidate,
                "target_start": found,
                "target_end": found + len(candidate),
                "bbox": candidate_box,
                "character_indices": [index for index, _ in group],
            }
        )
        cursor = found + len(candidate)
    return anchors


def target_segments(
    target: str, anchors: list[dict[str, Any]], left: float, right: float
) -> list[dict[str, Any]]:
    normalized_target = normalized_anchor_text(target)
    segments: list[dict[str, Any]] = []
    target_cursor = 0
    x_cursor = left
    for anchor in anchors:
        text = normalized_target[target_cursor : anchor["target_start"]].strip()
        if text:
            segments.append(
                {
                    "text": text,
                    "left": x_cursor,
                    "right": anchor["bbox"][0] - 1.2,
                }
            )
        target_cursor = anchor["target_end"]
        x_cursor = anchor["bbox"][2] + 1.2
    tail = normalized_target[target_cursor:].strip()
    if tail:
        segments.append({"text": tail, "left": x_cursor, "right": right})
    return [item for item in segments if item["right"] - item["left"] > 1]


def source_line_color(line: dict[str, Any], fallback: list[int]) -> list[int]:
    counts: dict[tuple[int, int, int], int] = {}
    for char in line.get("characters", []):
        if CJK_RE.fullmatch(str(char.get("text", ""))):
            color = tuple(int(value) for value in char.get("color_rgb", fallback))
            counts[color] = counts.get(color, 0) + 1
    if not counts:
        return fallback
    return list(max(counts, key=counts.get))


def pdf_box_to_pixels(
    box: list[float], scale_x: float, scale_y: float, image: Image.Image
) -> tuple[int, int, int, int]:
    return (
        max(0, math.floor(box[0] * scale_x) - 1),
        max(0, math.floor(box[1] * scale_y) - 1),
        min(image.width, math.ceil(box[2] * scale_x) + 1),
        min(image.height, math.ceil(box[3] * scale_y) + 1),
    )


def restore_character_boxes(
    image: Image.Image,
    source_image: Image.Image,
    characters: list[dict[str, Any]],
    preserved_indices: set[int],
    scale_x: float,
    scale_y: float,
) -> int:
    restored = 0
    for index, char in enumerate(characters):
        if index in preserved_indices:
            continue
        box = pdf_box_to_pixels(char["bbox"], scale_x, scale_y, image)
        erase_pad = max(1, round(((scale_x + scale_y) / 2) * 1.2))
        box = (
            max(0, box[0] - erase_pad),
            max(0, box[1] - erase_pad),
            min(image.width, box[2] + erase_pad),
            min(image.height, box[3] + erase_pad),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        pad = max(2, round(max(box[2] - box[0], box[3] - box[1]) * 0.18))
        outer = (
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(source_image.width, box[2] + pad),
            min(source_image.height, box[3] + pad),
        )
        border_pixels: list[tuple[int, int, int]] = []
        source_pixels = source_image.load()
        for y in range(outer[1], outer[3]):
            for x in range(outer[0], outer[2]):
                if box[0] <= x < box[2] and box[1] <= y < box[3]:
                    continue
                border_pixels.append(source_pixels[x, y])
        fill = Counter(border_pixels).most_common(1)[0][0] if border_pixels else (255, 255, 255)
        painter = ImageDraw.Draw(image)
        painter.rectangle(box, fill=fill)
        restored += 1
    return restored


def restore_table_lines(
    image: Image.Image,
    source_image: Image.Image,
    table_cells: list[dict[str, Any]],
    scale_x: float,
    scale_y: float,
) -> None:
    horizontal: set[tuple[float, float, float]] = set()
    vertical: set[tuple[float, float, float]] = set()
    for cell in table_cells:
        x0, top, x1, bottom = [float(value) for value in cell["bbox"]]
        horizontal.update({(top, x0, x1), (bottom, x0, x1)})
        vertical.update({(x0, top, bottom), (x1, top, bottom)})
    thickness = max(1, round(((scale_x + scale_y) / 2) * 0.8))
    for y, x0, x1 in horizontal:
        box = (
            max(0, round(x0 * scale_x)),
            max(0, round(y * scale_y) - thickness),
            min(image.width, round(x1 * scale_x)),
            min(image.height, round(y * scale_y) + thickness + 1),
        )
        image.paste(source_image.crop(box), box)
    for x, top, bottom in vertical:
        box = (
            max(0, round(x * scale_x) - thickness),
            max(0, round(top * scale_y)),
            min(image.width, round(x * scale_x) + thickness + 1),
            min(image.height, round(bottom * scale_y)),
        )
        image.paste(source_image.crop(box), box)


def background_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[tuple[int, int, int], float]:
    crop = image.crop(box).convert("RGB")
    if crop.width == 0 or crop.height == 0:
        return (255, 255, 255), 0.0
    small = crop.copy()
    small.thumbnail((256, 256))
    quantized = small.quantize(colors=16)
    colors = quantized.getcolors(maxcolors=16) or []
    count, index = max(colors, default=(1, 0))
    palette = quantized.getpalette() or [255, 255, 255]
    rgb = tuple(palette[index * 3 : index * 3 + 3])
    variance = 1.0 - (count / max(small.width * small.height, 1))
    return (int(rgb[0]), int(rgb[1]), int(rgb[2])), round(variance, 4)


def wrap_paragraph(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    output: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            output.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if draw.textlength(candidate, font=font) <= width:
                line = candidate
            else:
                output.append(line)
                line = word
        output.append(line)
    return output


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    original_size_px: float,
    width: int,
    height: int,
    minimum_scale: float = 0.82,
) -> tuple[ImageFont.FreeTypeFont, str, int]:
    size = max(int(round(original_size_px)), 6)
    minimum = max(int(round(size * minimum_scale)), 6)
    while size >= minimum:
        font = ImageFont.truetype(font_path, size=size)
        lines = wrap_paragraph(draw, text, font, max(width, 1))
        spacing = max(1, round(size * 0.08))
        rendered = "\n".join(lines)
        bbox = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=spacing)
        ascent, descent = font.getmetrics()
        exact_height = (
            len(lines) * (ascent + descent)
            + max(0, len(lines) - 1) * spacing
        )
        if (
            bbox[2] - bbox[0] <= width
            and bbox[3] - bbox[1] <= height
            and exact_height <= height
        ):
            return font, rendered, spacing
        size -= 1
    raise ValueError("Translated text does not fit its source box.")


def rendered_page_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("page-*.png"))


def split_words_by_widths(text: str, widths: list[float]) -> list[str]:
    words = text.split()
    if len(widths) <= 1 or len(words) < len(widths):
        return [text]
    total_width = sum(widths)
    cuts = [0]
    for index in range(1, len(widths)):
        target = sum(widths[:index]) / max(total_width, 1) * len(words)
        cut = max(cuts[-1] + 1, min(len(words) - (len(widths) - index), round(target)))
        cuts.append(cut)
    cuts.append(len(words))
    return [" ".join(words[cuts[i] : cuts[i + 1]]) for i in range(len(widths))]


TABLE_TOKEN_RE = re.compile(
    r"±\s*\d+(?:\.\d+)?%|"
    r"\d[\d,]*(?:\.\d+)?|"
    r"[A-Za-zμΩ]+(?:[A-Za-z0-9μΩ/₂₃₄₅₆₇₈₉-]*[A-Za-z0-9μΩ₂₃₄₅₆₇₈₉])?|"
    r"[%℃°]"
)
SUBSCRIPT_TRANSLATION = str.maketrans("₂₃₄₅₆₇₈₉", "23456789")


def canonical_table_token(token: str) -> str:
    return (
        token.translate(SUBSCRIPT_TRANSLATION)
        .replace(",", "")
        .replace(" ", "")
        .casefold()
    )


def token_spans(text: str) -> list[dict[str, Any]]:
    return [
        {
            "token": canonical_table_token(match.group()),
            "start": match.start(),
            "end": match.end(),
        }
        for match in TABLE_TOKEN_RE.finditer(text)
    ]


def semantic_table_parts(source_parts: list[str], target: str) -> list[str]:
    target_tokens = token_spans(target)
    if not target_tokens:
        return []
    cursor = 0
    first_matches: list[int | None] = []
    for source_part in source_parts:
        source_tokens = [item["token"] for item in token_spans(source_part)]
        first: int | None = None
        for source_token in source_tokens:
            found = next(
                (
                    index
                    for index in range(cursor, len(target_tokens))
                    if target_tokens[index]["token"] == source_token
                ),
                None,
            )
            if found is None:
                continue
            if first is None:
                first = found
            cursor = found + 1
        first_matches.append(first)
    if sum(item is not None for item in first_matches) < 2:
        return []
    starts = [0]
    for index in range(1, len(source_parts)):
        match_index = first_matches[index]
        if match_index is None:
            return []
        start = int(target_tokens[match_index]["start"])
        if start > 0 and target[start - 1] in {"-", "−", "+"}:
            start -= 1
        starts.append(start)
    starts.append(len(target))
    return [
        target[starts[index] : starts[index + 1]].strip()
        for index in range(len(source_parts))
    ]


def visual_gap_segments(line: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for char in line.get("characters", []):
        if not groups:
            groups.append([char])
            continue
        previous = groups[-1][-1]
        gap = float(char["bbox"][0]) - float(previous["bbox"][2])
        reference = max(float(char.get("size", 0)), float(previous.get("size", 0)), 1)
        if gap > max(14.0, reference * 1.55):
            groups.append([char])
        else:
            groups[-1].append(char)
    return [
        {
            "text": "".join(char["text"] for char in group).strip(),
            "bbox": [
                min(char["bbox"][0] for char in group),
                min(char["bbox"][1] for char in group),
                max(char["bbox"][2] for char in group),
                max(char["bbox"][3] for char in group),
            ],
        }
        for group in groups
        if "".join(char["text"] for char in group).strip()
    ]


def rule_based_table_segments(
    line: dict[str, Any], table_cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    raw_rules = sorted(
        {
            round(float(value), 3)
            for cell in table_cells
            for value in (cell["bbox"][0], cell["bbox"][2])
        }
    )
    rules: list[float] = []
    for value in raw_rules:
        if not rules or value - rules[-1] >= 10:
            rules.append(value)
    if not rules:
        return []
    left = min(float(line["bbox"][0]), rules[0])
    right = max(float(line["bbox"][2]), rules[-1])
    bounds = [left, *rules]
    if right > bounds[-1] + 1:
        bounds.append(right)
    groups: list[dict[str, Any]] = []
    for index in range(len(bounds) - 1):
        x0, x1 = bounds[index], bounds[index + 1]
        chars = [
            char
            for char in line.get("characters", [])
            if x0 - 0.5
            <= (float(char["bbox"][0]) + float(char["bbox"][2])) / 2
            < x1 + (0.5 if index + 1 == len(bounds) - 1 else 0)
        ]
        if not chars:
            continue
        groups.append(
            {
                "text": "".join(char["text"] for char in chars).strip(),
                "bbox": [
                    x0,
                    min(char["bbox"][1] for char in chars),
                    x1,
                    max(char["bbox"][3] for char in chars),
                ],
            }
        )
    return [item for item in groups if item["text"]]


def table_segment_targets(
    line: dict[str, Any], target: str, table_cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    segments = [
        item
        for item in line.get("segments", [])
        if int(item.get("cell_index", -1)) >= 0
    ]
    cell_indices: list[int] = []
    for item in segments:
        index = int(item["cell_index"])
        if index not in cell_indices:
            cell_indices.append(index)
    center_y = (float(line["bbox"][1]) + float(line["bbox"][3])) / 2
    row_cells = [
        cell["bbox"]
        for cell in table_cells
        if float(cell["bbox"][1]) - 1 <= center_y <= float(cell["bbox"][3]) + 1
    ]
    source_parts: list[str]
    if len(cell_indices) > 1:
        boxes = [table_cells[index]["bbox"] for index in cell_indices]
        source_parts = [
            "".join(
                item["text"]
                for item in segments
                if int(item["cell_index"]) == index
            )
            for index in cell_indices
        ]
    else:
        visual_segments = rule_based_table_segments(line, table_cells)
        if len(visual_segments) < 2:
            visual_segments = visual_gap_segments(line)
        if not row_cells or len(visual_segments) < 2:
            if row_cells and len(visual_segments) == 1:
                table_left = min(float(box[0]) for box in row_cells)
                table_right = max(
                    float(cell["bbox"][2]) for cell in table_cells
                )
                segment = visual_segments[0]
                if (
                    float(segment["bbox"][0]) < table_left
                    and table_left - float(segment["bbox"][0]) >= 20
                ):
                    right = table_left - 1
                elif float(segment["bbox"][0]) >= table_right - 2:
                    right = float(line["bbox"][2]) + 80
                else:
                    right = max(table_right - 1, float(line["bbox"][2]) + 1)
                row_top = min(float(box[1]) for box in row_cells)
                row_bottom = max(float(box[3]) for box in row_cells)
                line_height = float(line["bbox"][3]) - float(line["bbox"][1])
                if row_bottom - row_top > max(24.0, line_height * 2.5):
                    row_top, row_bottom = (
                        float(line["bbox"][1]),
                        float(line["bbox"][3]),
                    )
                return [
                    {
                        "text": target,
                        "left": float(segment["bbox"][0]),
                        "right": right,
                        "top": max(row_top, float(line["bbox"][1])),
                        "bottom": row_bottom,
                        "preserve_source": (
                            cjk_count(segment["text"]) == 0
                            and is_protected_token(segment["text"])
                        ),
                    }
                ]
            return []
        table_right = max(float(cell["bbox"][2]) for cell in table_cells)
        boxes = []
        for index, segment in enumerate(visual_segments):
            left = (
                float(segment["bbox"][0])
                if index == 0
                else float(visual_segments[index]["bbox"][0]) - 2.5
            )
            right = (
                float(visual_segments[index + 1]["bbox"][0]) - 2.5
                if index + 1 < len(visual_segments)
                else table_right - 1
            )
            boxes.append([left, line["bbox"][1], right, line["bbox"][3]])
        source_parts = [item["text"] for item in visual_segments]
    line_width = float(line["bbox"][2]) - float(line["bbox"][0])
    cell_span = max(box[2] for box in boxes) - min(box[0] for box in boxes)
    narrow_unprotected_cell = any(
        box[2] - box[0] < 20 and not is_protected_token(source_parts[index])
        for index, box in enumerate(boxes)
    )
    if narrow_unprotected_cell or cell_span < line_width * 0.35:
        return []
    parts = semantic_table_parts(source_parts, target)
    if not parts:
        parts = split_words_by_widths(
            target,
            [box[2] - box[0] for box in boxes],
        )
    if len(parts) != len(boxes):
        return []
    line_height = float(line["bbox"][3]) - float(line["bbox"][1])
    row_top = min((float(box[1]) for box in row_cells), default=float(line["bbox"][1]))
    row_bottom = max((float(box[3]) for box in row_cells), default=float(line["bbox"][3]))
    if row_bottom - row_top > max(24.0, line_height * 2.5):
        row_top, row_bottom = float(line["bbox"][1]), float(line["bbox"][3])
    draw_top = max(row_top, float(line["bbox"][1]))
    return [
        {
            "text": part,
            "left": box[0] + 3,
            "right": box[2] - 2,
            "top": draw_top,
            "bottom": row_bottom,
            "preserve_source": (
                cjk_count(source_part) == 0
                and is_protected_token(source_part)
            ),
        }
        for part, box, source_part in zip(parts, boxes, source_parts)
    ]


def prepared_translation(block: dict[str, Any]) -> str:
    if block.get("render_suppressed"):
        return ""
    if "render_translation_override" in block:
        return str(block["render_translation_override"]).strip()
    translation = str(block.get("translation", "")).strip()
    visible_source = "\n".join(
        line.get("text", "") for line in block.get("lines", [])
    )
    original_source = str(block.get("source_text", ""))
    if original_source.lstrip().startswith("Pos") and not visible_source.lstrip().startswith("Pos"):
        translation = translation.rsplit(" @ ", 1)[-1].strip()
    if cjk_count(original_source) and re.fullmatch(r"[\s.,;:!?-]+", translation):
        return ""
    return translation


def merge_list_continuations_for_rendering(manifest: dict[str, Any]) -> None:
    for page in manifest["pages"]:
        blocks = page["blocks"]
        for index in range(len(blocks) - 1):
            current = blocks[index]
            following = blocks[index + 1]
            source = str(current.get("source_text", "")).lstrip()
            following_source = str(following.get("source_text", "")).lstrip()
            if not source.startswith((">", "-", "•", "▪")):
                continue
            if following_source.startswith((">", "-", "•", "▪")):
                continue
            current_size = float(current.get("style", {}).get("size", 0))
            following_size = float(following.get("style", {}).get("size", 0))
            vertical_gap = float(following["bbox"][1]) - float(current["bbox"][3])
            indent = float(following["bbox"][0]) - float(current["bbox"][0])
            if (
                abs(current_size - following_size) > 0.5
                or not (-1.0 <= vertical_gap <= 3.0)
                or not (6.0 <= indent <= 24.0)
            ):
                continue
            following_translation = str(following.get("translation", "")).strip()
            if re.fullmatch(r"[\s.,;:!?-]+", following_translation):
                following_translation = ""
            current["render_translation_override"] = (
                f"{str(current.get('translation', '')).strip()} "
                f"{following_translation}"
            ).strip()
            current["bbox"] = [
                min(current["bbox"][0], following["bbox"][0]),
                min(current["bbox"][1], following["bbox"][1]),
                max(current["bbox"][2], following["bbox"][2]),
                max(current["bbox"][3], following["bbox"][3]),
            ]
            current["force_block_mode"] = True
            following["render_suppressed"] = True


def apply_command(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    manifest = read_json(Path(args.manifest))
    if sha256_file(source) != manifest["source_sha256"]:
        die("Input PDF hash does not match the manifest source.")
    enrich_manifest_layout(source, manifest)
    blocks = list(manifest_blocks(manifest).values())
    missing = [block["id"] for block in blocks if not normalize_text(block.get("translation", ""))]
    if missing:
        die(f"Manifest is incomplete; first missing block: {missing[0]}")
    merge_list_continuations_for_rendering(manifest)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="pdf-translate-") as temporary:
        render_dir = Path(temporary)
        images = render_pdf(source, render_dir, "source", args.dpi)
        if len(images) != len(manifest["pages"]):
            die(f"Rendered {len(images)} pages; expected {len(manifest['pages'])}.")

        result = canvas.Canvas(str(output), pageCompression=1)
        for page_info, image_path in zip(manifest["pages"], images):
            image = Image.open(image_path).convert("RGB")
            source_image = image.copy()
            draw = ImageDraw.Draw(image)
            scale_x = image.width / float(page_info["width"])
            scale_y = image.height / float(page_info["height"])
            average_scale = (scale_x + scale_y) / 2
            table_cells = page_info.get("table_cells", [])
            render_plans: dict[str, dict[str, Any]] = {}
            for block in page_info["blocks"]:
                translation = prepared_translation(block)
                source_lines = block.get("lines", [])
                target_lines = translation.splitlines() if translation else []
                if source_lines and len(target_lines) <= len(source_lines):
                    target_lines.extend([""] * (len(source_lines) - len(target_lines)))
                candidate_anchor_lines = [
                    line_anchor_plan(line, target_line)
                    for line, target_line in zip(source_lines, target_lines)
                ]
                candidate_table_lines = [
                    table_segment_targets(line, target_line, table_cells)
                    if target_line.strip()
                    else []
                    for line, target_line in zip(source_lines, target_lines)
                ]
                structured_table = any(candidate_table_lines)
                line_colors = {
                    tuple(source_line_color(line, [0, 0, 0]))
                    for line in source_lines
                }
                needs_line_preservation = (
                    len(source_lines) <= 1
                    or any(candidate_anchor_lines)
                    or structured_table
                    or len(line_colors) > 1
                )
                line_mode = (
                    bool(source_lines)
                    and len(target_lines) == len(source_lines)
                    and not block.get("force_block_mode")
                    and needs_line_preservation
                )
                anchor_lines: list[list[dict[str, Any]]] = []
                table_lines: list[list[dict[str, Any]]] = []
                restored_characters = 0
                if line_mode:
                    for line, anchors, table_items in zip(
                        source_lines,
                        candidate_anchor_lines,
                        candidate_table_lines,
                    ):
                        anchor_lines.append(anchors)
                        table_lines.append(table_items)
                        preserved = {
                            index
                            for anchor in anchors
                            for index in anchor["character_indices"]
                        }
                        for index, char in enumerate(line.get("characters", [])):
                            center_x = (
                                float(char["bbox"][0]) + float(char["bbox"][2])
                            ) / 2
                            if any(
                                item.get("preserve_source")
                                and float(item["left"]) - 4
                                <= center_x
                                <= float(item["right"]) + 3
                                for item in table_items
                            ):
                                preserved.add(index)
                        restored_characters += restore_character_boxes(
                            image,
                            source_image,
                            line.get("characters", []),
                            preserved,
                            scale_x,
                            scale_y,
                        )
                else:
                    restored_characters = restore_character_boxes(
                        image,
                        source_image,
                        block.get("characters", []),
                        set(),
                        scale_x,
                        scale_y,
                    )
                render_plans[block["id"]] = {
                    "translation": translation,
                    "source_lines": source_lines,
                    "target_lines": target_lines,
                    "line_mode": line_mode,
                    "anchor_lines": anchor_lines,
                    "table_lines": table_lines,
                    "restored_characters": restored_characters,
                }
            restore_table_lines(
                image,
                source_image,
                table_cells,
                scale_x,
                scale_y,
            )
            for block_index, block in enumerate(page_info["blocks"]):
                style = block["style"]
                role_size = float(style.get("role_size", style.get("size", 9)))
                plan = render_plans[block["id"]]
                translation = plan["translation"]
                source_lines = plan["source_lines"]
                target_lines = plan["target_lines"]
                line_mode = plan["line_mode"]
                inserted_sizes: list[int] = []
                restored_characters = int(plan["restored_characters"])
                preserved_anchors = sum(len(items) for items in plan["anchor_lines"])
                fallback_shrink = False

                if line_mode:
                    for line, target_line, anchors, table_items in zip(
                        source_lines,
                        target_lines,
                        plan["anchor_lines"],
                        plan["table_lines"],
                    ):
                        if not target_line.strip():
                            continue
                        left = float(line["bbox"][0])
                        if (
                            block.get("role") == "running-header"
                            and left > float(page_info["width"]) / 2
                        ):
                            left = max(50, float(page_info["width"]) - 180)
                        right = max(
                            float(line["bbox"][2]),
                            float(page_info["width"]) - 24,
                        )
                        color = tuple(
                            source_line_color(
                                line,
                                [int(item) for item in style.get("color_rgb", [0, 0, 0])],
                            )
                        )
                        items = table_items if not anchors else []
                        if not items:
                            items = target_segments(target_line, anchors, left, right)
                        for item in items:
                            if item.get("preserve_source"):
                                continue
                            top = float(item.get("top", line["bbox"][1]))
                            bottom = float(
                                item.get(
                                    "bottom",
                                    max(
                                        line["bbox"][3],
                                        top + role_size * 1.45,
                                    ),
                                )
                            )
                            box = pdf_box_to_pixels(
                                [
                                    float(item["left"]),
                                    top,
                                    float(item["right"]),
                                    bottom,
                                ],
                                scale_x,
                                scale_y,
                                image,
                            )
                            try:
                                font, rendered, spacing = fit_text(
                                    draw,
                                    item["text"],
                                    font_file(style),
                                    role_size * average_scale,
                                    max(box[2] - box[0] - 2, 1),
                                    max(box[3] - box[1] - 2, 1),
                                    minimum_scale=0.82,
                                )
                            except ValueError:
                                fallback_shrink = True
                                try:
                                    font, rendered, spacing = fit_text(
                                        draw,
                                        item["text"],
                                        font_file(style),
                                        role_size * average_scale,
                                        max(box[2] - box[0] - 2, 1),
                                        max(box[3] - box[1] - 2, 1),
                                        minimum_scale=0.50,
                                    )
                                except ValueError:
                                    die(
                                        f"Text segment does not fit: {block['id']} "
                                        f"{item['text']!r} in {box}."
                                    )
                            inserted_sizes.append(font.size)
                            draw.multiline_text(
                                (box[0] + 1, box[1] + 1),
                                rendered,
                                font=font,
                                fill=color,
                                spacing=spacing,
                                align="left",
                                anchor="la",
                            )
                else:
                    x0, top, x1, bottom = [float(value) for value in block["bbox"]]
                    right = max(x1, float(page_info["width"]) - 24)
                    if block_index + 1 < len(page_info["blocks"]):
                        next_top = float(page_info["blocks"][block_index + 1]["bbox"][1])
                        if next_top > bottom:
                            bottom = max(bottom, next_top - 3)
                    box = pdf_box_to_pixels(
                        [x0, top, right, bottom],
                        scale_x,
                        scale_y,
                        image,
                    )
                    if translation:
                        render_translation = re.sub(r"\s*\n\s*", " ", translation).strip()
                        try:
                            font, rendered, spacing = fit_text(
                                draw,
                                render_translation,
                                font_file(style),
                                role_size * average_scale,
                                max(box[2] - box[0] - 2, 1),
                                max(box[3] - box[1] - 2, 1),
                                minimum_scale=0.82,
                            )
                        except ValueError:
                            fallback_shrink = True
                            try:
                                font, rendered, spacing = fit_text(
                                    draw,
                                    render_translation,
                                    font_file(style),
                                    role_size * average_scale,
                                    max(box[2] - box[0] - 2, 1),
                                    max(box[3] - box[1] - 2, 1),
                                    minimum_scale=0.62,
                                )
                            except ValueError:
                                die(
                                    f"Translated block does not fit: {block['id']} "
                                    f"in {box}."
                                )
                        inserted_sizes.append(font.size)
                        draw.multiline_text(
                            (box[0] + 1, box[1] + 1),
                            rendered,
                            font=font,
                            fill=tuple(
                                int(item)
                                for item in style.get("color_rgb", [0, 0, 0])
                            ),
                            spacing=spacing,
                            align="left",
                            anchor="la",
                        )
                report.append(
                    {
                        "id": block["id"],
                        "page": page_info["page"],
                        "role": block.get("role"),
                        "role_font_px": round(role_size * average_scale, 2),
                        "inserted_font_px": inserted_sizes,
                        "minimum_inserted_font_px": min(inserted_sizes, default=0),
                        "fallback_shrink": fallback_shrink,
                        "restored_source_characters": restored_characters,
                        "preserved_anchors": preserved_anchors,
                        "line_mode": line_mode,
                    }
                )
            width, height = float(page_info["width"]), float(page_info["height"])
            result.setPageSize((width, height))
            result.drawImage(
                ImageReader(image),
                0,
                0,
                width=width,
                height=height,
                preserveAspectRatio=False,
                mask="auto",
            )
            result.showPage()
            source_image.close()
            image.close()
        result.save()

    report_path = output.with_suffix(".apply-report.json")
    write_json(report_path, report)
    print(
        json.dumps(
            {
                "output": str(output),
                "blocks_inserted": len(report),
                "fallback_shrink_blocks": sum(item["fallback_shrink"] for item in report),
                "preserved_anchors": sum(item["preserved_anchors"] for item in report),
                "report": str(report_path),
                "mode": "raster-preserving-character-replacement",
            },
            ensure_ascii=False,
        )
    )


def geometry(reader: PdfReader) -> list[dict[str, Any]]:
    output = []
    for index, page in enumerate(reader.pages):
        box = page.mediabox
        output.append(
            {
                "page": index + 1,
                "width": round(float(box.width), 3),
                "height": round(float(box.height), 3),
                "rotation": int(page.get("/Rotate", 0) or 0),
            }
        )
    return output


def qa_command(args: argparse.Namespace) -> None:
    source_path = Path(args.source).resolve()
    translated_path = Path(args.translated).resolve()
    manifest = read_json(Path(args.manifest))
    source_reader = PdfReader(source_path)
    translated_reader = PdfReader(translated_path)
    source_geometry = geometry(source_reader)
    translated_geometry = geometry(translated_reader)
    blocks = list(manifest_blocks(manifest).values())
    blanks = [block["id"] for block in blocks if not normalize_text(block.get("translation", ""))]
    target_cjk = [block["id"] for block in blocks if cjk_count(block.get("translation", ""))]
    residue_pages = []
    for index, page in enumerate(translated_reader.pages):
        count = cjk_count(page.extract_text() or "")
        if count:
            residue_pages.append({"page": index + 1, "cjk_characters": count})
    apply_report_path = translated_path.with_suffix(".apply-report.json")
    apply_report = read_json(apply_report_path) if apply_report_path.is_file() else []
    fallback_blocks = [
        item["id"] for item in apply_report if item.get("fallback_shrink")
    ]
    critical_role_scale_violations = []
    anchored_scale_exemptions = []
    for item in apply_report:
        inserted = float(item.get("minimum_inserted_font_px", 0) or 0)
        role_size = float(item.get("role_font_px", 0) or 0)
        if inserted and role_size and inserted / role_size < 0.55:
            diagnostic = {
                "id": item["id"],
                "page": item["page"],
                "scale": round(inserted / role_size, 3),
            }
            if int(item.get("preserved_anchors", 0)) > 0:
                anchored_scale_exemptions.append(diagnostic)
            else:
                critical_role_scale_violations.append(diagnostic)
    automatic_pass = (
        not blanks
        and not target_cjk
        and not residue_pages
        and not critical_role_scale_violations
        and source_geometry == translated_geometry
        and len(source_reader.pages) == len(translated_reader.pages)
    )
    report = {
        "source_sha256": sha256_file(source_path),
        "translated_sha256": sha256_file(translated_path),
        "rebuild_mode": "raster-safe",
        "flattened_output": True,
        "page_count_source": len(source_reader.pages),
        "page_count_translated": len(translated_reader.pages),
        "page_geometry_match": source_geometry == translated_geometry,
        "translated_blocks": len(blocks) - len(blanks),
        "total_blocks": len(blocks),
        "coverage_percent": round(100 * (len(blocks) - len(blanks)) / max(len(blocks), 1), 2),
        "blank_translation_blocks": blanks,
        "translation_blocks_with_cjk": target_cjk,
        "extractable_cjk_residue": residue_pages,
        "image_text_review_required_pages": [
            page["page"] for page in manifest["pages"] if page["image_count"] > 0
        ],
        "layout_diagnostics": {
            "apply_report_found": apply_report_path.is_file(),
            "fallback_shrink_blocks": fallback_blocks,
            "fallback_shrink_count": len(fallback_blocks),
            "critical_role_scale_violations": critical_role_scale_violations,
            "anchored_scale_exemptions": anchored_scale_exemptions,
            "preserved_anchors": sum(
                int(item.get("preserved_anchors", 0)) for item in apply_report
            ),
            "restored_source_characters": sum(
                int(item.get("restored_source_characters", 0))
                for item in apply_report
            ),
        },
        "automatic_pass": automatic_pass,
        "visual_review_complete": bool(args.visual_review_complete),
        "pass": automatic_pass and bool(args.visual_review_complete),
    }
    write_json(Path(args.report), report)
    print(json.dumps(report, ensure_ascii=False))
    if not report["pass"]:
        raise SystemExit(3)


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract")
    extract.add_argument("--input", required=True)
    extract.add_argument("--manifest", required=True)
    extract.add_argument("--source-language", default="zh")
    extract.add_argument("--target-language", default="en")
    extract.set_defaults(func=extract_command)

    split = commands.add_parser("split")
    split.add_argument("--manifest", required=True)
    split.add_argument("--output-dir", required=True)
    split.add_argument("--max-pages", type=int, default=12)
    split.add_argument("--max-cjk-characters", type=int, default=6000)
    split.add_argument("--force", action="store_true")
    split.set_defaults(func=split_command)

    merge = commands.add_parser("merge")
    merge.add_argument("--manifest", required=True)
    merge.add_argument("--batch", required=True)
    merge.add_argument("--allow-cjk", action="store_true")
    merge.set_defaults(func=merge_command)

    export_translation = commands.add_parser("export-translation")
    export_translation.add_argument("--manifest", required=True)
    export_translation.add_argument("--output", required=True)
    export_translation.set_defaults(func=export_translation_command)

    merge_translation = commands.add_parser("merge-translation")
    merge_translation.add_argument("--manifest", required=True)
    merge_translation.add_argument("--packet", required=True)
    merge_translation.add_argument("--allow-cjk", action="store_true")
    merge_translation.set_defaults(func=merge_translation_command)

    status = commands.add_parser("status")
    status.add_argument("--manifest", required=True)
    status.set_defaults(func=status_command)

    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--input", required=True)
    apply_parser.add_argument("--manifest", required=True)
    apply_parser.add_argument("--output", required=True)
    apply_parser.add_argument("--dpi", type=int, default=200)
    apply_parser.set_defaults(func=apply_command)

    qa = commands.add_parser("qa")
    qa.add_argument("--source", required=True)
    qa.add_argument("--translated", required=True)
    qa.add_argument("--manifest", required=True)
    qa.add_argument("--report", required=True)
    qa.add_argument("--visual-review-complete", action="store_true")
    qa.set_defaults(func=qa_command)
    return root


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
