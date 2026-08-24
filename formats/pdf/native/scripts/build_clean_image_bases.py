import argparse
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def dilate(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant")
        expanded = np.zeros_like(result)
        for dy in range(3):
            for dx in range(3):
                expanded |= padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
        result = expanded
    return result


def boundary_connected(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    connected = np.zeros_like(mask)
    pending: deque[tuple[int, int]] = deque()
    for x in range(width):
        pending.extend(((0, x), (height - 1, x)))
    for y in range(1, height - 1):
        pending.extend(((y, 0), (y, width - 1)))
    while pending:
        y, x = pending.popleft()
        if connected[y, x] or not mask[y, x]:
            continue
        connected[y, x] = True
        for ny in range(max(0, y - 1), min(height, y + 2)):
            for nx in range(max(0, x - 1), min(width, x + 2)):
                if not connected[ny, nx] and mask[ny, nx]:
                    pending.append((ny, nx))
    return connected


def horizontal_runs(mask: np.ndarray, minimum_length: int) -> np.ndarray:
    protected = np.zeros_like(mask)
    for y, row in enumerate(mask):
        start = None
        for x, value in enumerate(np.append(row, False)):
            if value and start is None:
                start = x
            elif not value and start is not None:
                if x - start >= minimum_length:
                    protected[y, start:x] = True
                start = None
    return protected


def vertical_runs(mask: np.ndarray, minimum_length: int) -> np.ndarray:
    return horizontal_runs(mask.T, minimum_length).T


def neutral_mask(crop: np.ndarray, protection: str) -> np.ndarray:
    values = crop.astype(np.int16)
    maximum = values.max(axis=2)
    minimum = values.min(axis=2)
    saturation = maximum - minimum
    candidate = (saturation <= 72) & (maximum < 254)
    line_core = (saturation <= 82) & (maximum < 185)
    if protection == "none":
        return candidate
    if protection == "lines":
        structural = horizontal_runs(line_core, 12) | vertical_runs(line_core, 12)
    elif protection == "boundary":
        structural = boundary_connected(line_core)
    else:
        raise ValueError(f"Unsupported neutral protection: {protection}")
    return candidate & ~dilate(structural, 1)


def colored_mask(crop: np.ndarray, color: str, protect_lines: bool) -> np.ndarray:
    values = crop.astype(np.int16)
    red, green, blue = (values[:, :, index] for index in range(3))
    if color == "red":
        seed = (
            (red - green > 28)
            & (red - blue > 28)
            & (green < 235)
            & (blue < 235)
        )
        relaxed = (
            (red - green > 8)
            & (red - blue > 8)
            & (green < 252)
            & (blue < 252)
        )
    elif color == "cyan":
        seed = (
            (green - red > 22)
            & (blue - red > 22)
            & (green > 105)
            & (blue > 105)
            & (red < 225)
        )
        relaxed = (
            (green - red > 6)
            & (blue - red > 6)
            & (green > 90)
            & (blue > 90)
            & (red < 250)
        )
    else:
        raise ValueError(f"Unsupported text color: {color}")
    candidate = seed | (dilate(seed, 2) & relaxed)
    if protect_lines:
        candidate &= ~dilate(horizontal_runs(relaxed, 18), 1)
    return candidate


def background_color(crop: np.ndarray) -> np.ndarray:
    values = crop.astype(np.int16)
    maximum = values.max(axis=2)
    minimum = values.min(axis=2)
    background = crop[(minimum > 238) & ((maximum - minimum) < 18)]
    if len(background) == 0:
        return np.array([255, 255, 255], dtype=np.uint8)
    return np.median(background, axis=0).astype(np.uint8)


def adaptive_background_color(crop: np.ndarray) -> np.ndarray:
    """Estimate the local UI fill without assuming that it is white."""
    if crop.shape[0] >= 3 and crop.shape[1] >= 3:
        flat = np.concatenate(
            (
                crop[0, :, :],
                crop[-1, :, :],
                crop[1:-1, 0, :],
                crop[1:-1, -1, :],
            ),
            axis=0,
        )
    else:
        flat = crop.reshape(-1, 3)
    quantized = (flat // 16).astype(np.int16)
    keys, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = keys[int(np.argmax(counts))]
    members = flat[np.all(quantized == dominant, axis=1)]
    return np.median(members, axis=0).astype(np.uint8)


def ui_glyph_mask(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Select contrasting glyph pixels while protecting long UI dividers."""
    fill = adaptive_background_color(crop)
    distance = np.max(
        np.abs(crop.astype(np.int16) - fill.astype(np.int16)), axis=2
    )
    seed = distance >= 24
    relaxed = distance >= 8
    candidate = seed | (dilate(seed, 1) & relaxed)
    height, width = candidate.shape
    horizontal_min = max(12, int(width * 0.86))
    vertical_min = max(12, int(height * 0.86))
    structural = (
        horizontal_runs(relaxed, horizontal_min)
        | vertical_runs(relaxed, vertical_min)
    )
    return candidate & ~dilate(structural, 1), fill


def reconstruct_ui_rows(
    image: np.ndarray, x0: int, y0: int, x1: int, y1: int
) -> np.ndarray:
    """Rebuild a tight text patch from its immediate left/right row pixels."""
    height, image_width = image.shape[:2]
    target_width = x1 - x0
    rebuilt = np.empty((y1 - y0, target_width, 3), dtype=np.uint8)
    for row_index, y in enumerate(range(y0, y1)):
        left = image[y, x0 - 1].astype(np.float32) if x0 > 0 else None
        right = image[y, x1].astype(np.float32) if x1 < image_width else None
        if left is not None and right is not None:
            for column in range(target_width):
                ratio = (column + 1) / (target_width + 1)
                rebuilt[row_index, column] = np.rint(
                    left * (1.0 - ratio) + right * ratio
                ).astype(np.uint8)
        elif left is not None:
            rebuilt[row_index, :] = left.astype(np.uint8)
        elif right is not None:
            rebuilt[row_index, :] = right.astype(np.uint8)
        else:
            rebuilt[row_index, :] = image[
                min(max(y, 0), height - 1), x0:x1
            ]
    return rebuilt


def _touches_opposite_edges(
    start: tuple[int, int], end: tuple[int, int], box: tuple[int, int, int, int]
) -> bool:
    x0, y0, x1, y1 = box
    sx, sy = start
    ex, ey = end
    horizontal = (sx == x0 and ex == x1 - 1) or (ex == x0 and sx == x1 - 1)
    vertical = (sy == y0 and ey == y1 - 1) or (ey == y0 and sy == y1 - 1)
    return horizontal or vertical


def restore_anchored_lines(
    image: np.ndarray,
    region: dict,
    box: tuple[int, int, int, int],
    source_image: np.ndarray,
) -> int:
    """Restore only explicit segments supported by opposite-edge anchors."""
    height, width = image.shape[:2]
    restored = 0
    anchors = region.get("line_anchors", [])
    if not anchors:
        raise ValueError("anchored_line_restore requires line_anchors")
    for anchor in anchors:
        try:
            start = tuple(int(value) for value in anchor["start"])
            end = tuple(int(value) for value in anchor["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid anchored line coordinates") from exc
        if len(start) != 2 or len(end) != 2:
            raise ValueError("invalid anchored line coordinates")
        if not _touches_opposite_edges(start, end, box):
            raise ValueError("line anchors must touch opposite cleanup-box edges")
        if not all(
            0 <= x < width and 0 <= y < height for x, y in (start, end)
        ):
            raise ValueError("line anchor lies outside image")
        start_color = source_image[start[1], start[0]].astype(np.int16)
        end_color = source_image[end[1], end[0]].astype(np.int16)
        tolerance = int(anchor.get("color_tolerance", 40))
        if int(np.max(np.abs(start_color - end_color))) > tolerance:
            raise ValueError("line anchor colors are incompatible")
        steps = max(abs(end[0] - start[0]), abs(end[1] - start[1])) + 1
        xs = np.rint(np.linspace(start[0], end[0], steps)).astype(int)
        ys = np.rint(np.linspace(start[1], end[1], steps)).astype(int)
        line_width = max(1, int(anchor.get("width", 1)))
        radius = (line_width - 1) // 2
        for index, (x, y) in enumerate(zip(xs, ys)):
            ratio = index / max(steps - 1, 1)
            color = np.rint(
                start_color * (1.0 - ratio) + end_color * ratio
            ).astype(np.uint8)
            xa, xb = max(box[0], x - radius), min(box[2], x + radius + 1)
            ya, yb = max(box[1], y - radius), min(box[3], y + radius + 1)
            image[ya:yb, xa:xb] = color
        restored += 1
    return restored


def clean_region(image: np.ndarray, region: dict) -> int:
    x0, y0, x1, y1 = region.get("clean_box", region["box"])
    source_crop = image[y0:y1, x0:x1].copy()
    mode = region["mode"]
    source_for_restore = image.copy() if mode == "anchored_line_restore" else None
    if mode == "neutral_plain":
        mask = neutral_mask(source_crop, "none")
    elif mode == "neutral_lines":
        mask = neutral_mask(source_crop, "lines")
    elif mode in {"neutral", "neutral_boundary"}:
        mask = neutral_mask(source_crop, "boundary")
    elif mode == "red":
        mask = colored_mask(source_crop, "red", False)
    elif mode == "cyan":
        mask = colored_mask(source_crop, "cyan", True)
    elif mode in {"text_only_area", "cyan_glyph", "white_text_area"}:
        mask = np.ones(source_crop.shape[:2], dtype=bool)
    elif mode == "ui_glyph":
        mask, fill = ui_glyph_mask(source_crop)
    elif mode == "ui_text_patch":
        target = image[y0:y1, x0:x1]
        before = target.copy()
        target[:] = reconstruct_ui_rows(image, x0, y0, x1, y1)
        return int(np.any(before != target, axis=2).sum())
    elif mode == "solid_fill":
        fill_rgb = np.asarray(region.get("fill_rgb", []), dtype=np.uint8)
        if fill_rgb.shape != (3,):
            raise ValueError("solid_fill requires fill_rgb with three channels")
        target = image[y0:y1, x0:x1]
        before = target.copy()
        target[:] = fill_rgb
        return int(np.any(before != target, axis=2).sum())
    elif mode == "anchored_line_restore":
        mask = neutral_mask(source_crop, "none")
    else:
        raise ValueError(f"Unsupported cleanup mode: {mode}")
    target = image[y0:y1, x0:x1]
    before = target.copy()
    target[mask] = fill if mode == "ui_glyph" else background_color(source_crop)
    if mode == "anchored_line_restore":
        region["_restored_segments"] = restore_anchored_lines(
            image, region, (x0, y0, x1, y1), source_for_restore
        )
    return int(np.any(before != target, axis=2).sum())


def build(metadata_path: Path) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    base = metadata_path.parent
    report = {"images": []}
    for item in metadata["images"]:
        source_path = resolve(base, item["source"])
        output_path = resolve(base, item["output"])
        source = np.array(Image.open(source_path).convert("RGB"))
        cleaned = source.copy()
        changed_by_region = [clean_region(cleaned, region) for region in item["regions"]]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(cleaned, "RGB").save(output_path, format="PNG")
        report["images"].append(
            {
                "id": item["id"],
                "source": str(source_path),
                "output": str(output_path),
                "size": [source.shape[1], source.shape[0]],
                "changed_pixels": int(np.any(source != cleaned, axis=2).sum()),
                "changed_by_region": changed_by_region,
                "restored_line_segments": sum(
                    int(region.get("_restored_segments", 0))
                    for region in item["regions"]
                ),
            }
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = build(args.metadata)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
