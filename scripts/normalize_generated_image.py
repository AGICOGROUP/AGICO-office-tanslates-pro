"""Pad a GPT-edited image to an exact source aspect ratio without cropping or downsampling."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image


def normalize(source_width: int, source_height: int, generated: Path, output: Path) -> tuple[int, int]:
    if source_width < 1 or source_height < 1:
        raise ValueError("source dimensions must be positive")
    with Image.open(generated) as image:
        image.load()
        width, height = image.size
        scale = max(1, math.ceil(width / source_width), math.ceil(height / source_height))
        target = (source_width * scale, source_height * scale)
        background = image.getpixel((0, 0))
        mode = image.mode
        canvas = Image.new(mode, target, background)
        canvas.paste(image, ((target[0] - width) // 2, (target[1] - height) // 2))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output)
    verify(source_width, source_height, output)
    return target


def verify(source_width: int, source_height: int, candidate: Path) -> tuple[int, int]:
    with Image.open(candidate) as image:
        width, height = image.size
    if width < source_width or height < source_height:
        raise ValueError("generated image dimensions must not be smaller than the source")
    if width * source_height != height * source_width:
        raise ValueError("generated image must preserve the exact source aspect ratio")
    return width, height


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('generated', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-width', type=int, required=True)
    parser.add_argument('--source-height', type=int, required=True)
    args = parser.parse_args()
    print(normalize(args.source_width, args.source_height, args.generated, args.output))


if __name__ == '__main__':
    main()
