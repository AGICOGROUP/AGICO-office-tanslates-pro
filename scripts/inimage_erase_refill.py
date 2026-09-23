# -*- coding: utf-8 -*-
"""Deterministic in-image label localization: erase source glyphs, refill target text.

This is the non-generative alternative to the native ``image_edit`` tool. Only pixels that
belong to a detected label are rewritten; every other pixel is copied from the source
untouched, so linework, arrows, hatching, circles, panel fills and borders stay
pixel-identical. Use it for technical drawings and diagrams. Use ``image_edit`` instead for
photographs, equipment renders and hand-drawn art, where a flat-colour reconstruction of the
background would look wrong.

Commands
--------
ocr      Detect label boxes and write a fill-in label table.
render   Erase the glyphs of every labelled row and typeset the target text in its place.
verify   Measure how much of the graphic survived, split by inside/outside the edited boxes.
zoom     Write an enlarged crop, for transcribing dense annotations before and after.

A label table is JSON::

    {"labels": [{"source": "DISCHARGE", "target": "卸料",
                 "x0": 665.0, "y0": 456.0, "x1": 747.0, "y1": 473.0,
                 "angle": 0.0, "size": null}]}

``target`` empty or null keeps the source text in place, which is the correct answer for a
label that cannot be erased without damaging a graphic crossing its box (see ``angle``).
``size`` caps the glyph size, needed for rotated labels whose axis-aligned box is the
bounding band rather than the text height.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

INK_T = 40          # channel distance from the reconstructed local background
PAD = 2             # grow every label box so anti-aliased edges are covered
RUN_GUARD = 0.92    # contiguous ink fraction that marks a row/column as a real line
COLOUR_CORE = 12    # percentile of the ink mask treated as the stroke body


def default_font() -> Path:
    """A CJK-capable face, resolved from the environment, never a saved user path."""
    windows = Path(os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or "C:\\Windows")
    for candidate in (windows / "Fonts" / "simhei.ttf", windows / "Fonts" / "msyh.ttc"):
        if candidate.is_file():
            return candidate
    for candidate in ("/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
        if Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit("no CJK font found; pass --font <path>")


def box_stroke_kernel(height: int) -> int:
    """Window wide enough to swallow a text stroke of this label height."""
    k = max(5, int(height * 0.5) | 1)
    return min(k, 15)


def _background(sub: np.ndarray) -> np.ndarray:
    """Per-pixel background estimate.

    A maximum filter lifts every pixel to the lightest value in its window, so dark or
    coloured glyph strokes vanish while flat and gradient panel fills stay. A median filter
    cannot do this: a thin stroke still dominates its own window.
    """
    k = box_stroke_kernel(sub.shape[0])
    return np.asarray(
        Image.fromarray(np.ascontiguousarray(sub)).filter(ImageFilter.MaxFilter(k)),
        dtype=np.int16,
    )


def _dilate(mask: np.ndarray, steps: int = 1) -> np.ndarray:
    out = mask.copy()
    for _ in range(steps):
        p = np.zeros_like(out)
        p[1:, :] |= out[:-1, :]
        p[:-1, :] |= out[1:, :]
        p[:, 1:] |= out[:, :-1]
        p[:, :-1] |= out[:, 1:]
        out |= p
    return out


def _longest_run(vec: np.ndarray) -> int:
    best = cur = 0
    for v in vec:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def _drop_straight_lines(ink: np.ndarray) -> np.ndarray:
    """Un-mask rows/columns carrying one near-continuous stroke: a frame line or leader.

    A coverage test is wrong here - bold and monospace text rows also cover most of their
    box - so only a single contiguous run counts. Glyph rows always contain inter-character
    gaps, so their run stays short.
    """
    out = ink.copy()
    h, w = out.shape
    if w > 12:
        for r in range(h):
            if _longest_run(out[r]) >= RUN_GUARD * w:
                out[r, :] = False
    if h > 12:
        for c in range(w):
            if _longest_run(out[:, c]) >= RUN_GUARD * h:
                out[:, c] = False
    return out


def _stroke_colour(sub: np.ndarray, ink: np.ndarray):
    """Colour of the stroke CORE, not the anti-aliased fringe.

    A median over the mask lands on mid-grey because most masked pixels are halo, which is
    what makes the refilled text look like a ghost of the original.
    """
    px = sub[ink].astype(np.int16)
    lum = px.mean(axis=1)
    core = px[lum <= np.percentile(lum, COLOUR_CORE)]
    return tuple(int(v) for v in np.median(core if len(core) else px, axis=0))


def load_table(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["labels"] if isinstance(data, dict) else data


def render(source: Path, table_path: Path, out: Path, font: Path) -> dict:
    labels = [row for row in load_table(table_path) if str(row.get("target") or "").strip()]
    im = Image.open(source).convert("RGB")
    arr = np.asarray(im).copy()
    placed, skipped = [], []

    # Pass 1: erase glyph pixels only, leaving every other pixel of the source.
    for row in labels:
        x0 = max(0, int(float(row["x0"])) - PAD)
        y0 = max(0, int(float(row["y0"])) - PAD)
        x1 = min(im.width, int(float(row["x1"])) + PAD)
        y1 = min(im.height, int(float(row["y1"])) + PAD)
        if x1 - x0 < 4 or y1 - y0 < 4:
            skipped.append((row.get("source"), "degenerate-box"))
            continue
        sub = arr[y0:y1, x0:x1]
        bg = _background(sub)
        ink = np.abs(sub.astype(np.int16) - bg).max(axis=2) > INK_T
        # The straight-line guard must run BEFORE dilation: growing the mask first closes
        # the 1-2 px gaps between bold letters, so a whole text row looks like one
        # continuous stroke, gets skipped, and the source text survives under the new text.
        ink = _dilate(_drop_straight_lines(ink), 1)
        if ink.mean() < 0.005:
            skipped.append((row.get("source"), "no-glyph-pixels"))
            continue
        colour = _stroke_colour(sub, ink)
        sub[ink] = bg[ink]
        arr[y0:y1, x0:x1] = sub
        placed.append((row, (x0, y0, x1, y1), colour))

    im = Image.fromarray(arr)
    draw = ImageDraw.Draw(im)

    # OCR boxes of tightly spaced lines overlap each other, so cap every glyph to the real
    # line pitch and centre it, otherwise vertically stacked neighbours collide.
    centres = [((b[1] + b[3]) / 2.0, b, i) for i, (_, b, _) in enumerate(placed)]
    pitch = {}
    for i, (cy, (ax0, ay0, ax1, ay1), _) in enumerate(centres):
        best = ay1 - ay0
        for j, (oy, (bx0, by0, bx1, by1), _) in enumerate(centres):
            if i == j or min(ax1, bx1) - max(ax0, bx0) < 0.5 * (ax1 - ax0):
                continue                      # only stacked, horizontally aligned labels
            if abs(oy - cy) < 60:
                best = min(best, abs(oy - cy))
        pitch[i] = max(9, best)

    # Pass 2: typeset the target text at the freed position, matched size and colour.
    for n, (row, (x0, y0, x1, y1), colour) in enumerate(placed):
        text = str(row["target"]).strip()
        box_w, box_h = x1 - x0, y1 - y0
        size = max(8, min(int(round(box_h * 0.94)), int(round(pitch[n] * 0.86))))
        if row.get("size"):
            size = min(size, int(row["size"]))
        fnt = ImageFont.truetype(str(font), size)
        while size > 8 and draw.textlength(text, font=fnt) > box_w + 2:
            size -= 1
            fnt = ImageFont.truetype(str(font), size)
        if draw.textlength(text, font=fnt) > box_w + 2:
            skipped.append((row.get("source"), f"too-wide@{size}"))
        angle = float(row.get("angle") or 0.0)
        if not angle:
            asc, desc = fnt.getmetrics()
            cy = (y0 + y1) / 2.0
            draw.text((x0, int(round(cy - (asc + desc) / 2.0))), text, font=fnt, fill=colour)
            continue
        tile = Image.new("RGBA", (int(draw.textlength(text, font=fnt)) + 8, box_h * 3), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((4, box_h), text, font=fnt, fill=colour + (255,))
        tile = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
        im.paste(tile, (x0 + (box_w - tile.width) // 2, y0 + (box_h - tile.height) // 2), tile)

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    rects = [box for _, box, _ in placed]
    return {"source": str(source), "output": str(out), "canvas": [im.width, im.height],
            "rendered": len(placed), "boxes": rects, "skipped": skipped}


def verify(source: Path, output: Path, rects: list) -> dict:
    """Measure graphic survival OUTSIDE the boxes that were deliberately edited.

    Counting the erased text itself as lost edges reports a false failure; the whole point of
    this method is that nothing outside a label box changes.
    """
    a = np.asarray(Image.open(source).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(output).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"error": f"canvas changed {a.shape[1]}x{a.shape[0]} -> {b.shape[1]}x{b.shape[0]}"}
    outside = np.ones(a.shape[:2], dtype=bool)
    for x0, y0, x1, y1 in rects:
        outside[int(y0):int(y1), int(x0):int(x1)] = False
    d = np.abs(a - b).max(axis=2)
    ga = np.abs(np.diff(a.mean(axis=2), axis=1)) > 30
    gb = np.abs(np.diff(b.mean(axis=2), axis=1)) > 30
    keep = ga & outside[:, :ga.shape[1]]
    return {
        "outside_changed_pct": round(100 * ((d > 90) & outside).sum() / max(1, outside.sum()), 4),
        "outside_edges_retained_pct": round(100 * gb[keep].mean(), 1) if keep.any() else 100.0,
        "inside_changed_pct": round(100 * ((d > 90) & ~outside).sum() / max(1, (~outside).sum()), 1),
    }


def ocr(image: Path, out: Path, min_conf: float) -> dict:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise SystemExit("rapidocr_onnxruntime is not installed; hand-author the label table instead")
    rows, _ = RapidOCR()(str(image))
    labels = []
    for quad, text, conf in rows or []:
        if float(conf) < min_conf:
            continue
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        labels.append({"source": text, "target": "", "x0": round(min(xs), 1),
                       "y0": round(min(ys), 1), "x1": round(max(xs), 1), "y1": round(max(ys), 1),
                       "angle": 0.0, "size": None, "confidence": round(float(conf), 3)})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"labels": labels}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"image": str(image), "boxes": len(labels), "table": str(out)}


def zoom(image: Path, box: tuple, out: Path, scale: int) -> dict:
    im = Image.open(image).convert("RGB").crop(box)
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return {"crop": list(box), "written": str(out), "size": [im.width, im.height]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ocr")
    a.add_argument("image", type=Path)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--min-conf", type=float, default=0.5)

    a = sub.add_parser("render")
    a.add_argument("image", type=Path)
    a.add_argument("--labels", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--font", type=Path, default=None)
    a.add_argument("--report", type=Path, default=None)

    a = sub.add_parser("verify")
    a.add_argument("image", type=Path)
    a.add_argument("output", type=Path)
    a.add_argument("--labels", type=Path, required=True)

    a = sub.add_parser("zoom")
    a.add_argument("image", type=Path)
    a.add_argument("--box", type=int, nargs=4, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--scale", type=int, default=3)

    args = p.parse_args(argv)

    if args.cmd == "ocr":
        result = ocr(args.image, args.out, args.min_conf)
    elif args.cmd == "render":
        result = render(args.image, args.labels, args.out, args.font or default_font())
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    elif args.cmd == "verify":
        table = [r for r in load_table(args.labels) if str(r.get("target") or "").strip()]
        rects = [(max(0, float(r["x0"])) - PAD, max(0, float(r["y0"])) - PAD,
                  float(r["x1"]) + PAD, float(r["y1"]) + PAD) for r in table]
        result = verify(args.image, args.output, rects)
    else:
        result = zoom(args.image, tuple(args.box), args.out, args.scale)

    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
