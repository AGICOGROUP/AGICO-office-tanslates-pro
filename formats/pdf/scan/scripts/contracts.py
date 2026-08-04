from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from reportlab.pdfbase.pdfmetrics import stringWidth

from layout_adjustments import LayoutAdjustmentError, validate_layout_adjustment


class ManifestError(ValueError):
    pass


class TextOverflowError(ValueError):
    pass


@dataclass(frozen=True)
class FitResult:
    lines: tuple[str, ...]
    font_size: float
    leading: float


def _normalized_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _validate_rgb(value: object, label: str) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise ManifestError(f"{label} must be a three-value RGB list")
    if any(not isinstance(channel, (int, float)) or channel < 0 or channel > 1 for channel in value):
        raise ManifestError(f"{label} RGB channels must be between 0 and 1")


def _validate_rich_lines(block: dict, page: dict) -> None:
    block_id = block.get("id", "<unknown>")
    rich_lines = block.get("rich_lines")
    if rich_lines is None:
        return
    if block.get("action") != "replace":
        raise ManifestError(f"block {block_id} rich_lines require action 'replace'")
    if not isinstance(rich_lines, list) or not rich_lines:
        raise ManifestError(f"block {block_id} rich_lines must contain at least one line")
    translated_text: list[str] = []
    for line_index, line in enumerate(rich_lines, start=1):
        if not isinstance(line, list) or not line:
            raise ManifestError(f"block {block_id} rich line {line_index} must contain runs")
        for run_index, run in enumerate(line, start=1):
            if not isinstance(run, dict):
                raise ManifestError(f"block {block_id} rich run {line_index}.{run_index} must be an object")
            run_type = run.get("type")
            if run_type == "text":
                text = run.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ManifestError(f"block {block_id} text run {line_index}.{run_index} is blank")
                translated_text.append(text)
                if "color" in run:
                    _validate_rgb(run["color"], f"block {block_id} text run {line_index}.{run_index} color")
                if "bold" in run and not isinstance(run["bold"], bool):
                    raise ManifestError(f"block {block_id} text run {line_index}.{run_index} bold must be boolean")
            elif run_type == "source_crop":
                source_box = run.get("source_box")
                if not isinstance(source_box, list) or len(source_box) != 4:
                    raise ManifestError(f"block {block_id} source crop {line_index}.{run_index} must have a four-value source_box")
                if any(not isinstance(value, (int, float)) for value in source_box):
                    raise ManifestError(f"block {block_id} source crop {line_index}.{run_index} source_box must be numeric")
                x0, y0, x1, y1 = source_box
                if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                    raise ManifestError(f"block {block_id} source crop {line_index}.{run_index} has invalid bounds")
                if x1 > page["pixel_width"] or y1 > page["pixel_height"]:
                    raise ManifestError(f"block {block_id} source crop {line_index}.{run_index} exceeds the source page")
                if not str(run.get("alt", "")).strip():
                    raise ManifestError(f"block {block_id} source crop {line_index}.{run_index} requires non-empty alt text")
            else:
                raise ManifestError(f"block {block_id} rich run {line_index}.{run_index} has invalid type {run_type!r}")
    if _normalized_text("".join(translated_text)) != _normalized_text(str(block.get("translation", ""))):
        raise ManifestError(f"block {block_id} rich text runs do not match translation")


def validate_manifest(manifest: dict) -> dict:
    source_lines = manifest.get("source_lines", [])
    blocks = manifest.get("blocks", [])
    source_ids = [line.get("id") for line in source_lines]
    if not source_ids or any(not line_id for line_id in source_ids):
        raise ManifestError("source_lines must contain stable non-empty IDs")
    if len(source_ids) != len(set(source_ids)):
        raise ManifestError("duplicate source line IDs in source_lines")

    page_index = {page.get("source_page"): page for page in manifest.get("pages", [])}
    for page_number, page in page_index.items():
        block_boxes = [
            block["box"]
            for block in blocks
            if block.get("page") == page_number
            and isinstance(block.get("box"), list)
            and len(block["box"]) == 4
        ]
        for adjustment in page.get("layout_adjustments", []):
            try:
                validate_layout_adjustment(
                    adjustment,
                    float(page["pixel_width"]),
                    float(page["pixel_height"]),
                    [*page.get("protected_boxes", []), *block_boxes],
                )
            except LayoutAdjustmentError as exc:
                raise ManifestError(
                    f"page {page_number} invalid layout adjustment: {exc}"
                ) from exc
    assignments: list[str] = []
    translated_count = 0
    preserve_count = 0
    for block in blocks:
        block_id = block.get("id", "<unknown>")
        required = ("page", "source_line_ids", "source", "translation", "role", "box", "status", "action")
        missing = [name for name in required if name not in block]
        if missing:
            raise ManifestError(f"block {block_id} missing fields: {missing}")
        if block["status"] not in {"translated", "preserve_confirm", "bilingual_complete"}:
            raise ManifestError(f"block {block_id} has invalid status {block['status']!r}")
        if not str(block["source"]).strip():
            raise ManifestError(f"block {block_id} has blank source")
        if block["status"] == "translated" and not str(block["translation"]).strip():
            raise ManifestError(f"block {block_id} has blank translation")
        if len(block["box"]) != 4:
            raise ManifestError(f"block {block_id} must have a four-value box")
        if block["action"] not in {"replace", "preserve"}:
            raise ManifestError(f"block {block_id} has invalid action {block['action']!r}")
        if block["action"] == "replace" and len(block.get("clean_box", [])) != 4:
            raise ManifestError(f"block {block_id} must have a four-value clean_box")
        if block["status"] == "translated" and block["action"] != "replace":
            raise ManifestError(f"translated block {block_id} must use action 'replace'")
        if block["status"] == "preserve_confirm" and block["action"] != "preserve":
            raise ManifestError(
                f"block {block_id} preserve_confirm must use action 'preserve'"
            )
        if block["status"] == "bilingual_complete":
            if block["action"] != "preserve":
                raise ManifestError(
                    f"block {block_id} bilingual_complete must use action 'preserve'"
                )
            evidence = block.get("bilingual_evidence") or {}
            clear_count = int(evidence.get("clear_source_label_count", -1))
            matched_count = int(evidence.get("matched_bilingual_pair_count", -1))
            unmatched_count = int(evidence.get("unmatched_source_label_count", -1))
            source_hash = str(evidence.get("source_region_sha256", ""))
            if (
                clear_count <= 0
                or matched_count != clear_count
                or unmatched_count != 0
                or len(source_hash) != 64
                or any(character not in "0123456789abcdefABCDEF" for character in source_hash)
            ):
                raise ManifestError(
                    f"block {block_id} has incomplete bilingual coverage"
                )
        page = page_index.get(block["page"])
        if page is None:
            raise ManifestError(f"block {block_id} references unknown page {block['page']}")
        _validate_rich_lines(block, page)
        assignments.extend(block["source_line_ids"])
        translated_count += block["status"] == "translated"
        preserve_count += block["status"] == "preserve_confirm"

    counts = Counter(assignments)
    duplicate = sorted(line_id for line_id, count in counts.items() if count > 1)
    unassigned = sorted(set(source_ids) - set(assignments))
    unknown = sorted(set(assignments) - set(source_ids))
    failures = []
    if duplicate:
        failures.append(f"duplicate assignments: {duplicate}")
    if unassigned:
        failures.append(f"unassigned source lines: {unassigned}")
    if unknown:
        failures.append(f"unknown source lines: {unknown}")
    if failures:
        raise ManifestError("; ".join(failures))

    return {
        "source_line_count": len(source_ids),
        "assigned_line_count": len(assignments),
        "translated_block_count": translated_count,
        "preserve_confirm_count": preserve_count,
    }


def _wrap_paragraph(text: str, font_name: str, font_size: float, width: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    if stringWidth(current, font_name, font_size) > width:
        raise TextOverflowError(f"unbreakable token exceeds width: {current!r}")
    for word in words[1:]:
        if stringWidth(word, font_name, font_size) > width:
            raise TextOverflowError(f"unbreakable token exceeds width: {word!r}")
        candidate = f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_text(
    text: str,
    font_name: str,
    max_size: float,
    min_size: float,
    width: float,
    height: float,
    leading_ratio: float = 1.2,
) -> FitResult:
    if min_size <= 0 or max_size < min_size or width <= 0 or height <= 0:
        raise ValueError("invalid fitting dimensions or font sizes")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise TextOverflowError("cannot fit blank text")

    steps = int(round((max_size - min_size) / 0.25))
    sizes = [round(max_size - index * 0.25, 2) for index in range(steps + 1)]
    if not sizes or sizes[-1] != min_size:
        sizes.append(min_size)

    last_error: Exception | None = None
    for font_size in sizes:
        lines: list[str] = []
        try:
            for paragraph in normalized.split("\n"):
                lines.extend(_wrap_paragraph(paragraph, font_name, font_size, width))
        except TextOverflowError as exc:
            last_error = exc
            continue
        leading = font_size * leading_ratio
        if len(lines) * leading <= height + 1e-6:
            return FitResult(tuple(lines), font_size, leading)

    reason = f": {last_error}" if last_error else ""
    raise TextOverflowError(
        f"complete text does not fit at minimum {min_size} pt in {width} x {height} pt{reason}"
    )
