from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "formats" / "image" / "scripts" / "image_pdf_bridge.py"


class ImagePdfBridgeTests(unittest.TestCase):
    def run_bridge(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BRIDGE), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_wrap_png_creates_one_page_pdf_and_records_source_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (320, 180), "white").save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"

            result = self.run_bridge("wrap", str(source), str(pdf), str(metadata))

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, len(PdfReader(pdf).pages))
            report = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual([320, 180], report["pixel_size"])
            self.assertEqual("PNG", report["format"])
            self.assertEqual("RGB", report["mode"])

    def test_wrap_rejects_unsupported_image_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.gif"
            Image.new("RGB", (10, 10), "white").save(source)
            result = self.run_bridge("wrap", str(source), str(root / "x.pdf"), str(root / "x.json"))
            self.assertEqual(2, result.returncode)
            self.assertIn("PNG or JPEG", result.stderr)

    def test_unwrap_restores_png_pixel_size_and_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            image = Image.new("RGBA", (96, 64), (255, 255, 255, 0))
            for x in range(20, 76):
                for y in range(16, 48):
                    image.putpixel((x, y), (20, 40, 60, 255))
            image.save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"
            self.assertEqual(0, self.run_bridge("wrap", str(source), str(pdf), str(metadata)).returncode)

            output = root / "translated.png"
            result = self.run_bridge("unwrap", str(pdf), str(metadata), str(output))

            self.assertEqual(0, result.returncode, result.stderr)
            with Image.open(output) as translated:
                self.assertEqual((96, 64), translated.size)
                self.assertEqual("RGBA", translated.mode)
                self.assertEqual(0, translated.getpixel((0, 0))[3])
                self.assertEqual(255, translated.getpixel((48, 32))[3])

    def test_unwrap_requires_same_output_format_as_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jpg"
            Image.new("RGB", (80, 50), "white").save(source)
            pdf = root / "source.pdf"
            metadata = root / "image-metadata.json"
            self.assertEqual(0, self.run_bridge("wrap", str(source), str(pdf), str(metadata)).returncode)

            result = self.run_bridge("unwrap", str(pdf), str(metadata), str(root / "wrong.png"))
            self.assertEqual(2, result.returncode)
            self.assertIn("same image format", result.stderr)


if __name__ == "__main__":
    unittest.main()
