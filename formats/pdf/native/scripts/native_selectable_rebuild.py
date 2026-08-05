import argparse
import copy
import importlib.util
import io
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream, DictionaryObject, NameObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}
LAYOUT_SCALE = 4.0
MANUAL_TABLE_BLOCK_RANGES: dict[int, tuple[int, int]] = {}
MANUAL_BLOCK_IDS: set[str] = set()
DEFAULT_PIPELINE = Path(__file__).with_name("pdf_translation_pipeline.py")
LIST_ITEM_START_RE = re.compile(
    r"^\s*(?:[-\u2013\u2014\u2022\u00b7]|[\(\[]?\d{1,2}(?:[\)\],]|\.(?!\d)|\u3001)|[IVXLC]+\.)\s*",
    re.IGNORECASE,
)
TOC_ITEM_START_RE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2})+\s*.*\.{5,}\d+\s*$")
DOT_LEADER_TEXT_RE = re.compile(r"^(.*?)(\.{5,})(\d+)\s*$", re.S)


def typography_group(role: str) -> str:
    value = str(role or "").lower()
    if value in {"title", "cover-title"} or value.startswith("heading-1"):
        return "major_title"
    if value in {"subtitle", "subheading"} or value.startswith("heading-"):
        return "minor_title"
    if value.startswith("body-") or value in {"body", "list_item", "warning_body"}:
        return "body"
    return "special"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def apply_page_typography_policy(page_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for block in page_info.get("blocks", []):
        group = typography_group(str(block.get("role", "")))
        if group != "special" and not block.get("render_suppressed"):
            grouped.setdefault(group, []).append(block)
    evidence: dict[str, dict[str, Any]] = {}
    for group, blocks in grouped.items():
        sizes = [float(block.get("style", {}).get("role_size", block.get("style", {}).get("size", 9))) for block in blocks]
        target_size = _median(sizes)
        bold_votes = sum(bool(block.get("style", {}).get("bold", False)) for block in blocks)
        target_bold = bold_votes >= (len(blocks) / 2) if group != "body" else bold_votes > (len(blocks) / 2)
        fonts = [str(block.get("style", {}).get("font", "")) for block in blocks]
        target_font = max(set(fonts), key=fonts.count) if fonts else ""
        for block in blocks:
            block.setdefault("style", {})["role_size"] = target_size
            block["style"]["bold"] = target_bold
            if target_font:
                block["style"]["font"] = target_font
        evidence[group] = {"font_name": target_font, "font_size": target_size, "bold": target_bold, "block_ids": [str(block.get("id", "")) for block in blocks]}
    return evidence
PARAGRAPH_END_RE = re.compile(r"[。！？；.!?;:\uFF1A]\s*$")


def horizontal_text_origin(
    alignment: str, left: float, right: float, text_width: float
) -> float:
    if alignment == "center":
        return (left + right - text_width) / 2
    if alignment == "right":
        return right - text_width
    return left


def infer_block_alignment(block: dict[str, Any], page_width: float) -> str:
    x0, _, x1, _ = [float(value) for value in block["bbox"]]
    if str(block.get("role", "")) == "running-header" and x0 >= page_width * 0.5:
        return "right"
    if int(block.get("style", {}).get("align", 0)) != 1:
        return "left"
    lines = block.get("lines", []) or [{"bbox": block["bbox"]}]
    centers = [
        (float(line["bbox"][0]) + float(line["bbox"][2])) / 2
        for line in lines
    ]
    if len(centers) > 1 and max(centers) - min(centers) > page_width * 0.015:
        return "left"
    if (
        str(block.get("role", "")).startswith("body-")
        and x1 - x0 >= page_width * 0.62
    ):
        return "left"
    margin_difference = abs(x0 - (page_width - x1))
    if margin_difference <= max(8.0, page_width * 0.02):
        return "center"
    return "left"


def _box_contains(box: list[float], point: tuple[float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _smallest_containing_cell(
    page_info: dict[str, Any], line_box: list[float]
) -> list[float] | None:
    center = ((line_box[0] + line_box[2]) / 2, (line_box[1] + line_box[3]) / 2)
    candidates = [
        [float(value) for value in cell["bbox"]]
        for cell in page_info.get("table_cells", [])
        if _box_contains([float(value) for value in cell["bbox"]], center)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))


def table_column_interval(
    page_info: dict[str, Any], line_box: list[float]
) -> list[float] | None:
    raw_boundaries = [
        float(value)
        for cell in page_info.get("table_cells", [])
        for value in (cell["bbox"][0], cell["bbox"][2])
    ]
    if len(raw_boundaries) < 4:
        return None
    clusters: list[list[float]] = []
    for value in sorted(raw_boundaries):
        if clusters and abs(value - sum(clusters[-1]) / len(clusters[-1])) <= 1.5:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    boundaries = sorted(
        sum(cluster) / len(cluster)
        for cluster in clusters
        if len(cluster) >= 2
    )
    center_x = (float(line_box[0]) + float(line_box[2])) / 2
    for left, right in zip(boundaries, boundaries[1:]):
        if (
            left <= center_x <= right
            and float(line_box[0]) >= left - 2
            and float(line_box[2]) <= right + 2
        ):
            return [round(left, 3), round(right, 3)]
    return None


def pretable_cell_box(
    page_info: dict[str, Any], line_box: list[float]
) -> list[float] | None:
    """Recover a first-row cell whose upper border was missed by extraction."""
    cells = [
        [float(value) for value in cell["bbox"]]
        for cell in page_info.get("table_cells", [])
    ]
    if not cells:
        return None
    table_top = min(cell[1] for cell in cells)
    box = [float(value) for value in line_box]
    gap = table_top - box[3]
    if not (0 <= gap <= 40):
        return None
    interval = table_column_interval(page_info, box)
    if interval is None:
        return None
    nearby_tops = []
    for block in page_info.get("blocks", []):
        candidate = [float(value) for value in block["bbox"]]
        center_x = (candidate[0] + candidate[2]) / 2
        candidate_gap = table_top - candidate[3]
        if (
            interval[0] <= center_x <= interval[1]
            and 0 <= candidate_gap <= 40
        ):
            nearby_tops.append(candidate[1])
    top = min(nearby_tops, default=box[1])
    return [interval[0] + 3, top, interval[1] - 3, table_top - 2]


def _near_table_region(
    page_info: dict[str, Any], line_box: list[float], size: float
) -> bool:
    cells = [
        [float(value) for value in cell["bbox"]]
        for cell in page_info.get("table_cells", [])
    ]
    if not cells:
        return False
    table_top = min(cell[1] for cell in cells)
    table_left = min(cell[0] for cell in cells)
    table_right = max(cell[2] for cell in cells)
    center_x = (line_box[0] + line_box[2]) / 2
    gap = table_top - line_box[3]
    return (
        table_left <= center_x <= table_right
        and 0 <= gap <= max(36.0, size * 3.5)
        and line_box[2] - line_box[0] <= float(page_info["width"]) * 0.42
    )


def resolve_text_container(
    page_info: dict[str, Any],
    block: dict[str, Any],
    line: dict[str, Any],
) -> list[float]:
    width = float(page_info["width"])
    line_box = [float(value) for value in line.get("bbox", block["bbox"])]
    cell = _smallest_containing_cell(page_info, line_box)
    size = float(block.get("style", {}).get("role_size", block.get("style", {}).get("size", 9)))
    characters = line.get("characters", []) or block.get("characters", [])
    if (
        characters
        and all(bool(character.get("protected")) for character in characters)
        and line_box[2] - line_box[0] <= size * 2
    ):
        return [
            line_box[0] - 1,
            line_box[1],
            max(line_box[2] + 1, line_box[0] + 6),
            max(line_box[3], line_box[1] + size * 1.28),
        ]
    if cell is not None:
        interval = table_column_interval(page_info, line_box)
        left, right = (interval if interval is not None else [cell[0], cell[2]])
        return [left + 3, max(cell[1] + 2, line_box[1]), right - 3, cell[3] - 2]

    alignment = infer_block_alignment(block, width)
    role = str(block.get("role", ""))
    content_left, content_right = [
        float(value)
        for value in page_info.get("content_bounds", [24.0, width - 24.0])
    ]
    if role.startswith("body-") or role.startswith("heading-"):
        right_side_occupied = any(
            str(other.get("id", "")) != str(block.get("id", ""))
            and float(other["bbox"][0]) >= line_box[2] + 10
            and float(other["bbox"][3]) > line_box[1] - 2
            and float(other["bbox"][1]) < line_box[3] + 2
            for other in page_info.get("blocks", [])
        )
        if not right_side_occupied:
            content_right = max(content_right, width - 42.0)
    if role in {"running-header", "footer"} or alignment == "center":
        left, right = 24.0, width - 24.0
    else:
        left, right = max(content_left, line_box[0]), content_right

    line_top, line_bottom = line_box[1], line_box[3]
    vertical_mid = (line_top + line_bottom) / 2
    for raw_image in (
        page_info.get("image_boxes", []) if role.startswith("body-") else []
    ):
        image = [float(value) for value in raw_image]
        image_width = image[2] - image[0]
        image_height = image[3] - image[1]
        if image_width > width * 0.78 or image_height > float(page_info["height"]) * 0.78:
            continue
        if not (image[1] - 2 <= vertical_mid <= image[3] + 2):
            continue
        if image[0] > left + 10:
            right = min(right, image[0] - 6)
        elif image[2] < right - 10:
            left = max(left, image[2] + 6)

    height_scale = 1.6 if role in {"running-header", "footer"} else 1.28
    bottom = max(line_bottom, line_top + size * height_scale)
    if _near_table_region(page_info, line_box, size):
        table_top = min(
            float(cell["bbox"][1]) for cell in page_info.get("table_cells", [])
        )
        bottom = max(bottom, table_top - 3)
    return [left, line_top, max(left + 2, right), bottom]


def _font_family_key(block: dict[str, Any]) -> str:
    font = str(block.get("style", {}).get("font", "")).casefold()
    return re.sub(r"^[a-z]{6}\+", "", font)


def _flow_compatible(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    if not str(previous.get("role", "")).startswith("body-"):
        return False
    if not str(current.get("role", "")).startswith("body-"):
        return False
    if previous.get("manual_table_parts") is not None or current.get("manual_table_parts") is not None:
        return False
    if previous.get("force_block_mode") or current.get("force_block_mode"):
        return False
    if tuple(previous.get("style", {}).get("color_rgb", [])) != tuple(current.get("style", {}).get("color_rgb", [])):
        return False
    if bool(previous.get("style", {}).get("bold")) != bool(current.get("style", {}).get("bold")):
        return False
    if abs(float(previous["style"].get("size", 9)) - float(current["style"].get("size", 9))) > 0.6:
        return False
    if _font_family_key(previous) != _font_family_key(current):
        return False
    reviewed_group = str(previous.get("reviewed_flow_group", "")).strip()
    reviewed_join = bool(reviewed_group) and reviewed_group == str(
        current.get("reviewed_flow_group", "")
    ).strip()
    current_source = str(current.get("source_text", ""))
    if not reviewed_join and (
        LIST_ITEM_START_RE.match(current_source) or TOC_ITEM_START_RE.match(current_source)
    ):
        return False
    previous_source = str(previous.get("source_text", "")).strip()
    if (
        not reviewed_join
        and
        PARAGRAPH_END_RE.search(previous_source)
        and not previous_source.endswith((";", "\uff1b"))
    ):
        return False
    gap = float(current["bbox"][1]) - float(previous["bbox"][3])
    size = max(float(previous["style"].get("size", 9)), float(current["style"].get("size", 9)))
    return -1.0 <= gap <= size * 1.35


def apply_reviewed_text_region_adjustments(pages: list[dict[str, Any]]) -> None:
    def shift_geometry(value: Any, dy: float, seen: set[int]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if (
                    key == "bbox"
                    and isinstance(child, list)
                    and len(child) == 4
                    and all(isinstance(item, (int, float)) for item in child)
                ):
                    if id(child) in seen:
                        continue
                    seen.add(id(child))
                    child[1] = float(child[1]) + dy
                    child[3] = float(child[3]) + dy
                else:
                    shift_geometry(child, dy, seen)
        elif isinstance(value, list):
            for child in value:
                shift_geometry(child, dy, seen)

    for page in pages:
        blocks_by_id = {str(block.get("id")): block for block in page.get("blocks", [])}
        for group in page.get("reviewed_flow_groups", []):
            group_id = str(group["id"])
            for block_id in group.get("block_ids", []):
                block = blocks_by_id.get(str(block_id))
                if block is not None:
                    block["reviewed_flow_group"] = group_id
        for adjustment in page.get("reviewed_text_region_adjustments", []):
            dy = float(adjustment.get("dy", 0))
            for block_id in adjustment.get("block_ids", []):
                block = blocks_by_id.get(str(block_id))
                if block is not None:
                    shift_geometry(block, dy, set())


def group_paragraph_flows(page_info: dict[str, Any]) -> list[dict[str, Any]]:
    all_blocks = page_info.get("blocks", [])
    block_positions = {block["id"]: index for index, block in enumerate(all_blocks)}
    groups: list[list[dict[str, Any]]] = []
    for block in all_blocks:
        if block.get("render_suppressed"):
            continue
        if not str(block.get("role", "")).startswith("body-"):
            continue
        if infer_block_alignment(block, float(page_info["width"])) == "center":
            continue
        if _smallest_containing_cell(page_info, [float(value) for value in block["bbox"]]) is not None:
            continue
        if _near_table_region(
            page_info,
            [float(value) for value in block["bbox"]],
            float(block.get("style", {}).get("size", 9)),
        ):
            continue
        if groups and _flow_compatible(groups[-1][-1], block):
            groups[-1].append(block)
        else:
            groups.append([block])

    output: list[dict[str, Any]] = []
    for blocks in groups:
        slots: list[list[float]] = []
        for block in blocks:
            lines = block.get("lines", []) or [{"bbox": block["bbox"]}]
            slots.extend(resolve_text_container(page_info, block, line) for line in lines)
        if slots:
            last_position = block_positions[blocks[-1]["id"]]
            has_following_block = last_position + 1 < len(all_blocks)
            next_top = (
                float(all_blocks[last_position + 1]["bbox"][1])
                if has_following_block
                else float(slots[-1][3])
            )
            tops = [float(slot[1]) for slot in slots]
            source_size = float(blocks[0].get("style", {}).get("size", 9))
            pitch_candidates = [
                later - earlier
                for earlier, later in zip(tops, tops[1:])
                if later - earlier > source_size * 0.8
            ]
            pitch = (
                sorted(pitch_candidates)[len(pitch_candidates) // 2]
                if pitch_candidates
                else source_size * 1.95
            )
            new_top = tops[-1] + pitch
            added_slots = 0
            while (
                has_following_block
                and added_slots < 2
                and new_top + source_size * 0.75 <= next_top - 2
            ):
                synthetic_line = {
                    "bbox": [
                        float(slots[-1][0]),
                        new_top,
                        float(slots[-1][2]),
                        new_top + source_size,
                    ]
                }
                candidate_slot = resolve_text_container(
                    page_info, blocks[-1], synthetic_line
                )
                candidate_width = max(1.0, candidate_slot[2] - candidate_slot[0])
                intended_width = max(
                    1.0,
                    float(synthetic_line["bbox"][2])
                    - float(synthetic_line["bbox"][0]),
                )
                blocked_by_image = any(
                    (
                        not (
                            float(image[3]) <= candidate_slot[1]
                            or float(image[1]) >= candidate_slot[3]
                        )
                        and (
                            max(
                                0.0,
                                min(float(image[2]), candidate_slot[2])
                                - max(float(image[0]), candidate_slot[0]),
                            )
                            >= candidate_width * 0.6
                            or max(
                                0.0,
                                min(float(image[2]), float(synthetic_line["bbox"][2]))
                                - max(float(image[0]), float(synthetic_line["bbox"][0])),
                            )
                            >= intended_width * 0.6
                        )
                    )
                    for image in page_info.get("image_boxes", [])
                )
                if blocked_by_image:
                    break
                slots.append(candidate_slot)
                new_top += pitch
                added_slots += 1
        output.append(
            {
                "id": "+".join(block["id"] for block in blocks),
                "block_ids": [block["id"] for block in blocks],
                "blocks": blocks,
                "text": " ".join(
                    str(block.get("render_translation_override", block.get("translation", ""))).strip()
                    for block in blocks
                    if str(block.get("render_translation_override", block.get("translation", ""))).strip()
                ),
                "style": copy.deepcopy(blocks[0]["style"]),
                "role": blocks[0].get("role"),
                "slots": slots,
                "alignment": "left",
            }
        )
    return output


def group_table_cell_flows(page_info: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, float, float, float], list[dict[str, Any]]] = {}
    cell_lookup: dict[tuple[float, float, float, float], list[float]] = {}
    for block in page_info.get("blocks", []):
        if block.get("render_suppressed") or block.get("manual_table_parts") is not None:
            continue
        lines = block.get("lines", []) or [{"bbox": block["bbox"], "segments": []}]
        segment_cells = {
            int(segment.get("cell_index", -1))
            for line in lines
            for segment in line.get("segments", [])
            if int(segment.get("cell_index", -1)) >= 0
        }
        if len(segment_cells) > 1:
            continue
        cell = _smallest_containing_cell(
            page_info, [float(value) for value in block["bbox"]]
        )
        if cell is None:
            continue
        key = tuple(round(value, 2) for value in cell)
        grouped.setdefault(key, []).append(block)
        cell_lookup[key] = cell

    output: list[dict[str, Any]] = []
    for key, blocks in grouped.items():
        if len(blocks) < 2:
            continue
        blocks.sort(key=lambda block: (float(block["bbox"][1]), float(block["bbox"][0])))
        cell = cell_lookup[key]
        text = " ".join(
            str(block.get("render_translation_override", block.get("translation", ""))).strip()
            for block in blocks
            if str(block.get("render_translation_override", block.get("translation", ""))).strip()
        )
        if not text:
            continue
        output.append(
            {
                "id": "+".join(block["id"] for block in blocks),
                "block_ids": [block["id"] for block in blocks],
                "blocks": blocks,
                "text": text,
                "style": copy.deepcopy(blocks[0]["style"]),
                "role": blocks[0].get("role"),
                "box": [cell[0] + 3, cell[1] + 2, cell[2] - 3, cell[3] - 2],
                "alignment": "left",
                "source_top": min(float(block["bbox"][1]) for block in blocks),
                "fragments": [
                    {
                        "block_id": block["id"],
                        "text": str(
                            block.get(
                                "render_translation_override",
                                block.get("translation", ""),
                            )
                        ).strip(),
                        "box": [cell[0] + 3, cell[1] + 2, cell[2] - 3, cell[3] - 2],
                        "source_top": float(block["bbox"][1]),
                        "source_left": float(block["bbox"][0]),
                        "style": copy.deepcopy(block["style"]),
                        "role": block.get("role"),
                        "alignment": "left",
                    }
                    for block in blocks
                ],
            }
        )
    return output


def aggregate_table_fragments(
    fragments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build exactly one render flow for each physical table cell.

    PDF extractors often split one cell into several blocks and can also emit a
    single block that crosses several cells.  Rendering those blocks
    independently duplicates text and creates collisions.  Aggregating the
    already segmented fragments by cell makes the cell, rather than the source
    extraction block, the atomic layout container.
    """
    grouped: dict[tuple[float, float, float, float], list[dict[str, Any]]] = {}
    for fragment in fragments:
        key = tuple(round(float(value), 2) for value in fragment["box"])
        grouped.setdefault(key, []).append(fragment)

    output: list[dict[str, Any]] = []
    for key, items in grouped.items():
        items.sort(
            key=lambda item: (
                float(item.get("source_top", 0)),
                float(item.get("source_left", 0)),
                str(item.get("block_id", "")),
            )
        )
        text = " ".join(
            str(item.get("text", "")).strip()
            for item in items
            if str(item.get("text", "")).strip()
        )
        if not text:
            continue
        block_ids = list(dict.fromkeys(str(item["block_id"]) for item in items))
        first = items[0]
        output.append(
            {
                "id": "cell:" + "+".join(block_ids),
                "block_ids": block_ids,
                "text": text,
                "style": copy.deepcopy(first["style"]),
                "role": first.get("role"),
                "box": [float(value) for value in key],
                "alignment": str(first.get("alignment", "left")),
                "color": tuple(
                    int(value)
                    for value in first.get(
                        "color",
                        first.get("style", {}).get("color_rgb", [0, 0, 0]),
                    )
                ),
                "source_top": min(float(item.get("source_top", 0)) for item in items),
                "fragments": items,
            }
        )
    return sorted(output, key=lambda flow: (flow["box"][1], flow["box"][0]))


def merge_table_cell_flows(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge segmented and legacy table flows at fragment granularity."""
    fragments: list[dict[str, Any]] = []
    for flow in flows:
        if flow.get("fragments"):
            fragments.extend(flow["fragments"])
            continue
        for index, block_id in enumerate(flow.get("block_ids", [])):
            fragments.append(
                {
                    "block_id": block_id,
                    "text": flow.get("text", "") if index == 0 else "",
                    "box": flow["box"],
                    "source_top": flow.get("source_top", flow["box"][1]),
                    "source_left": flow.get("source_left", flow["box"][0]),
                    "style": copy.deepcopy(flow["style"]),
                    "role": flow.get("role"),
                    "alignment": flow.get("alignment", "left"),
                    "color": flow.get("color", flow["style"].get("color_rgb", [0, 0, 0])),
                }
            )
    return aggregate_table_fragments(fragments)


def build_table_cell_render_plan(
    page_info: dict[str, Any], pipeline
) -> tuple[list[dict[str, Any]], set[str]]:
    """Segment cross-cell blocks, then aggregate all text by physical cell."""
    fragments: list[dict[str, Any]] = []
    consumed: set[str] = set()
    table_cells = page_info.get("table_cells", [])
    if not table_cells:
        return [], consumed

    for block in page_info.get("blocks", []):
        if block.get("render_suppressed"):
            continue
        translation = pipeline.prepared_translation(block)
        source_lines = block.get("lines", [])
        if not translation or not source_lines:
            continue
        target_lines = translation.splitlines()
        if len(target_lines) > len(source_lines):
            continue
        target_lines.extend([""] * (len(source_lines) - len(target_lines)))

        manual_parts = block.get("manual_table_parts")
        if manual_parts is not None and len(manual_parts) != len(source_lines):
            raise ValueError(f"manual_table_parts line count mismatch: {block['id']}")

        block_fragments: list[dict[str, Any]] = []
        mapped_nonempty_lines = 0
        mapping_failed = False
        for line_index, (line, target_line) in enumerate(
            zip(source_lines, target_lines)
        ):
            if not target_line.strip():
                continue
            line_box = [float(value) for value in line["bbox"]]
            synthetic_cell = pretable_cell_box(page_info, line_box)
            if synthetic_cell is not None and manual_parts is None:
                items = [
                    {
                        "text": target_line,
                        "left": synthetic_cell[0],
                        "right": synthetic_cell[2],
                    }
                ]
            elif manual_parts is not None:
                parts = manual_parts[line_index]
                if parts is None:
                    synthetic_cell = line_box
                    items = [{
                        "text": target_line,
                        "left": line_box[0],
                        "right": line_box[2],
                    }]
                else:
                    placeholders = " ".join(f"CELL{index}" for index in range(len(parts)))
                    items = pipeline.table_segment_targets(line, placeholders, table_cells)
                    if len(items) != len(parts):
                        raise ValueError(
                            f"manual_table_parts cell count mismatch: {block['id']} "
                            f"({len(parts)} parts, {len(items)} cells)"
                        )
                    for item, part in zip(items, parts):
                        item["text"] = str(part)
            else:
                items = pipeline.table_segment_targets(line, target_line, table_cells)
            if not items:
                mapping_failed = True
                break

            interval = table_column_interval(page_info, line_box) if len(items) == 1 else None
            line_fragments: list[dict[str, Any]] = []
            for item in items:
                probe = [
                    float(item["left"]),
                    line_box[1],
                    float(item["right"]),
                    line_box[3],
                ]
                cell = _smallest_containing_cell(page_info, probe)
                if synthetic_cell is not None:
                    cell_box = [float(value) for value in synthetic_cell]
                elif cell is None:
                    mapping_failed = True
                    break
                else:
                    left, right = (
                        (interval[0], interval[1])
                        if interval is not None
                        else (cell[0], cell[2])
                    )
                    cell_box = [left + 3, cell[1] + 2, right - 3, cell[3] - 2]
                color = tuple(
                    pipeline.source_line_color(
                        line,
                        [
                            int(value)
                            for value in block.get("style", {}).get(
                                "color_rgb", [0, 0, 0]
                            )
                        ],
                    )
                )
                line_fragments.append(
                    {
                        "block_id": block["id"],
                        "text": str(item.get("text", "")),
                        "box": cell_box,
                        "source_top": line_box[1],
                        "source_left": float(item["left"]),
                        "style": copy.deepcopy(block["style"]),
                        "role": block.get("role"),
                        "alignment": "left",
                        "color": color,
                    }
                )
            if mapping_failed:
                break
            block_fragments.extend(line_fragments)
            mapped_nonempty_lines += 1

        if not mapping_failed and mapped_nonempty_lines and block_fragments:
            fragments.extend(block_fragments)
            consumed.add(str(block["id"]))

    return aggregate_table_fragments(fragments), consumed


def minimum_body_font_size(style: dict[str, Any]) -> float:
    raw = max(9.5, float(style.get("size", 9)) * 0.6)
    return math.floor(raw * 4) / 4


def harmonize_flow_font_sizes(
    flows: list[dict[str, Any]],
    pipeline,
    scratch: ImageDraw.ImageDraw,
    uniform_body_font_size: float | None = None,
) -> None:
    if uniform_body_font_size is not None:
        target = float(uniform_body_font_size)
        for flow in flows:
            flow["target_font_size"] = target
            flow["style"]["role_size"] = target
            flow["fixed_body_font_size"] = True
        return
    fitted_by_role: dict[str, list[float]] = {}
    for flow in flows:
        style = flow["style"]
        source_size = float(style.get("role_size", style.get("size", 9)))
        try:
            font, _, _ = fit_text_to_slots(
                scratch,
                flow["text"],
                pipeline.font_file(style),
                source_size * LAYOUT_SCALE,
                flow["slots"],
                minimum_scale=0.35,
            )
            fitted_size = float(font.size) / LAYOUT_SCALE
        except ValueError:
            fitted_size = minimum_body_font_size(style)
        fitted_by_role.setdefault(typography_group(str(flow.get("role", "body"))), []).append(
            fitted_size
        )
    source_by_role: dict[str, list[float]] = {}
    for flow in flows:
        source_by_role.setdefault(typography_group(str(flow.get("role", "body"))), []).append(
            float(flow["style"].get("size", 9))
        )

    def middle(values: list[float]) -> float:
        ordered = sorted(values)
        index = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[index]
        return (ordered[index - 1] + ordered[index]) / 2

    target_by_role = {}
    for role, sizes in fitted_by_role.items():
        source_median = middle(source_by_role[role])
        target_by_role[role] = max(
            minimum_body_font_size({"size": source_median}),
            min(min(sizes), source_median),
        )
    for flow in flows:
        target = target_by_role[typography_group(str(flow.get("role", "body")))]
        flow["target_font_size"] = target
        flow["style"]["role_size"] = target


def fit_text_to_slots(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    original_size_px: float,
    slots: list[list[float]],
    minimum_scale: float = 0.62,
):
    size = max(int(round(original_size_px)), 6)
    minimum = max(int(round(size * minimum_scale)), 6)
    words = text.split()
    while size >= minimum:
        font = ImageFont.truetype(font_path, size=size)
        ascent, descent = font.getmetrics()
        if all((ascent + descent) <= max(1, (slot[3] - slot[1]) * LAYOUT_SCALE) for slot in slots):
            lines: list[str] = []
            cursor = 0
            valid = True
            for slot in slots:
                if cursor >= len(words):
                    break
                available = max(1.0, (slot[2] - slot[0]) * LAYOUT_SCALE)
                line_words: list[str] = []
                while cursor < len(words):
                    candidate_words = line_words + [words[cursor]]
                    candidate = " ".join(candidate_words)
                    if draw.textlength(candidate, font=font) <= available:
                        line_words = candidate_words
                        cursor += 1
                    else:
                        break
                if not line_words:
                    valid = False
                    break
                lines.append(" ".join(line_words))
            if valid and cursor == len(words):
                return font, lines, max(1, round(size * 0.08))
        size -= 1
    raise ValueError("Translated paragraph does not fit the source flow slots.")


def fit_flow_text_to_slots(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    original_size_px: float,
    slots: list[list[float]],
    minimum_scale: float,
):
    try:
        font, lines, spacing = fit_text_to_slots(
            draw,
            text,
            font_path,
            original_size_px,
            slots,
            minimum_scale=minimum_scale,
        )
        return font, lines, False
    except ValueError:
        font, lines, spacing = fit_text_to_slots(
            draw,
            text,
            font_path,
            original_size_px,
            slots,
            minimum_scale=0.55,
        )
        return font, lines, True


def compact_dot_leader_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    font_size_px: float,
    available_width_px: float,
) -> str:
    match = DOT_LEADER_TEXT_RE.match(text)
    if not match:
        return text
    prefix = match.group(1).rstrip()
    suffix = match.group(3)
    original_count = len(match.group(2))
    font = ImageFont.truetype(font_path, size=max(6, int(round(font_size_px))))
    dot_width = max(0.1, float(draw.textlength(".", font=font)))
    fixed_width = float(draw.textlength(prefix + suffix, font=font))
    count = min(original_count, max(5, int((available_width_px - fixed_width) // dot_width)))
    candidate = prefix + "." * count + suffix
    while count > 5 and draw.textlength(candidate, font=font) > available_width_px:
        count -= 1
        candidate = prefix + "." * count + suffix
    return candidate


def load_pipeline(path: Path):
    spec = importlib.util.spec_from_file_location("pdf_translation_pipeline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import translation pipeline: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def strip_text_stream(stream_object, pdf) -> int:
    content = ContentStream(stream_object, pdf)
    original_count = len(content.operations)
    content.operations = [
        (operands, operator)
        for operands, operator in content.operations
        if operator not in TEXT_SHOW_OPERATORS
    ]
    removed = original_count - len(content.operations)
    stream_object.set_data(content.get_data())
    return removed


def strip_form_text(resources, pdf, visited: set[tuple[int, int]]) -> int:
    if not resources:
        return 0
    resources = resources.get_object()
    xobjects = resources.get("/XObject")
    if not xobjects:
        return 0
    removed = 0
    for reference in xobjects.get_object().values():
        key = (
            int(getattr(reference, "idnum", id(reference))),
            int(getattr(reference, "generation", 0)),
        )
        if key in visited:
            continue
        visited.add(key)
        object_ = reference.get_object()
        if object_.get("/Subtype") != "/Form":
            continue
        removed += strip_text_stream(object_, pdf)
        removed += strip_form_text(object_.get("/Resources"), pdf, visited)
    return removed


def strip_native_text(source: Path) -> tuple[PdfWriter, int]:
    reader = PdfReader(str(source))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    removed = 0
    visited: set[tuple[int, int]] = set()
    for page in writer.pages:
        contents = page.get("/Contents")
        if contents:
            removed += strip_text_stream(contents.get_object(), writer)
        removed += strip_form_text(page.get("/Resources"), writer, visited)
    return writer, removed


def font_key(style: dict[str, Any]) -> str:
    if style.get("bold") and style.get("italic"):
        return "ArialV5-BoldItalic"
    if style.get("bold"):
        return "ArialV5-Bold"
    if style.get("italic"):
        return "ArialV5-Italic"
    return "ArialV5"


def register_fonts() -> dict[str, str]:
    fonts = {
        "ArialV5": r"C:\Windows\Fonts\arial.ttf",
        "ArialV5-Bold": r"C:\Windows\Fonts\arialbd.ttf",
        "ArialV5-Italic": r"C:\Windows\Fonts\ariali.ttf",
        "ArialV5-BoldItalic": r"C:\Windows\Fonts\arialbi.ttf",
    }
    for name, path in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, path))
    return fonts


def draw_fitted_text(
    pdf: canvas.Canvas,
    pipeline,
    scratch: ImageDraw.ImageDraw,
    *,
    text: str,
    style: dict[str, Any],
    color: tuple[int, int, int],
    box: tuple[float, float, float, float],
    page_height: float,
    minimum_scale: float = 0.82,
    alignment: str = "left",
) -> dict[str, Any]:
    x0, top, x1, bottom = box
    font_path = pipeline.font_file(style)
    original_size = (
        float(style.get("role_size", style.get("size", 9))) * LAYOUT_SCALE
    )
    width = max(int(round((x1 - x0 - 2) * LAYOUT_SCALE)), 1)
    height = max(int(round((bottom - top - 2) * LAYOUT_SCALE)), 1)
    fallback = False
    try:
        font, rendered, spacing = pipeline.fit_text(
            scratch,
            text,
            font_path,
            original_size,
            width,
            height,
            minimum_scale=minimum_scale,
        )
    except ValueError:
        fallback = True
        try:
            font, rendered, spacing = pipeline.fit_text(
                scratch,
                text,
                font_path,
                original_size,
                width,
                height,
                minimum_scale=0.45,
            )
        except ValueError as error:
            raise ValueError(
                f"Text cannot fit: {text!r}, box={box}, "
                f"size={original_size}, width={width}, height={height}"
            ) from error

    font_name = font_key(style)
    font_size = float(font.size) / LAYOUT_SCALE
    ascent, descent = font.getmetrics()
    ascent /= LAYOUT_SCALE
    descent /= LAYOUT_SCALE
    leading = float(ascent + descent + spacing / LAYOUT_SCALE)
    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(
        color[0] / 255.0,
        color[1] / 255.0,
        color[2] / 255.0,
    )
    drawn_boxes: list[list[float]] = []
    for index, line in enumerate(rendered.splitlines() or [""]):
        line_width = pdfmetrics.stringWidth(line, font_name, font_size)
        origin_x = horizontal_text_origin(
            alignment, x0 + 1, x1 - 1, line_width
        )
        line_top = top + 1 + index * leading
        pdf.drawString(origin_x, page_height - line_top - ascent, line)
        drawn_boxes.append(
            [origin_x, line_top, origin_x + line_width, line_top + ascent + descent]
        )
    return {
        "font_size": font_size,
        "source_font_size": float(style.get("role_size", style.get("size", 9))),
        "font_name": font_name,
        "bold": bool(style.get("bold")),
        "fallback_shrink": fallback,
        "rendered": rendered,
        "box": [round(value, 3) for value in box],
        "alignment": alignment,
        "drawn_boxes": [
            [round(value, 3) for value in drawn_box]
            for drawn_box in drawn_boxes
        ],
    }


def draw_flow_text(
    pdf: canvas.Canvas,
    pipeline,
    scratch: ImageDraw.ImageDraw,
    *,
    flow: dict[str, Any],
    color: tuple[int, int, int],
    page_height: float,
) -> dict[str, Any]:
    style = flow["style"]
    source_size = float(style.get("role_size", style.get("size", 9)))
    fallback = False
    minimum_scale = min(
        1.0,
        minimum_body_font_size(style) / max(source_size, 0.1),
    )
    flow_text = flow["text"]
    if len(flow["slots"]) == 1:
        slot = flow["slots"][0]
        flow_text = compact_dot_leader_text(
            scratch,
            flow_text,
            pipeline.font_file(style),
            source_size * LAYOUT_SCALE,
            max(1.0, (float(slot[2]) - float(slot[0])) * LAYOUT_SCALE),
        )
    try:
        if flow.get("fixed_body_font_size"):
            font, lines, _ = fit_text_to_slots(
                scratch,
                flow_text,
                pipeline.font_file(style),
                source_size * LAYOUT_SCALE,
                flow["slots"],
                minimum_scale=1.0,
            )
        else:
            font, lines, fallback = fit_flow_text_to_slots(
                scratch,
                flow_text,
                pipeline.font_file(style),
                source_size * LAYOUT_SCALE,
                flow["slots"],
                minimum_scale=minimum_scale,
            )
    except ValueError as error:
        raise ValueError(
            f"Paragraph flow cannot fit at the readable source-relative floor: "
            f"{flow['id']}, text={flow['text']!r}, slots={flow['slots']}"
        ) from error

    font_name = font_key(style)
    font_size = float(font.size) / LAYOUT_SCALE
    ascent, descent = font.getmetrics()
    ascent /= LAYOUT_SCALE
    descent /= LAYOUT_SCALE
    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
    drawn_boxes: list[list[float]] = []
    for line, slot in zip(lines, flow["slots"]):
        left, top, right, _ = [float(value) for value in slot]
        text_width = pdfmetrics.stringWidth(line, font_name, font_size)
        origin_x = horizontal_text_origin(flow.get("alignment", "left"), left, right, text_width)
        pdf.drawString(origin_x, page_height - top - ascent, line)
        drawn_boxes.append([origin_x, top, origin_x + text_width, top + ascent + descent])

    return {
        "font_size": font_size,
        "source_font_size": source_size,
        "font_name": font_name,
        "bold": bool(style.get("bold")),
        "fallback_shrink": fallback,
        "rendered": "\n".join(lines),
        "box": [
            round(min(slot[0] for slot in flow["slots"]), 3),
            round(min(slot[1] for slot in flow["slots"]), 3),
            round(max(slot[2] for slot in flow["slots"]), 3),
            round(max(slot[3] for slot in flow["slots"]), 3),
        ],
        "alignment": flow.get("alignment", "left"),
        "slots": [[round(value, 3) for value in slot] for slot in flow["slots"]],
        "drawn_boxes": [
            [round(value, 3) for value in drawn_box]
            for drawn_box in drawn_boxes
        ],
        "block_ids": flow["block_ids"],
    }


def anchor_items(
    pipeline,
    line: dict[str, Any],
    target: str,
    left: float,
    right: float,
) -> list[dict[str, Any]]:
    anchors = pipeline.line_anchor_plan(line, target)
    items = pipeline.target_segments(target, anchors, left, right)
    for anchor in anchors:
        characters = [
            line["characters"][index] for index in anchor["character_indices"]
        ]
        color = tuple(
            int(value)
            for value in characters[0].get("color_rgb", [0, 0, 0])
        )
        items.append(
            {
                "text": anchor["text"],
                "left": float(anchor["bbox"][0]),
                "right": float(anchor["bbox"][2]),
                "top": float(anchor["bbox"][1]),
                "bottom": float(anchor["bbox"][3]),
                "color": color,
                "is_anchor": True,
            }
        )
    return sorted(items, key=lambda item: float(item["left"]))


def make_overlay(
    page_info: dict[str, Any],
    pipeline,
    font_paths: dict[str, str],
) -> tuple[bytes, list[dict[str, Any]]]:
    del font_paths
    width = float(page_info["width"])
    height = float(page_info["height"])
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1)
    scratch_image = Image.new("RGB", (8, 8), "white")
    scratch = ImageDraw.Draw(scratch_image)
    report: list[dict[str, Any]] = []
    blocks = page_info["blocks"]
    page_info["typography_evidence"] = apply_page_typography_policy(page_info)
    segmented_table_flows, segmented_table_ids = build_table_cell_render_plan(
        page_info, pipeline
    )
    legacy_table_flows = [
        flow
        for flow in group_table_cell_flows(page_info)
        if not any(block_id in segmented_table_ids for block_id in flow["block_ids"])
    ]
    table_cell_flows = merge_table_cell_flows(
        segmented_table_flows + legacy_table_flows
    )
    table_flow_member_ids = {
        block_id for flow in table_cell_flows for block_id in flow["block_ids"]
    }
    paragraph_flows = group_paragraph_flows(page_info)
    harmonize_flow_font_sizes(
        paragraph_flows,
        pipeline,
        scratch,
        uniform_body_font_size=page_info.get("uniform_body_font_size"),
    )
    flow_by_first_id = {flow["block_ids"][0]: flow for flow in paragraph_flows}
    flow_member_ids = {
        block_id for flow in paragraph_flows for block_id in flow["block_ids"]
    }

    # Table cells are atomic containers. Draw every cell exactly once before
    # walking the source blocks, then skip every consumed extraction block.
    for flow in table_cell_flows:
        style = flow["style"]
        color = tuple(
            int(value)
            for value in flow.get("color", style.get("color_rgb", [0, 0, 0]))
        )
        draw = draw_fitted_text(
            pdf,
            pipeline,
            scratch,
            text=flow["text"],
            style=style,
            color=color,
            box=tuple(float(value) for value in flow["box"]),
            page_height=height,
            minimum_scale=0.35,
            alignment=flow["alignment"],
        )
        draw["block_ids"] = flow["block_ids"]
        report.append(
            {
                "id": flow["id"],
                "page": page_info["page"],
                "role": flow.get("role"),
                "draws": [draw],
            }
        )

    for block_index, block in enumerate(blocks):
        if block["id"] in MANUAL_BLOCK_IDS:
            continue
        manual_range = MANUAL_TABLE_BLOCK_RANGES.get(
            int(page_info["page"])
        )
        block_number = int(block["id"].rsplit("b", 1)[1])
        if (
            manual_range
            and manual_range[0] <= block_number <= manual_range[1]
        ):
            continue
        if block["id"] in table_flow_member_ids:
            continue
        if block["id"] in flow_member_ids:
            flow = flow_by_first_id.get(block["id"])
            if flow is None:
                continue
            style = flow["style"]
            color = tuple(int(value) for value in style.get("color_rgb", [0, 0, 0]))
            flow_draw = draw_flow_text(
                pdf,
                pipeline,
                scratch,
                flow=flow,
                color=color,
                page_height=height,
            )
            report.append(
                {
                    "id": flow["id"],
                    "page": page_info["page"],
                    "role": block.get("role"),
                    "draws": [flow_draw],
                }
            )
            continue
        translation = pipeline.prepared_translation(block)
        if not translation:
            continue
        style = copy.deepcopy(block["style"])
        default_color = tuple(
            int(value) for value in style.get("color_rgb", [0, 0, 0])
        )
        source_lines = block.get("lines", [])
        target_lines = translation.splitlines() if translation else []
        if source_lines and len(target_lines) <= len(source_lines):
            target_lines.extend([""] * (len(source_lines) - len(target_lines)))
        candidate_anchors = [
            pipeline.line_anchor_plan(line, target_line)
            for line, target_line in zip(source_lines, target_lines)
        ]
        candidate_tables = [
            pipeline.table_segment_targets(
                line, target_line, page_info.get("table_cells", [])
            )
            if target_line.strip()
            else []
            for line, target_line in zip(source_lines, target_lines)
        ]
        manual_table_parts = block.get("manual_table_parts")
        if manual_table_parts is not None:
            if len(manual_table_parts) != len(source_lines):
                raise ValueError(
                    f"manual_table_parts line count mismatch: {block['id']}"
                )
            candidate_tables = []
            for line, parts in zip(source_lines, manual_table_parts):
                placeholders = " ".join(
                    f"CELL{index}" for index in range(len(parts))
                )
                items = pipeline.table_segment_targets(
                    line, placeholders, page_info.get("table_cells", [])
                )
                if len(items) != len(parts):
                    raise ValueError(
                        f"manual_table_parts cell count mismatch: {block['id']} "
                        f"({len(parts)} parts, {len(items)} cells)"
                    )
                for item, part in zip(items, parts):
                    item["text"] = str(part)
                candidate_tables.append(items)
        line_colors = {
            tuple(pipeline.source_line_color(line, [0, 0, 0]))
            for line in source_lines
        }
        line_mode = (
            bool(source_lines)
            and len(target_lines) == len(source_lines)
            and not block.get("force_block_mode")
            and (
                len(source_lines) <= 1
                or any(candidate_anchors)
                or any(candidate_tables)
                or len(line_colors) > 1
            )
        )
        block_draws: list[dict[str, Any]] = []

        if line_mode:
            for line, target_line, table_items in zip(
                source_lines, target_lines, candidate_tables
            ):
                if not target_line.strip():
                    continue
                container = resolve_text_container(page_info, block, line)
                left, container_top, right, container_bottom = container
                color = tuple(
                    pipeline.source_line_color(
                        line,
                        [int(value) for value in default_color],
                    )
                )
                if table_items:
                    items = table_items
                else:
                    items = anchor_items(
                        pipeline, line, target_line, left, right
                    )
                    if not items:
                        items = [
                            {
                                "text": target_line,
                                "left": left,
                                "right": right,
                            }
                        ]
                for item in items:
                    if not str(item.get("text", "")).strip():
                        continue
                    top = float(item.get("top", line["bbox"][1]))
                    bottom = float(
                        item.get(
                            "bottom",
                            container_bottom,
                        )
                    )
                    item_color = tuple(item.get("color", color))
                    item_left = float(item["left"])
                    item_right = float(item["right"])
                    if table_items:
                        interval = table_column_interval(
                            page_info,
                            [float(value) for value in line["bbox"]],
                        )
                        if interval is not None:
                            item_left = max(item_left, interval[0] + 3)
                            item_right = min(item_right, interval[1] - 3)
                    block_draws.append(
                        draw_fitted_text(
                            pdf,
                            pipeline,
                            scratch,
                            text=str(item["text"]),
                            style=style,
                            color=item_color,
                            box=(
                                item_left,
                                top,
                                item_right,
                                bottom,
                            ),
                            page_height=height,
                            alignment=(
                                "left"
                                if table_items or item.get("is_anchor")
                                else infer_block_alignment(block, width)
                            ),
                        )
                    )
        else:
            reference_line = source_lines[0] if source_lines else {"bbox": block["bbox"]}
            x0, top, right, bottom = resolve_text_container(
                page_info, block, reference_line
            )
            render_translation = " ".join(translation.split())
            block_draws.append(
                draw_fitted_text(
                    pdf,
                    pipeline,
                    scratch,
                    text=render_translation,
                    style=style,
                    color=default_color,
                    box=(x0, top, right, bottom),
                    page_height=height,
                    minimum_scale=0.5,
                    alignment=infer_block_alignment(block, width),
                )
            )

        report.append(
            {
                "id": block["id"],
                "page": page_info["page"],
                "role": block.get("role"),
                "draws": block_draws,
            }
        )

    pdf.save()
    scratch_image.close()
    return stream.getvalue(), report


def rebuild(
    source: Path,
    manifest_path: Path,
    output: Path,
    pipeline_path: Path,
) -> None:
    pipeline = load_pipeline(pipeline_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pipeline.enrich_manifest_layout(source, manifest)
    apply_reviewed_text_region_adjustments(manifest["pages"])
    missing = [
        block["id"]
        for page in manifest["pages"]
        for block in page["blocks"]
        if not (block.get("translation") or "").strip()
    ]
    if missing:
        raise ValueError(f"Missing translation: {missing[0]}")

    fonts = register_fonts()
    writer, removed_text_operations = strip_native_text(source)
    report: list[dict[str, Any]] = []
    for page, page_info in zip(writer.pages, manifest["pages"]):
        overlay_bytes, page_report = make_overlay(page_info, pipeline, fonts)
        overlay = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
        page.merge_page(overlay, over=True)
        report.extend(page_report)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        writer.write(stream)
    report_path = output.with_suffix(".rebuild-report.json")
    report_path.write_text(
        json.dumps(
            {
                "source": str(source),
                "output": str(output),
                "mode": "native-graphics-selectable-vector-text",
                "removed_native_text_operations": removed_text_operations,
                "blocks": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "removed_native_text_operations": removed_text_operations,
                "vector_text_blocks": len(report),
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pipeline", type=Path, default=DEFAULT_PIPELINE)
    args = parser.parse_args()
    rebuild(
        args.source.resolve(),
        args.manifest.resolve(),
        args.output.resolve(),
        args.pipeline.resolve(),
    )


if __name__ == "__main__":
    main()
