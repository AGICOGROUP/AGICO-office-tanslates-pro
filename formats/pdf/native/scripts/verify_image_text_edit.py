import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def verify_line_anchors(
    source: np.ndarray, rebuilt: np.ndarray, anchors: list[dict]
) -> list[dict]:
    height, width = source.shape[:2]
    results = []
    for anchor in anchors:
        anchor_id = str(anchor.get("id", "unnamed"))
        start = tuple(int(value) for value in anchor["start"])
        end = tuple(int(value) for value in anchor["end"])
        if not all(0 <= x < width and 0 <= y < height for x, y in (start, end)):
            raise AssertionError(f"declared line anchor outside image: {anchor_id}")
        steps = max(abs(end[0] - start[0]), abs(end[1] - start[1])) + 1
        xs = np.rint(np.linspace(start[0], end[0], steps)).astype(int)
        ys = np.rint(np.linspace(start[1], end[1], steps)).astype(int)
        start_color = source[start[1], start[0]].astype(np.float32)
        end_color = source[end[1], end[0]].astype(np.float32)
        tolerance = int(anchor.get("pixel_tolerance", 40))
        failures = 0
        maximum_error = 0
        for index, (x, y) in enumerate(zip(xs, ys)):
            ratio = index / max(steps - 1, 1)
            expected = start_color * (1.0 - ratio) + end_color * ratio
            error = int(
                np.max(np.abs(rebuilt[y, x].astype(np.float32) - expected))
            )
            maximum_error = max(maximum_error, error)
            if error > tolerance:
                failures += 1
        if failures:
            raise AssertionError(f"declared line continuity failed: {anchor_id}")
        results.append(
            {
                "id": anchor_id,
                "sampled_pixels": steps,
                "maximum_error": maximum_error,
                "passed": True,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("rebuilt", type=Path)
    parser.add_argument(
        "--regions-json",
        type=Path,
        required=True,
        help='JSON array of [x0, y0, x1, y1] text regions',
    )
    parser.add_argument("--protect-saturation", type=int, default=80)
    parser.add_argument("--minimum-changed-pixels", type=int, default=1)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--line-anchors-json", type=Path)
    args = parser.parse_args()

    source = np.array(Image.open(args.source).convert("RGB"))
    rebuilt = np.array(Image.open(args.rebuilt).convert("RGB"))
    assert source.shape == rebuilt.shape
    regions = json.loads(args.regions_json.read_text(encoding="utf-8"))
    allowed = np.zeros(source.shape[:2], dtype=bool)
    for x0, y0, x1, y1 in regions:
        allowed[int(y0) : int(y1), int(x0) : int(x1)] = True

    changed = np.any(source != rebuilt, axis=2)
    changed_pixels = int(changed.sum())
    assert changed_pixels >= args.minimum_changed_pixels
    assert not np.any(changed & ~allowed), (
        "Pixels outside approved text regions changed"
    )

    maximum = source.max(axis=2)
    saturation = maximum - source.min(axis=2)
    protected = (saturation > args.protect_saturation) & (maximum < 252)
    assert not np.any(changed & protected & ~allowed), (
        "Protected engineering-color pixels changed outside text regions"
    )
    line_checks = []
    if args.line_anchors_json:
        anchors = json.loads(args.line_anchors_json.read_text(encoding="utf-8"))
        line_checks = verify_line_anchors(source, rebuilt, anchors)
    evidence = {}
    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        difference_path = args.evidence_dir / "difference.png"
        overlay_path = args.evidence_dir / "alpha-overlay.png"
        difference = np.clip(
            np.abs(source.astype(np.int16) - rebuilt.astype(np.int16)) * 4,
            0,
            255,
        ).astype(np.uint8)
        overlay = np.rint(
            source.astype(np.float32) * 0.5 + rebuilt.astype(np.float32) * 0.5
        ).astype(np.uint8)
        Image.fromarray(difference, "RGB").save(difference_path)
        Image.fromarray(overlay, "RGB").save(overlay_path)
        evidence = {
            "difference": str(difference_path.resolve()),
            "alpha_overlay": str(overlay_path.resolve()),
        }
    print(
        json.dumps(
            {
                "shape": list(source.shape),
                "changed_pixels": changed_pixels,
                "approved_region_pixels": int(allowed.sum()),
                "outside_region_changes": int((changed & ~allowed).sum()),
                "line_checks": line_checks,
                "evidence": evidence,
            }
        )
    )


if __name__ == "__main__":
    main()
