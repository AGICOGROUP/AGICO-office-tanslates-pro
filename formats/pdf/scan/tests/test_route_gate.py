from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classify_pdf.py"
SPEC = importlib.util.spec_from_file_location("classify_pdf", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class RouteGateTests(unittest.TestCase):
    def test_rotated_scan_page_requires_normalization(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name) / "rotated.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(width=200, height=100)
            page.rotate(90)
            with source.open("wb") as stream:
                writer.write(stream)

            report = MODULE.classify(source)

            self.assertEqual(report["route"], "normalize-rotation-first")
            self.assertEqual(report["rotated_pages"], [1])


if __name__ == "__main__":
    unittest.main()
