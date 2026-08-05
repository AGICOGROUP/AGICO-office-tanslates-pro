from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from contracts import TextOverflowError, fit_text, validate_manifest


REGULAR_FONT_PATHS = [Path(r"C:\Windows\Fonts\arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
BOLD_FONT_PATHS = [Path(r"C:\Windows\Fonts\arialbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
REGULAR_FONT = "ScanTranslation-Regular"
BOLD_FONT = "ScanTranslation-Bold"
ROLE_DEFAULTS = {
    "title": (18, 11), "subtitle": (15, 10), "heading": (16, 10),
    "subheading": (14, 9), "body": (10, 6), "list_item": (10, 6),
    "table_header": (9, 6), "table_cell": (9, 6), "warning_title": (12, 8),
    "warning_body": (9, 6), "caption": (9, 6), "header": (9, 6), "footer": (8, 5.5),
}


def typography_group(role: str) -> str:
    value = str(role or "").lower()
    if value in {"title", "cover_title", "heading_1"}:
        return "major_title"
    if value in {"subtitle", "heading", "subheading", "heading_2", "heading_3", "warning_title"}:
        return "minor_title"
    if value in {"body", "list_item", "warning_body", "caption"}:
        return "body"
    return "special"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def apply_page_typography_policy(blocks: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for block in blocks:
        if block.get("action") not in {None, "replace"}:
            continue
        group = typography_group(block.get("role", ""))
        if group != "special":
            grouped.setdefault(group, []).append(block)
    evidence: dict[str, dict] = {}
    for group, members in grouped.items():
        sizes = [float(member.get("max_font", ROLE_DEFAULTS.get(member.get("role", ""), (9, 6))[0])) for member in members]
        target_size = _median(sizes)
        bold_votes = sum(bool(member.get("bold", False)) for member in members)
        target_bold = bold_votes >= len(members) / 2 if group != "body" else bold_votes > len(members) / 2
        for member in members:
            member["max_font"] = target_size
            member["bold"] = target_bold
        evidence[group] = {"font_name": BOLD_FONT if target_bold else REGULAR_FONT, "font_size": target_size, "bold": target_bold, "block_ids": [member.get("id", "") for member in members]}
    return evidence


def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise RuntimeError(f"No embeddable TrueType font found in: {paths}")


def register_fonts() -> None:
    if REGULAR_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(REGULAR_FONT, str(_first_existing(REGULAR_FONT_PATHS))))
        pdfmetrics.registerFont(TTFont(BOLD_FONT, str(_first_existing(BOLD_FONT_PATHS))))


def _clamp_box(box: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(width, math.floor(box[0])))
    y0 = max(0, min(height, math.floor(box[1])))
    x1 = max(x0 + 1, min(width, math.ceil(box[2])))
    y1 = max(y0 + 1, min(height, math.ceil(box[3])))
    return x0, y0, x1, y1


def _sample_background(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    array = np.asarray(image.convert("RGB"))
    height, width, _ = array.shape
    x0, y0, x1, y1 = box
    outer = (max(0, x0 - 6), max(0, y0 - 6), min(width, x1 + 6), min(height, y1 + 6))
    ox0, oy0, ox1, oy1 = outer
    samples = []
    if oy0 < y0: samples.append(array[oy0:y0, ox0:ox1].reshape(-1, 3))
    if y1 < oy1: samples.append(array[y1:oy1, ox0:ox1].reshape(-1, 3))
    if ox0 < x0: samples.append(array[y0:y1, ox0:x0].reshape(-1, 3))
    if x1 < ox1: samples.append(array[y0:y1, x1:ox1].reshape(-1, 3))
    if not samples:
        return 255, 255, 255
    return tuple(int(value) for value in np.median(np.concatenate(samples), axis=0))


def clean_background(original: Image.Image, blocks: list[dict]) -> tuple[Image.Image, dict]:
    source = original.convert("RGB")
    cleaned = source.copy()
    approved = Image.new("1", cleaned.size, 0)
    approved_draw = ImageDraw.Draw(approved)
    draw = ImageDraw.Draw(cleaned)
    for block in blocks:
        if block.get("action") != "replace":
            continue
        box = _clamp_box(block["clean_box"], cleaned.width, cleaned.height)
        approved_draw.rectangle(box, fill=1)
        background = block.get("background", "sample")
        color = _sample_background(source, box) if background == "sample" else tuple(background)
        draw.rectangle(box, fill=color)
    changed = np.any(np.asarray(ImageChops.difference(source, cleaned).convert("RGB")) != 0, axis=2)
    outside = changed & ~np.asarray(approved, dtype=bool)
    return cleaned, {
        "changed_pixel_count": int(np.count_nonzero(changed)),
        "outside_approved_pixel_changes": int(np.count_nonzero(outside)),
    }


def apply_raster_layout_adjustments(original: Image.Image, page: dict) -> tuple[Image.Image, dict]:
    source = original.convert("RGB")
    adjusted = source.copy()
    approved = Image.new("1", adjusted.size, 0)
    approved_draw = ImageDraw.Draw(approved)
    for item in page.get("layout_adjustments", []):
        source_box = _clamp_box(item.get("source_box", item["original_box"]), source.width, source.height)
        original_box = _clamp_box(item["original_box"], source.width, source.height)
        target_box = _clamp_box(item["target_box"], source.width, source.height)
        crop = source.crop(source_box)
        background = item.get("background", "sample")
        color = _sample_background(source, original_box) if background == "sample" else tuple(background)
        ImageDraw.Draw(adjusted).rectangle(original_box, fill=color)
        resized = crop.resize((target_box[2] - target_box[0], target_box[3] - target_box[1]), Image.Resampling.LANCZOS)
        adjusted.paste(resized, (target_box[0], target_box[1]))
        approved_draw.rectangle(original_box, fill=1)
        approved_draw.rectangle(target_box, fill=1)
    changed = np.any(np.asarray(ImageChops.difference(source, adjusted).convert("RGB")) != 0, axis=2)
    outside = changed & ~np.asarray(approved, dtype=bool)
    return adjusted, {
        "layout_adjustment_count": len(page.get("layout_adjustments", [])),
        "layout_changed_pixel_count": int(np.count_nonzero(changed)),
        "layout_outside_approved_pixel_changes": int(np.count_nonzero(outside)),
    }


def _page_box(block: dict, page: dict) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = block["box"]
    sx = page["width_pt"] / page["pixel_width"]
    sy = page["height_pt"] / page["pixel_height"]
    return x0 * sx, page["height_pt"] - y1 * sy, x1 * sx, page["height_pt"] - y0 * sy


def _draw_block(pdf: canvas.Canvas, block: dict, page: dict) -> dict:
    left, bottom, right, top = _page_box(block, page)
    angle = float(block.get("rotation", 0)) % 360
    if angle not in {0, 90, 180, 270}:
        raise ValueError(f"block {block['id']} rotation must be 0, 90, 180, or 270")
    box_width, box_height = max(0.1, right - left - 2), max(0.1, top - bottom - 2)
    width, height = (box_height, box_width) if angle in {90, 270} else (box_width, box_height)
    default_max, default_min = ROLE_DEFAULTS.get(block["role"], (9, 6))
    font_name = BOLD_FONT if block.get("bold") else REGULAR_FONT
    try:
        fitted = fit_text(
            block["translation"], font_name,
            float(block.get("max_font", default_max)), float(block.get("min_font", default_min)),
            width, height, float(block.get("leading_ratio", 1.16)),
        )
    except TextOverflowError as exc:
        raise TextOverflowError(f"block {block['id']} complete text does not fit: {exc}") from exc
    pdf.saveState()
    center_x, center_y = (left + right) / 2, (bottom + top) / 2
    pdf.translate(center_x, center_y)
    pdf.rotate(angle)
    local_left, local_bottom = -width / 2, -height / 2
    local_right, local_top = width / 2, height / 2
    pdf.setFillColorRGB(*block.get("color", [0, 0, 0]))
    pdf.setFont(font_name, fitted.font_size)
    text_height = len(fitted.lines) * fitted.leading
    if block.get("valign") == "center":
        first_baseline = local_top - max(0, (height - text_height) / 2) - fitted.font_size
    else:
        first_baseline = local_top - 1 - fitted.font_size
    for index, line in enumerate(fitted.lines):
        line_width = pdfmetrics.stringWidth(line, font_name, fitted.font_size)
        if block.get("align") == "right": x = local_right - 1 - line_width
        elif block.get("align") == "center": x = (local_left + local_right - line_width) / 2
        else: x = local_left + 1
        pdf.drawString(x, first_baseline - index * fitted.leading, line)
    pdf.restoreState()
    return {"id": block["id"], "font_size": fitted.font_size, "line_count": len(fitted.lines), "complete": True, "box_pt": [left, bottom, right, top]}


def _fit_rich_lines(block: dict, page: dict, width: float, height: float) -> tuple[float, float, list[dict]]:
    default_max, default_min = ROLE_DEFAULTS.get(block["role"], (9, 6))
    max_size = float(block.get("max_font", default_max))
    min_size = float(block.get("min_font", default_min))
    leading_ratio = float(block.get("leading_ratio", 1.16))
    sx = page["width_pt"] / page["pixel_width"]
    sy = page["height_pt"] / page["pixel_height"]
    steps = int(round((max_size - min_size) / 0.25))
    sizes = [round(max_size - index * 0.25, 2) for index in range(steps + 1)]
    if not sizes or sizes[-1] != min_size:
        sizes.append(min_size)
    for font_size in sizes:
        lines: list[dict] = []
        total_height = 0.0
        fits = True
        for runs in block["rich_lines"]:
            measured_runs = []
            line_width = 0.0
            line_height = font_size * leading_ratio
            for run in runs:
                if run["type"] == "text":
                    font_name = BOLD_FONT if run.get("bold", block.get("bold", False)) else REGULAR_FONT
                    run_width = pdfmetrics.stringWidth(run["text"], font_name, font_size)
                    measured = {**run, "width_pt": run_width, "height_pt": font_size, "font_name": font_name}
                else:
                    x0, y0, x1, y1 = run["source_box"]
                    run_width = (x1 - x0) * sx
                    run_height = (y1 - y0) * sy
                    measured = {**run, "width_pt": run_width, "height_pt": run_height}
                    line_height = max(line_height, run_height)
                line_width += run_width
                measured_runs.append(measured)
            if line_width > width + 1e-6:
                fits = False
                break
            total_height += line_height
            lines.append({"runs": measured_runs, "width_pt": line_width, "height_pt": line_height})
        if fits and total_height <= height + 1e-6:
            return font_size, total_height, lines
    raise TextOverflowError(
        f"block {block['id']} complete rich text does not fit at minimum {min_size} pt in {width} x {height} pt"
    )


def _draw_rich_block(pdf: canvas.Canvas, block: dict, page: dict, source_image: Image.Image) -> dict:
    left, bottom, right, top = _page_box(block, page)
    angle = float(block.get("rotation", 0)) % 360
    if angle not in {0, 90, 180, 270}:
        raise ValueError(f"block {block['id']} rotation must be 0, 90, 180, or 270")
    box_width, box_height = max(0.1, right - left - 2), max(0.1, top - bottom - 2)
    width, height = (box_height, box_width) if angle in {90, 270} else (box_width, box_height)
    font_size, content_height, lines = _fit_rich_lines(block, page, width, height)
    pdf.saveState()
    center_x, center_y = (left + right) / 2, (bottom + top) / 2
    pdf.translate(center_x, center_y)
    pdf.rotate(angle)
    local_left, local_bottom = -width / 2, -height / 2
    local_right, local_top = width / 2, height / 2
    top_cursor = local_top - (max(0, height - content_height) / 2 if block.get("valign") == "center" else 1)
    crop_records: list[dict] = []
    colors: set[tuple[float, float, float]] = set()
    for line in lines:
        if block.get("align") == "right":
            cursor_x = local_right - 1 - line["width_pt"]
        elif block.get("align") == "center":
            cursor_x = (local_left + local_right - line["width_pt"]) / 2
        else:
            cursor_x = local_left + 1
        line_bottom = top_cursor - line["height_pt"]
        for run in line["runs"]:
            run_y = line_bottom + (line["height_pt"] - run["height_pt"]) / 2
            if run["type"] == "text":
                color = tuple(float(value) for value in run.get("color", block.get("color", [0, 0, 0])))
                colors.add(color)
                pdf.setFillColorRGB(*color)
                pdf.setFont(run["font_name"], font_size)
                pdf.drawString(cursor_x, run_y, run["text"])
            else:
                source_box = _clamp_box(run["source_box"], source_image.width, source_image.height)
                crop = source_image.crop(source_box)
                pdf.drawImage(
                    ImageReader(crop), cursor_x, run_y,
                    width=run["width_pt"], height=run["height_pt"], preserveAspectRatio=False, mask="auto",
                )
                crop_records.append(
                    {
                        "block_id": block["id"],
                        "source_page": page["source_page"],
                        "source_box": list(source_box),
                        "output_box_pt": _rotated_output_box(
                            center_x, center_y, angle, cursor_x, run_y,
                            cursor_x + run["width_pt"], run_y + run["height_pt"],
                        ),
                        "pixel_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                        "alt": run["alt"],
                    }
                )
            cursor_x += run["width_pt"]
        top_cursor = line_bottom
    pdf.restoreState()
    return {
        "id": block["id"], "font_size": font_size, "line_count": len(lines), "complete": True,
        "box_pt": [left, bottom, right, top], "rich": True,
        "mixed_color": len(colors) > 1, "source_crop_runs": crop_records,
    }


def _rotated_output_box(
    center_x: float, center_y: float, angle: float,
    x0: float, y0: float, x1: float, y1: float,
) -> list[float]:
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    corners = []
    for local_x, local_y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        corners.append(
            (
                center_x + local_x * cosine - local_y * sine,
                center_y + local_x * sine + local_y * cosine,
            )
        )
    return [
        min(point[0] for point in corners), min(point[1] for point in corners),
        max(point[0] for point in corners), max(point[1] for point in corners),
    ]


def _draw_vector_lines(pdf: canvas.Canvas, page: dict) -> None:
    """Rebuild only rules explicitly approved after a tight text clean-up."""
    sx = page["width_pt"] / page["pixel_width"]
    sy = page["height_pt"] / page["pixel_height"]
    for line in page.get("vector_lines", []):
        x0, y0, x1, y1 = line["points"]
        pdf.setStrokeColorRGB(*line.get("color", [0, 0, 0]))
        pdf.setLineWidth(float(line.get("width", 0.5)))
        pdf.line(x0 * sx, page["height_pt"] - y0 * sy, x1 * sx, page["height_pt"] - y1 * sy)


def resolve_page_typography(blocks: list[dict], page: dict) -> dict[str, dict]:
    evidence = apply_page_typography_policy(blocks)
    grouped: dict[str, list[dict]] = {}
    for block in blocks:
        if block.get("action") != "replace":
            continue
        group = typography_group(block.get("role", ""))
        if group != "special":
            grouped.setdefault(group, []).append(block)
    for group, members in grouped.items():
        fitted_sizes: list[float] = []
        for block in members:
            left, bottom, right, top = _page_box(block, page)
            angle = float(block.get("rotation", 0)) % 360
            box_width, box_height = max(0.1, right - left - 2), max(0.1, top - bottom - 2)
            width, height = (box_height, box_width) if angle in {90, 270} else (box_width, box_height)
            if block.get("rich_lines"):
                fitted_size, _, _ = _fit_rich_lines(block, page, width, height)
            else:
                default_max, default_min = ROLE_DEFAULTS.get(block["role"], (9, 6))
                font_name = BOLD_FONT if block.get("bold") else REGULAR_FONT
                fitted_size = fit_text(
                    block["translation"], font_name,
                    float(block.get("max_font", default_max)),
                    float(block.get("min_font", default_min)),
                    width, height, float(block.get("leading_ratio", 1.16)),
                ).font_size
            fitted_sizes.append(float(fitted_size))
        target_size = min(fitted_sizes)
        for block in members:
            block["max_font"] = target_size
            block["min_font"] = target_size
        evidence[group]["font_size"] = target_size
    return evidence


def build_pdf(manifest: dict, output_path: str | Path) -> dict:
    register_fonts()
    validate_manifest(manifest)
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    clean_dir = output.parent / "clean-bases"
    clean_dir.mkdir(parents=True, exist_ok=True)
    page_index = {page["source_page"]: page for page in manifest["pages"]}
    blocks_by_page = {number: [block for block in manifest["blocks"] if block["page"] == number] for number in manifest["selected_pages"]}
    report = {
        "pages": [], "rendered_blocks": [], "outside_approved_pixel_changes": 0,
        "source_crop_runs": [], "source_crop_run_count": 0, "mixed_color_block_count": 0,
    }
    pdf = canvas.Canvas(str(output), pageCompression=1)
    for page_number in manifest["selected_pages"]:
        page = page_index[page_number]
        render_path = Path(page["render_path"])
        if page.get("render_sha256"):
            digest = hashlib.sha256(render_path.read_bytes()).hexdigest()
            if digest.lower() != str(page["render_sha256"]).lower():
                raise ValueError(f"source render hash mismatch on page {page_number}")
        typography_evidence = resolve_page_typography(blocks_by_page[page_number], page)
        pdf.setPageSize((page["width_pt"], page["height_pt"]))
        with Image.open(page["render_path"]) as loaded:
            source_image = loaded.convert("RGB")
        layout_base, layout_report = apply_raster_layout_adjustments(source_image, page)
        cleaned, clean_report = clean_background(layout_base, blocks_by_page[page_number])
        clean_path = clean_dir / f"page-{page_number:04d}.png"
        cleaned.save(clean_path, optimize=True)
        pdf.drawImage(ImageReader(cleaned), 0, 0, width=page["width_pt"], height=page["height_pt"], preserveAspectRatio=False)
        _draw_vector_lines(pdf, page)
        rendered_ids = []
        for block in blocks_by_page[page_number]:
            if block["action"] == "replace":
                if block.get("rich_lines"):
                    rendered = _draw_rich_block(pdf, block, page, source_image)
                    report["source_crop_runs"].extend(rendered.pop("source_crop_runs"))
                    report["mixed_color_block_count"] += int(rendered.get("mixed_color", False))
                else:
                    rendered = _draw_block(pdf, block, page)
                report["rendered_blocks"].append(rendered)
                rendered_ids.append(block["id"])
        pdf.showPage()
        report["outside_approved_pixel_changes"] += clean_report["outside_approved_pixel_changes"]
        report["outside_approved_pixel_changes"] += layout_report["layout_outside_approved_pixel_changes"]
        report["pages"].append({"source_page": page_number, "clean_path": str(clean_path), "rendered_block_ids": rendered_ids, "typography_evidence": typography_evidence, **layout_report, **clean_report})
    pdf.save()
    report["output"] = str(output)
    report["rendered_block_count"] = len(report["rendered_blocks"])
    report["source_crop_run_count"] = len(report["source_crop_runs"])
    output.with_suffix(".build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a scan-PDF translation from an approved manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_pdf(json.loads(Path(args.manifest).read_text(encoding="utf-8")), args.output)
    print(json.dumps({"output": report["output"], "rendered_block_count": report["rendered_block_count"], "outside_approved_pixel_changes": report["outside_approved_pixel_changes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
