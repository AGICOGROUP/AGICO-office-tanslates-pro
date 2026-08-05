from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "extract_original_images.py"
)
SPEC = importlib.util.spec_from_file_location("extract_original_images", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def make_pdf(path: Path) -> None:
    image = Image.new("RGB", (20, 10), (40, 90, 160))
    data = io.BytesIO()
    image.save(data, format="PNG")
    reader = ImageReader(io.BytesIO(data.getvalue()))
    pdf = canvas.Canvas(str(path), pagesize=(200, 200))
    pdf.drawImage(reader, 10, 20, width=80, height=40)
    pdf.showPage()
    pdf.drawImage(reader, 40, 70, width=100, height=50)
    pdf.save()


class OriginalImageExtractionTests(unittest.TestCase):
    def test_matches_placements_by_scoped_resource_name_not_list_position(self):
        placements = [
            {"name": "Image30", "x0": 10},
            {"name": "Image27", "x0": 700},
        ]
        matched = module._placements_by_resource_name(placements)
        self.assertEqual(matched["Image27"][0]["x0"], 700)
        self.assertEqual(matched["Image30"][0]["x0"], 10)
        self.assertEqual(module._resource_stem("Image27.jpg"), "Image27")

    def test_extracts_images_and_page_placements_from_original(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            inventory = module.extract_inventory(
                source, module.sha256_file(source), root / "images"
            )
            self.assertEqual(inventory["source_sha256"], module.sha256_file(source))
            self.assertEqual(len(inventory["images"]), 2)
            self.assertTrue(
                all(Path(item["path"]).is_file() for item in inventory["images"])
            )
            self.assertEqual(
                [item["placements"][0]["page"] for item in inventory["images"]],
                [1, 2],
            )
            self.assertTrue(
                all(
                    item["source_kind"] == "original-xobject"
                    for item in inventory["images"]
                )
            )

    def test_rejects_source_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "source.pdf"
            make_pdf(source)
            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                module.extract_inventory(source, "0" * 64, root / "images")


if __name__ == "__main__":
    unittest.main()
