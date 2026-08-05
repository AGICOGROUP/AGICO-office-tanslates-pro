import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

try:
    from layout_adjustments import validate_layout_adjustment
except ModuleNotFoundError:  # Support direct import by validation/test harnesses.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from layout_adjustments import validate_layout_adjustment


FONT_REGULAR = "ImageTextRegular"
FONT_BOLD = "ImageTextBold"


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def default_font(bold: bool) -> Path:
    candidates = (
        [
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ]
        if bold
        else [
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No suitable TrueType font found; pass --regular-font/--bold-font")


def register_fonts(regular: Path, bold: Path) -> None:
    if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
    if FONT_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))


def pixel_box_to_page(
    box: list[int],
    image_size: tuple[int, int],
    placement: list[float],
) -> tuple[float, float, float, float]:
    pixel_width, pixel_height = image_size
    image_x, image_y, page_width, page_height = placement
    scale_x = page_width / pixel_width
    scale_y = page_height / pixel_height
    x0, y0, x1, y1 = box
    return (
        image_x + x0 * scale_x,
        image_y + (pixel_height - y1) * scale_y,
        image_x + x1 * scale_x,
        image_y + (pixel_height - y0) * scale_y,
    )


def fitted_size(
    lines: list[str],
    font_name: str,
    maximum_size: float,
    maximum_width: float,
    maximum_height: float,
) -> float:
    size = maximum_size
    while size >= 1.8:
        width = max(pdfmetrics.stringWidth(line, font_name, size) for line in lines)
        height = len(lines) * size * 1.16
        if width <= maximum_width and height <= maximum_height:
            return size
        size -= 0.1
    return 1.8


def draw_horizontal(
    pdf: canvas.Canvas,
    rect: tuple[float, float, float, float],
    region: dict,
) -> None:
    left, bottom, right, top = rect
    lines = region["text"].splitlines()
    font_name = FONT_BOLD if region.get("bold") else FONT_REGULAR
    size = fitted_size(
        lines,
        font_name,
        float(region["max_font"]),
        max(1.0, right - left - 1.2),
        max(1.0, top - bottom - 0.8),
    )
    line_height = size * 1.16
    block_height = len(lines) * line_height
    baseline = bottom + (top - bottom - block_height) / 2 + block_height - size
    pdf.setFont(font_name, size)
    for index, line in enumerate(lines):
        pdf.drawCentredString(
            (left + right) / 2,
            baseline - index * line_height,
            line,
        )


def draw_rotated(
    pdf: canvas.Canvas,
    rect: tuple[float, float, float, float],
    region: dict,
) -> None:
    left, bottom, right, top = rect
    font_name = FONT_BOLD if region.get("bold") else FONT_REGULAR
    text = region["text"].replace("\n", " ")
    size = fitted_size(
        [text],
        font_name,
        float(region["max_font"]),
        max(1.0, top - bottom - 1.0),
        max(1.0, right - left - 0.5),
    )
    pdf.saveState()
    pdf.translate((left + right) / 2, (bottom + top) / 2)
    pdf.rotate(float(region.get("rotation", 90)))
    pdf.setFont(font_name, size)
    pdf.drawCentredString(0, -size * 0.34, text)
    pdf.restoreState()


def make_overlay(
    page_width: float,
    page_height: float,
    items: list[dict],
    base: Path,
) -> bytes:
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_width, page_height), pageCompression=1)
    for item in items:
        clean_path = resolve(base, item["output"])
        with Image.open(clean_path) as clean_image:
            image_size = clean_image.size
        x, y, width, height = item["placement"]
        adjustment = item.get("layout_adjustment")
        if adjustment:
            validate_layout_adjustment(
                adjustment,
                page_width,
                page_height,
                adjustment.get("protected_boxes", []),
            )
            old_x0, old_y0, old_x1, old_y1 = adjustment["original_box"]
            pdf.setFillColorRGB(*adjustment.get("background", [1, 1, 1]))
            pdf.rect(old_x0, old_y0, old_x1 - old_x0, old_y1 - old_y0, fill=1, stroke=0)
            target_x0, target_y0, target_x1, target_y1 = adjustment["target_box"]
            x, y, width, height = target_x0, target_y0, target_x1 - target_x0, target_y1 - target_y0
            item["placement"] = [x, y, width, height]
        pdf.drawImage(
            ImageReader(str(clean_path)),
            x,
            y,
            width=width,
            height=height,
            preserveAspectRatio=False,
            mask=None,
        )
        for region in item["regions"]:
            if not region.get("text"):
                continue
            rect = pixel_box_to_page(region["box"], image_size, item["placement"])
            pdf.setFillColorRGB(*region.get("color", [0.07, 0.07, 0.07]))
            if region.get("rotation"):
                draw_rotated(pdf, rect, region)
            else:
                draw_horizontal(pdf, rect, region)
    pdf.save()
    return stream.getvalue()


def apply(
    input_pdf: Path,
    metadata_path: Path,
    output_pdf: Path,
    regular_font: Path,
    bold_font: Path,
) -> None:
    register_fonts(regular_font, bold_font)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    base = metadata_path.parent
    by_page: dict[int, list[dict]] = {}
    for item in metadata["images"]:
        by_page.setdefault(int(item["page"]), []).append(item)

    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))
    for page_number, items in by_page.items():
        page = writer.pages[page_number - 1]
        overlay = PdfReader(
            io.BytesIO(
                make_overlay(
                    float(page.mediabox.width),
                    float(page.mediabox.height),
                    items,
                    base,
                )
            )
        ).pages[0]
        page.merge_page(overlay, over=True)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as stream:
        writer.write(stream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("--regular-font", type=Path)
    parser.add_argument("--bold-font", type=Path)
    args = parser.parse_args()
    apply(
        args.input_pdf,
        args.metadata,
        args.output_pdf,
        args.regular_font or default_font(False),
        args.bold_font or default_font(True),
    )


if __name__ == "__main__":
    main()
