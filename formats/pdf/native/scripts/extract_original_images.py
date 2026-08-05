from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pixel_sha(image) -> str:
    digest = hashlib.sha256()
    digest.update(f"{image.width}x{image.height}:{image.mode}".encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _placement(record: dict[str, Any], page_number: int) -> dict[str, Any]:
    return {
        "page": page_number,
        "x0": float(record["x0"]),
        "y0": float(record["y0"]),
        "x1": float(record["x1"]),
        "y1": float(record["y1"]),
        "width": float(record["width"]),
        "height": float(record["height"]),
    }


def _resource_stem(value: str) -> str:
    return Path(str(value)).stem


def _placements_by_resource_name(
    placements: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in placements:
        name = record.get("name")
        if name:
            by_name.setdefault(_resource_stem(str(name)), []).append(record)
    return by_name


def extract_inventory(
    source: Path, expected_sha256: str, output_dir: Path
) -> dict[str, Any]:
    source = source.resolve()
    actual_hash = sha256_file(source)
    if actual_hash != expected_sha256:
        raise ValueError("source hash mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(source))
    images: list[dict[str, Any]] = []
    with pdfplumber.open(str(source)) as plumber:
        for page_number, page in enumerate(reader.pages, start=1):
            placements = plumber.pages[page_number - 1].images
            placements_by_name = _placements_by_resource_name(placements)
            for image_index, image_file in enumerate(page.images, start=1):
                pil_image = image_file.image.convert("RGB")
                filename = f"p{page_number:04d}-i{image_index:03d}.png"
                output_path = (output_dir / filename).resolve()
                pil_image.save(output_path, format="PNG")
                resource_name = _resource_stem(str(image_file.name))
                matched_records = placements_by_name.get(resource_name, [])
                if not matched_records:
                    matched_records = [
                        record
                        for record in placements
                        if tuple(record.get("srcsize") or ())
                        == (pil_image.width, pil_image.height)
                    ]
                page_placements = [
                    _placement(record, page_number)
                    for record in matched_records
                ]
                images.append(
                    {
                        "id": f"p{page_number:04d}-i{image_index:03d}",
                        "page": page_number,
                        "name": str(image_file.name),
                        "object_id": str(image_file.name),
                        "sha256": _pixel_sha(pil_image),
                        "width_px": pil_image.width,
                        "height_px": pil_image.height,
                        "format": "PNG",
                        "path": str(output_path),
                        "placements": page_placements,
                        "source_kind": "original-xobject",
                        "reviewed": False,
                        "contains_source_text": None,
                        "unreadable_regions": [],
                    }
                )
    inventory = {
        "schema_version": 1,
        "source_path": str(source),
        "source_sha256": actual_hash,
        "images": images,
    }
    (output_dir / "image-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("expected_sha256")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = extract_inventory(
        args.source, args.expected_sha256, args.output_dir
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
