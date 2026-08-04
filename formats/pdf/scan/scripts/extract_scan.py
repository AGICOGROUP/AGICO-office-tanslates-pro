from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import re
import sys
from pathlib import Path

from PIL import Image
from pypdf import PdfReader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_pdftoppm() -> str:
    # The bundled .CMD shim cannot reliably forward non-ASCII Windows paths.
    # Prefer the real executable so Chinese source filenames remain intact.
    bundled = (
        Path(sys.executable).resolve().parent.parent
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdftoppm.exe"
    )
    if bundled.exists():
        return str(bundled)
    discovered = shutil.which("pdftoppm")
    if discovered:
        return discovered
    raise RuntimeError("pdftoppm is unavailable")


def _normalize_box(points, scale: float) -> list[float]:
    xs = [float(point[0]) / scale for point in points]
    ys = [float(point[1]) / scale for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _ocr_pass(engine, image: Image.Image, scale: float) -> list[dict]:
    working = image
    if scale != 1.0:
        working = image.resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    result, _ = engine(working)
    records = []
    for item in result or []:
        points, text, score = item
        value = str(text).strip()
        if value:
            records.append(
                {
                    "box": _normalize_box(points, scale),
                    "text": value,
                    "score": float(score),
                    "scale": scale,
                }
            )
    return records


def _iou(first: list[float], second: list[float]) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    a = (first[2] - first[0]) * (first[3] - first[1])
    b = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(a + b - intersection, 1e-9)


def merge_ocr_records(records: list[dict]) -> list[dict]:
    chosen: list[dict] = []
    for record in sorted(records, key=lambda item: item["score"], reverse=True):
        duplicate = None
        for index, existing in enumerate(chosen):
            same_text = record["text"] == existing["text"]
            overlap = _iou(record["box"], existing["box"])
            if overlap >= 0.55 or (same_text and overlap >= 0.25):
                duplicate = index
                break
        if duplicate is None:
            chosen.append(record)
    return sorted(chosen, key=lambda item: (item["box"][1], item["box"][0]))


def extract_selected_pages(
    source: str | Path,
    pages: list[int],
    output_dir: str | Path,
    dpi: int = 400,
    run_ocr: bool = True,
    expected_sha256: str | None = None,
) -> dict:
    source_path = Path(source).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    actual_hash = sha256_file(source_path)
    if expected_sha256 and actual_hash.lower() != expected_sha256.lower():
        raise ValueError(
            f"source SHA-256 mismatch: expected {expected_sha256}, actual {actual_hash}"
        )

    reader = PdfReader(str(source_path))
    if any(page < 1 or page > len(reader.pages) for page in pages):
        raise ValueError(f"selected pages must be within 1..{len(reader.pages)}")

    render_dir = output_path / f"source-pages-{dpi}dpi"
    render_dir.mkdir(parents=True, exist_ok=True)
    pdftoppm = find_pdftoppm()
    page_records = []
    rendered_paths: dict[int, Path] = {}
    if pages and pages == list(range(min(pages), max(pages) + 1)):
        batch_prefix = render_dir / "source-page"
        command = [
            pdftoppm, "-f", str(min(pages)), "-l", str(max(pages)),
            "-r", str(dpi), "-png", str(source_path), str(batch_prefix),
        ]
        subprocess.run(command, check=True, capture_output=True)
        for candidate in render_dir.glob("source-page-*.png"):
            match = re.search(r"-(\d+)$", candidate.stem)
            if match:
                rendered_paths[int(match.group(1))] = candidate
    for page_number in pages:
        page = reader.pages[page_number - 1]
        width_pt = float(page.mediabox.width)
        height_pt = float(page.mediabox.height)
        render_path = rendered_paths.get(page_number)
        if render_path is None:
            prefix = render_dir / f"source-page-{page_number:02d}"
            command = [
                pdftoppm, "-f", str(page_number), "-l", str(page_number),
                "-r", str(dpi), "-png", "-singlefile",
                str(source_path), str(prefix),
            ]
            subprocess.run(command, check=True, capture_output=True)
            render_path = prefix.with_suffix(".png")
        with Image.open(render_path) as image:
            pixel_width, pixel_height = image.size
        page_records.append(
            {
                "source_page": page_number,
                "width_pt": width_pt,
                "height_pt": height_pt,
                "rotation": int(page.get("/Rotate", 0) or 0),
                "media_box": [float(value) for value in page.mediabox],
                "crop_box": [float(value) for value in page.cropbox],
                "render_path": str(render_path),
                "render_sha256": sha256_file(render_path),
                "pixel_width": pixel_width,
                "pixel_height": pixel_height,
                "dpi": dpi,
            }
        )

    source_lines = []
    if run_ocr:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        for page_record in page_records:
            with Image.open(page_record["render_path"]) as loaded:
                image = loaded.convert("RGB")
            raw = _ocr_pass(engine, image, 1.0) + _ocr_pass(engine, image, 3.0)
            merged = merge_ocr_records(raw)
            for index, record in enumerate(merged, 1):
                source_lines.append(
                    {
                        "id": f"p{page_record['source_page']:02d}-l{index:03d}",
                        "page": page_record["source_page"],
                        **record,
                    }
                )

    report = {
        "source": str(source_path),
        "source_sha256": actual_hash,
        "source_page_count": len(reader.pages),
        "selected_pages": pages,
        "pages": page_records,
        "source_lines": source_lines,
    }
    (output_path / "extraction-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--pages", default="all", help="all or comma-separated 1-based pages")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dpi", type=int, default=400)
    args = parser.parse_args()
    reader = PdfReader(str(Path(args.source).resolve()))
    pages = (
        list(range(1, len(reader.pages) + 1))
        if args.pages.strip().lower() == "all"
        else [int(value) for value in args.pages.split(",") if value.strip()]
    )
    report = extract_selected_pages(args.source, pages, args.output, dpi=args.dpi)
    print(
        json.dumps(
            {
                "pages": len(report["pages"]),
                "ocr_lines": len(report["source_lines"]),
                "output": str(Path(args.output).resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
