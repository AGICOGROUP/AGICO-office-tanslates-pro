from __future__ import annotations

from typing import Iterable


class LayoutAdjustmentError(ValueError):
    pass


def _box(value: object, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise LayoutAdjustmentError(f"{label} must contain four coordinates")
    x0, y0, x1, y1 = (float(item) for item in value)
    if x1 <= x0 or y1 <= y0:
        raise LayoutAdjustmentError(f"{label} has invalid bounds")
    return x0, y0, x1, y1


def _contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _overlaps(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return min(first[2], second[2]) > max(first[0], second[0]) and min(first[3], second[3]) > max(first[1], second[1])


def validate_layout_adjustment(
    item: dict,
    page_width: float,
    page_height: float,
    protected_boxes: Iterable[list[float]],
) -> dict:
    if item.get("trigger") != "text_does_not_fit" or item.get("fit_failure") is not True:
        raise LayoutAdjustmentError("image adjustment requires a recorded text fit failure")
    original = _box(item.get("original_box"), "original_box")
    target = _box(item.get("target_box"), "target_box")
    if "source_box" in item and _box(item["source_box"], "source_box") != original:
        raise LayoutAdjustmentError("source_box must equal original_box")
    if not _contains((0.0, 0.0, float(page_width), float(page_height)), target):
        raise LayoutAdjustmentError("target_box escapes the page")
    original_ratio = (original[2] - original[0]) / (original[3] - original[1])
    target_ratio = (target[2] - target[0]) / (target[3] - target[1])
    if abs(original_ratio - target_ratio) / original_ratio > 0.005:
        raise LayoutAdjustmentError("image aspect ratio must remain unchanged")
    geometric_scale = (target[2] - target[0]) / (original[2] - original[0])
    if geometric_scale > 1.0001 or abs(float(item.get("scale", geometric_scale)) - geometric_scale) > 0.005:
        raise LayoutAdjustmentError("image may only shift or shrink uniformly")
    approved = [_box(region, "approved_background_region") for region in item.get("approved_background_regions", [])]
    if not any(_contains(region, original) for region in approved):
        raise LayoutAdjustmentError("vacated image area is not an approved background region")
    for protected in protected_boxes:
        protected_box = _box(protected, "protected_box")
        if _overlaps(original, protected_box):
            raise LayoutAdjustmentError("original image contains protected content")
        if _overlaps(target, protected_box):
            raise LayoutAdjustmentError("target image overlaps protected content")
    return {"original_box": list(original), "target_box": list(target), "scale": geometric_scale}
