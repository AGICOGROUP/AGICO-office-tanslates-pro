from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_pptx_package import inspect_package  # noqa: E402


def slide_xml(text: str, shape_id: int = 2) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="TextBox 1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody>
    </p:sp>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="3" name="Picture 1"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
      <p:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rIdImage"/></p:blipFill>
      <p:spPr/>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>"""


SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>"""


class PowerPointPackageInspectorTests(unittest.TestCase):
    def make_deck(self, directory: str, texts=("重复术语", "重复术语")) -> Path:
        path = Path(directory) / "sample.pptx"
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("ppt/presentation.xml", "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>")
            archive.writestr("ppt/media/image1.png", b"same-image-bytes")
            for index, text in enumerate(texts, start=1):
                archive.writestr(f"ppt/slides/slide{index}.xml", slide_xml(text))
                archive.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", SLIDE_RELS)
        return path

    def test_extracts_each_occurrence_and_groups_repeated_image_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_deck(directory))

        self.assertEqual(2, len(report["occurrences"]))
        self.assertEqual([1, 2], [item["slide_index"] for item in report["occurrences"]])
        self.assertEqual(1, len(report["image_groups"]))
        self.assertEqual(2, len(report["image_groups"][0]["occurrences"]))
        self.assertEqual(1, report["metrics"]["package_passes"])

    def test_plain_text_boxes_do_not_make_the_deck_complex(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_deck(directory, texts=("普通标题",)))

        self.assertEqual("fast", report["risk_plan"]["route"])
        self.assertEqual([], report["risk_plan"]["strict_reasons"])

    def test_chart_part_routes_the_deck_to_complex(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = self.make_deck(directory, texts=("标题",))
            with ZipFile(deck, "a", ZIP_DEFLATED) as archive:
                archive.writestr("ppt/charts/chart1.xml", "<chart/>")
            report = inspect_package(deck)

        self.assertEqual("complex", report["risk_plan"]["route"])
        self.assertIn("chart", report["risk_plan"]["complex_reasons"])


if __name__ == "__main__":
    unittest.main()
