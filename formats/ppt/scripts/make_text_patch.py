#!/usr/bin/env python3
"""Create a tightly bounded, lossless background patch for an image label."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_box(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(part.strip()) for part in value.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("box must be x,y,w,h")
    x, y, width, height = parts
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("box values must be non-negative with positive size")
    return parts


def parse_rgb(value: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        raise argparse.ArgumentTypeError("RGB must contain six hexadecimal digits")
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("RGB must contain six hexadecimal digits") from exc


def make_patch(
    source_path: Path,
    output_path: Path,
    box: tuple[int, int, int, int],
    mode: str,
    fill_rgb: tuple[int, int, int] | None = None,
    supplied_patch: Path | None = None,
    verified_solid: bool = False,
) -> None:
    with Image.open(source_path) as source:
        x, y, width, height = box
        if x + width > source.width or y + height > source.height:
            raise ValueError("box exceeds source image bounds")

    if mode == "solid":
        if not verified_solid:
            raise ValueError("solid mode requires explicit verified_solid evidence")
        if fill_rgb is None:
            raise ValueError("solid mode requires fill_rgb")
        patch = Image.new("RGB", (width, height), fill_rgb)
    elif mode == "supplied":
        if supplied_patch is None:
            raise ValueError("supplied mode requires supplied_patch")
        with Image.open(supplied_patch) as candidate:
            if candidate.size != (width, height):
                raise ValueError("supplied patch dimensions must equal the declared source region")
            patch = candidate.convert("RGBA").copy()
    else:
        raise ValueError(f"unsupported mode: {mode}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    patch.save(output_path, format="PNG", optimize=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--box", type=parse_box, required=True, help="x,y,w,h in source pixels")
    parser.add_argument("--mode", choices=("solid", "supplied"), required=True)
    parser.add_argument("--fill-rgb", type=parse_rgb)
    parser.add_argument("--supplied-patch", type=Path)
    parser.add_argument("--verified-solid", action="store_true")
    args = parser.parse_args()
    make_patch(
        args.source,
        args.output,
        args.box,
        args.mode,
        args.fill_rgb,
        args.supplied_patch,
        args.verified_solid,
    )


if __name__ == "__main__":
    main()
