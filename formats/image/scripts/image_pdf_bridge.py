from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SUPPORTED_SUFFIXES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}


class BridgeError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_format(path: Path) -> str:
    try:
        return SUPPORTED_SUFFIXES[path.suffix.lower()]
    except KeyError as exc:
        raise BridgeError("Input and output images must use PNG or JPEG format") from exc


def find_pdftoppm() -> str:
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
    raise BridgeError("pdftoppm is unavailable")


def wrap(source: Path, output_pdf: Path, metadata_path: Path) -> None:
    declared_format = expected_format(source)
    if not source.is_file():
        raise BridgeError(f"Source image does not exist: {source}")

    with Image.open(source) as opened:
        if getattr(opened, "n_frames", 1) != 1 or getattr(opened, "is_animated", False):
            raise BridgeError("Animated or multi-frame images are unsupported")
        if opened.format != declared_format:
            raise BridgeError("Image extension does not match its encoded PNG or JPEG format")
        image = ImageOps.exif_transpose(opened).copy()

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    alpha_name = None
    if declared_format == "PNG" and "A" in image.getbands():
        alpha_name = f"{metadata_path.stem}-alpha.png"
        image.getchannel("A").save(metadata_path.with_name(alpha_name), format="PNG")
        background = Image.new("RGB", image.size, "white")
        background.paste(image.convert("RGB"), mask=image.getchannel("A"))
        pdf_image = background
    else:
        pdf_image = image.convert("RGB")

    encoded = BytesIO()
    pdf_image.save(encoded, format="PNG")
    encoded.seek(0)
    width, height = pdf_image.size
    page = canvas.Canvas(str(output_pdf), pagesize=(width, height), pageCompression=1)
    page.drawImage(ImageReader(encoded), 0, 0, width=width, height=height)
    page.showPage()
    page.save()

    metadata = {
        "schema_version": 1,
        "source_sha256": sha256_file(source),
        "format": declared_format,
        "source_suffix": source.suffix.lower(),
        "pixel_size": [width, height],
        "mode": image.mode,
        "alpha_file": alpha_name,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def unwrap(translated_pdf: Path, metadata_path: Path, output_image: Path) -> None:
    if not translated_pdf.is_file() or not metadata_path.is_file():
        raise BridgeError("Translated PDF and image metadata must exist")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    output_format = expected_format(output_image)
    if output_format != metadata.get("format"):
        raise BridgeError("Output must use the same image format as the source")

    output_image.parent.mkdir(parents=True, exist_ok=True)
    render_prefix = output_image.parent / f".{output_image.stem}-render"
    command = [find_pdftoppm(), "-f", "1", "-l", "1", "-r", "72", "-singlefile", "-png", str(translated_pdf), str(render_prefix)]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    rendered_path = render_prefix.with_suffix(".png")
    if completed.returncode != 0 or not rendered_path.exists():
        raise BridgeError(completed.stderr.strip() or "Failed to render translated PDF")

    try:
        with Image.open(rendered_path) as opened:
            rendered = opened.convert("RGB")
        size = tuple(int(value) for value in metadata["pixel_size"])
        if rendered.size != size:
            rendered = rendered.resize(size, Image.Resampling.LANCZOS)
        alpha_file = metadata.get("alpha_file")
        if output_format == "PNG" and alpha_file:
            with Image.open(metadata_path.with_name(alpha_file)) as alpha_image:
                alpha = alpha_image.convert("L")
            if alpha.size != size:
                raise BridgeError("Stored PNG alpha dimensions do not match the source")
            rendered.putalpha(alpha)
            rendered.save(output_image, format="PNG")
        elif output_format == "PNG":
            rendered.save(output_image, format="PNG")
        else:
            rendered.save(output_image, format="JPEG", quality=95, subsampling=0, optimize=True)
    finally:
        rendered_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge static PNG/JPEG images through the scan-PDF workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    wrap_parser = subparsers.add_parser("wrap")
    wrap_parser.add_argument("source", type=Path)
    wrap_parser.add_argument("output_pdf", type=Path)
    wrap_parser.add_argument("metadata", type=Path)
    unwrap_parser = subparsers.add_parser("unwrap")
    unwrap_parser.add_argument("translated_pdf", type=Path)
    unwrap_parser.add_argument("metadata", type=Path)
    unwrap_parser.add_argument("output_image", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "wrap":
            wrap(args.source, args.output_pdf, args.metadata)
        else:
            unwrap(args.translated_pdf, args.metadata, args.output_image)
        return 0
    except (BridgeError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
