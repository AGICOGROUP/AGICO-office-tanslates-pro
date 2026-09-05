from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_pptx_package import InspectionError, PROTECTED_RE, inspect_package  # noqa: E402


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


TABLE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="7" name="Table 1"/></p:nvGraphicFramePr>
    <a:graphic><a:graphicData><a:tbl>
      <a:tr><a:tc><a:txBody><a:p><a:r><a:t>Cell A</a:t></a:r></a:p></a:txBody></a:tc>
            <a:tc><a:txBody><a:p><a:r><a:t>Cell B</a:t></a:r></a:p></a:txBody></a:tc></a:tr>
    </a:tbl></a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>"""


OLE_IMAGE_SLIDE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="4099" name="Object 3"/></p:nvGraphicFramePr>
    <a:graphic><a:graphicData><p:oleObj progId="Visio.Drawing.11" r:id="rIdOle"><p:pic>
      <p:nvPicPr><p:cNvPr id="0" name="Object 3"/></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rIdImage"/></p:blipFill>
    </p:pic></p:oleObj></a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>"""

OLE_SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
  <Relationship Id="rIdOle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="../embeddings/oleObject1.bin"/>
</Relationships>"""


class PowerPointPackageInspectorTests(unittest.TestCase):
    def make_deck(self, directory: str, texts=("重复术语", "重复术语"), content_types: str = "<Types/>") -> Path:
        path = Path(directory) / "sample.pptx"
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
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

    def test_protected_tokens_are_recognized_when_glued_to_cjk_text(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_deck(directory, texts=("尼龙帆布带B650", '温度变送器G1/2"')))

        tokens = [token for item in report["occurrences"] for token in item["protected_tokens"]]
        self.assertIn("B650", tokens)
        self.assertIn("G1/2", tokens)

    def test_trailing_cjk_is_not_absorbed_into_protected_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_deck(directory, texts=("规格B650档，详见附页",)))

        tokens = report["occurrences"][0]["protected_tokens"]
        self.assertIn("B650", tokens)
        self.assertNotIn("B650档", tokens)

    def test_cjk_glued_source_tokens_survive_into_spaced_translations(self):
        # Mirrors the verify-stage containment check: every token extracted from the
        # CJK-glued source text must appear in the spaced English translation.
        pairs = [
            ("尼龙帆布带B650", "Nylon Canvas Conveyor Belt B650"),
            ('温度变送器G1/2"', 'Temperature Transmitter G1/2"'),
            ("功率75kW", "Power rating 75kW"),
            ("温度80°C", "Temperature 80°C"),
            ("流量50t/h", "Flow rate 50t/h"),
        ]
        for source_text, translated_text in pairs:
            for token in PROTECTED_RE.findall(source_text):
                with self.subTest(source=source_text, token=token):
                    self.assertIn(token, translated_text)

    def test_inventory_has_no_route_tier(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_deck(directory, texts=("普通标题",)))

        self.assertNotIn("risk_plan", report)

    def test_chart_part_does_not_create_an_alternate_route(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = self.make_deck(directory, texts=("标题",))
            with ZipFile(deck, "a", ZIP_DEFLATED) as archive:
                archive.writestr("ppt/charts/chart1.xml", "<chart/>")
            report = inspect_package(deck)

        self.assertNotIn("risk_plan", report)
        self.assertEqual(1, len(report["slides"]))

    def test_rejects_human_text_in_unsupported_editable_parts(self):
        samples = {
            "ppt/charts/chart1.xml": '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:v>Sales</c:v></c:chartSpace>',
            "ppt/diagrams/data1.xml": '<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Process</a:t></dgm:dataModel>',
            "ppt/notesSlides/notesSlide1.xml": '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Speaker note</a:t></p:notes>',
            "ppt/slideMasters/slideMaster1.xml": '<p:sldMaster xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Confidential</a:t></p:sldMaster>',
        }
        for part_name, payload in samples.items():
            with self.subTest(part=part_name), tempfile.TemporaryDirectory() as directory:
                deck = self.make_deck(directory, texts=("Title",))
                with ZipFile(deck, "a", ZIP_DEFLATED) as archive:
                    archive.writestr(part_name, payload)
                with self.assertRaisesRegex(InspectionError, "unsupported editable text"):
                    inspect_package(deck)

    def test_rejects_macro_package_renamed_to_pptx(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = self.make_deck(directory, texts=("Title",))
            with ZipFile(deck, "a", ZIP_DEFLATED) as archive:
                archive.writestr("ppt/vbaProject.bin", b"macro")

            with self.assertRaisesRegex(InspectionError, "macro-enabled PowerPoint package"):
                inspect_package(deck)

    def test_rejects_macro_content_type_renamed_to_pptx(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = self.make_deck(
                directory,
                texts=("Title",),
                content_types='<Types><Override ContentType="application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"/></Types>',
            )

            with self.assertRaisesRegex(InspectionError, "macro-enabled PowerPoint package"):
                inspect_package(deck)

    def test_table_occurrences_keep_com_cell_and_ooxml_paragraph_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "table.pptx"
            with ZipFile(deck, "w", ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("ppt/slides/slide1.xml", TABLE_SLIDE)
            report = inspect_package(deck)

        first, second = report["occurrences"]
        self.assertEqual((1, 1, 1), (first["row"], first["column"], first["paragraph_index"]))
        self.assertEqual(1, first["package_paragraph_index"])
        self.assertEqual((1, 2, 1), (second["row"], second["column"], second["paragraph_index"]))
        self.assertEqual(2, second["package_paragraph_index"])

    def test_embedded_object_preview_is_not_classified_as_an_image(self):
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "ole-image.pptx"
            with ZipFile(deck, "w", ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("ppt/slides/slide1.xml", OLE_IMAGE_SLIDE)
                archive.writestr("ppt/slides/_rels/slide1.xml.rels", OLE_SLIDE_RELS)
                archive.writestr("ppt/media/image1.png", b"preview")
                archive.writestr("ppt/embeddings/oleObject1.bin", b"editable-object")

            report = inspect_package(deck)

        self.assertEqual([], report["image_groups"])
        embedded = report["embedded_objects"][0]
        self.assertEqual(4099, embedded["shape_id"])
        self.assertEqual("Visio.Drawing.11", embedded["prog_id"])
        self.assertEqual("ppt/embeddings/oleObject1.bin", embedded["embedding_path"])


if __name__ == "__main__":
    unittest.main()
