from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_excel_package import inspect_package, _is_invisible_rectangle  # noqa: E402


WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

SHEET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheetData/><drawing r:id="rIdDrawing"/>
</worksheet>"""


class ExcelPackageInspectorTests(unittest.TestCase):
    def test_real_workbook_pipeline_localizes_image_bytes(self):
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as ExcelImage
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, replacement = root / "original.png", root / "replacement.png"
            Image.new("RGB", (16, 16), "white").save(original)
            Image.new("RGB", (16, 16), "black").save(replacement)
            workbook = Workbook()
            workbook.active["A1"] = "设备"
            for cell in ("A3", "D3"):
                workbook.active.add_image(ExcelImage(io.BytesIO(original.read_bytes())), cell)
            source, output, job = root / "source.xlsx", root / "output.xlsx", root / "job"
            workbook.save(source)
            node = Path(sys.executable).parent.parent / "node" / "bin" / "node.exe"
            pipeline = ROOT / "scripts" / "excel_pipeline.mjs"
            def run(*args):
                result = subprocess.run([str(node), str(pipeline), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
                self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            run("inspect", "--input", source, "--job-dir", job, "--target-language", "en", "--output-mode", "monolingual")
            run("prepare", "--job-dir", job)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for unit in manifest["translation_units"]:
                unit.update(status="translated", translation="Equipment")
            for image in manifest["images"]:
                image.update(status="localized", replacement_path=str(replacement), replacement_sha256=hashlib.sha256(replacement.read_bytes()).hexdigest())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            run("apply", "--input", source, "--job-dir", job, "--output", output)
            run("verify", "--source", source, "--job-dir", job, "--output", output)
            self.assertTrue(json.loads((job / "verification.json").read_text(encoding="utf-8"))["passed"])

    def test_localized_image_writes_every_copy_and_preserves_other_parts(self):
        import inspect_excel_package as inspector
        from PIL import Image
        def png(color, size=(16, 16)):
            data = io.BytesIO()
            Image.new("RGB", size, color).save(data, format="PNG")
            return data.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            original, translated = png("white"), png("black")
            package = self.make_package(directory, media={"xl/media/a.png": original, "xl/media/b.png": original})
            replacement = Path(directory) / "translated.png"
            replacement.write_bytes(translated)
            with ZipFile(package) as archive:
                before = {name: archive.read(name) for name in archive.namelist()}
            group = inspect_package(package)["images"][0]
            manifest = {"images": [{**group, "status": "localized", "replacement_path": str(replacement),
                                    "replacement_sha256": hashlib.sha256(translated).hexdigest()}]}
            inspector.apply_image_replacements(package, manifest)
            inspector.verify_image_manifest(inspect_package(package), manifest)
            with ZipFile(package) as archive:
                for name, data in before.items():
                    self.assertEqual(translated if name.startswith("xl/media/") else data, archive.read(name))
            with self.assertRaisesRegex(ValueError, "image"):
                inspector.verify_image_manifest({"images": []}, manifest)

    def test_localized_image_requires_same_format_and_dimensions(self):
        import inspect_excel_package as inspector
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            buffer = io.BytesIO()
            Image.new("RGB", (16, 16)).save(buffer, format="PNG")
            package = self.make_package(directory, media={"xl/media/a.png": buffer.getvalue()})
            before = package.read_bytes()
            replacement = Path(directory) / "wrong-size.png"
            Image.new("RGB", (8, 8)).save(replacement)
            manifest = {"images": [{"sha256": hashlib.sha256(buffer.getvalue()).hexdigest(), "status": "localized",
                                    "replacement_path": str(replacement), "replacement_sha256": hashlib.sha256(replacement.read_bytes()).hexdigest()}]}
            with self.assertRaisesRegex(ValueError, "dimensions"):
                inspector.apply_image_replacements(package, manifest)
            self.assertEqual(before, package.read_bytes())

    def test_hidden_paint_cache_is_inactive_but_live_paint_and_unknown_extensions_are_not(self):
        xml = '''<xdr:sp xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main">
          <xdr:spPr><a:prstGeom prst="rect"/><a:noFill/><a:ln><a:noFill/></a:ln>
          <a:extLst><a:ext uri="{909E8E84-426E-40DD-AFC4-6F175D3DCCD1}">
          <a14:hiddenFill><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a14:hiddenFill>
          </a:ext></a:extLst></xdr:spPr></xdr:sp>'''
        self.assertTrue(_is_invisible_rectangle(ET.fromstring(xml)))
        for changed in [
            xml.replace('<a:noFill/>', '<a:solidFill/>', 1),
            xml.replace('909E8E84-426E-40DD-AFC4-6F175D3DCCD1', 'UNKNOWN'),
            xml.replace('drawing/2010/main', 'unrecognized-namespace'),
            xml.replace('</xdr:sp>', '<xdr:txBody><a:p><a:r><a:t>Label</a:t></a:r></a:p></xdr:txBody></xdr:sp>'),
            xml.replace('</xdr:spPr>', '<a:effectLst><a:outerShdw/></a:effectLst></xdr:spPr>'),
        ]:
            with self.subTest(changed=changed):
                self.assertFalse(_is_invisible_rectangle(ET.fromstring(changed)))

    def make_package(self, directory, media=None, include_features=(), drawing_xml=None):
        media = media or {}
        path = Path(directory) / "sample.xlsx"
        with ZipFile(path, "w") as archive:
            archive.writestr("xl/workbook.xml", WORKBOOK_XML)
            archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
            archive.writestr("xl/worksheets/sheet1.xml", SHEET_XML)
            if media:
                archive.writestr(
                    "xl/worksheets/_rels/sheet1.xml.rels",
                    """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                    <Relationship Id="rIdDrawing" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
                    </Relationships>""",
                )
                anchors = []
                relationships = []
                for index, media_path in enumerate(media, start=1):
                    anchors.append(
                        f'<xdr:twoCellAnchor><xdr:pic><xdr:blipFill><a:blip r:embed="rIdImage{index}"/></xdr:blipFill></xdr:pic></xdr:twoCellAnchor>'
                    )
                    relationships.append(
                        f'<Relationship Id="rIdImage{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{Path(media_path).name}"/>'
                    )
                archive.writestr(
                    "xl/drawings/drawing1.xml",
                    '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    + "".join(anchors)
                    + "</xdr:wsDr>",
                )
                archive.writestr(
                    "xl/drawings/_rels/drawing1.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(relationships)
                    + "</Relationships>",
                )
            elif drawing_xml:
                archive.writestr("xl/drawings/drawing1.xml", drawing_xml)
            for media_path, data in media.items():
                archive.writestr(media_path, data)
            feature_parts = {
                "vba": ("xl/vbaProject.bin", b"vba"),
                "chart": ("xl/charts/chart1.xml", b"<chart/>") ,
                "comment": ("xl/comments1.xml", b"<comments/>"),
                "external_link": ("xl/externalLinks/externalLink1.xml", b"<externalLink/>"),
                "table": ("xl/tables/table1.xml", b"<table/>"),
            }
            for feature in include_features:
                name, data = feature_parts[feature]
                archive.writestr(name, data)
        return path

    def test_reports_no_images_for_plain_package(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect_package(self.make_package(directory))
        self.assertEqual([], report["images"])
        self.assertEqual(0, report["features"]["image_occurrence_count"])

    def test_groups_identical_image_bytes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = self.make_package(
                directory,
                media={"xl/media/image1.png": b"same", "xl/media/image2.png": b"same"},
            )
            report = inspect_package(workbook)
        self.assertEqual(1, len(report["images"]))
        self.assertEqual(2, report["images"][0]["occurrence_count"])
        self.assertEqual(["Sheet1"], report["images"][0]["sheets"])
        self.assertEqual(hashlib.sha256(b"same").hexdigest(), report["images"][0]["sha256"])

    def test_keeps_distinct_image_hashes_and_extracts_one_file_per_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = self.make_package(
                directory,
                media={"xl/media/image1.png": b"first", "xl/media/image2.jpeg": b"second"},
            )
            extract_dir = Path(directory) / "images"
            report = inspect_package(workbook, extract_dir)
            self.assertEqual(2, len(report["images"]))
            extracted = [Path(item["extracted_path"]) for item in report["images"]]
            self.assertTrue(all(path.is_file() for path in extracted))
            self.assertEqual({b"first", b"second"}, {path.read_bytes() for path in extracted})

    def test_detects_risk_features(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = self.make_package(
                directory,
                media={"xl/media/image1.png": b"image"},
                include_features={"vba", "chart", "comment", "external_link", "table"},
            )
            features = inspect_package(workbook)["features"]
        self.assertTrue(features["has_vba"])
        self.assertEqual(1, features["chart_count"])
        self.assertEqual(1, features["comment_count"])
        self.assertEqual(1, features["external_link_count"])
        self.assertEqual(1, features["table_count"])
        self.assertEqual(1, features["drawing_count"])

    def test_tiny_empty_shapes_are_decorative(self):
        drawing = """<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <xdr:twoCellAnchor><xdr:sp><xdr:spPr><a:xfrm><a:ext cx="9525" cy="238125"/></a:xfrm></xdr:spPr></xdr:sp></xdr:twoCellAnchor>
        </xdr:wsDr>"""
        with tempfile.TemporaryDirectory() as directory:
            features = inspect_package(self.make_package(directory, drawing_xml=drawing))["features"]
        self.assertEqual(0, features["meaningful_drawing_count"])
        self.assertEqual(1, features["decorative_drawing_count"])

    def test_text_shape_is_meaningful(self):
        drawing = """<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <xdr:twoCellAnchor><xdr:sp><xdr:txBody><a:p><a:r><a:t>Note</a:t></a:r></a:p></xdr:txBody></xdr:sp></xdr:twoCellAnchor>
        </xdr:wsDr>"""
        with tempfile.TemporaryDirectory() as directory:
            features = inspect_package(self.make_package(directory, drawing_xml=drawing))["features"]
        self.assertEqual(1, features["meaningful_drawing_count"])
        self.assertEqual(0, features["decorative_drawing_count"])

    def test_large_invisible_rectangles_are_decorative_without_modifying_package(self):
        shape = '<xdr:sp><xdr:spPr><a:xfrm><a:ext cx="1270000" cy="1270000"/></a:xfrm><a:prstGeom prst="rect"/><a:noFill/><a:ln><a:noFill/></a:ln></xdr:spPr></xdr:sp>'
        drawing = ('<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                   'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                   + '<xdr:twoCellAnchor>' + shape * 1510 + '</xdr:twoCellAnchor></xdr:wsDr>')
        with tempfile.TemporaryDirectory() as directory:
            workbook = self.make_package(directory, drawing_xml=drawing)
            before = workbook.read_bytes()
            features = inspect_package(workbook)["features"]
            self.assertEqual(0, features["meaningful_drawing_count"])
            self.assertEqual(1510, features["decorative_drawing_count"])
            self.assertEqual(before, workbook.read_bytes())

    def test_invisible_exemption_requires_explicit_no_fill_and_no_line_without_effects(self):
        for properties, extra in [
            ('<a:noFill/>', ''),
            ('<a:ln><a:noFill/></a:ln>', ''),
            ('<a:solidFill/><a:ln><a:noFill/></a:ln>', ''),
            ('<a:noFill/><a:ln><a:solidFill/></a:ln>', ''),
            ('<a:noFill/><a:ln><a:noFill/></a:ln><a:effectLst><a:outerShdw/></a:effectLst>', ''),
            ('<a:noFill/><a:ln><a:noFill/></a:ln>', '<xdr:txBody><a:p><a:r><a:t>Equipment</a:t></a:r></a:p></xdr:txBody>'),
            ('<a:noFill/><a:ln><a:noFill/></a:ln>', '<xdr:style><a:effectRef idx="2"/></xdr:style>'),
        ]:
            with self.subTest(properties=properties, extra=extra), tempfile.TemporaryDirectory() as directory:
                drawing = ('<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                           '<xdr:twoCellAnchor><xdr:sp><xdr:spPr><a:xfrm><a:ext cx="1270000" cy="1270000"/>'
                           '</a:xfrm><a:prstGeom prst="rect"/>' + properties + '</xdr:spPr>' + extra
                           + '</xdr:sp></xdr:twoCellAnchor></xdr:wsDr>')
                features = inspect_package(self.make_package(directory, drawing_xml=drawing))["features"]
                self.assertEqual(1, features["meaningful_drawing_count"])

    def test_connector_shape_is_meaningful(self):
        drawing = """<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">
          <xdr:twoCellAnchor><xdr:cxnSp/></xdr:twoCellAnchor>
        </xdr:wsDr>"""
        with tempfile.TemporaryDirectory() as directory:
            features = inspect_package(self.make_package(directory, drawing_xml=drawing))["features"]
        self.assertEqual(1, features["meaningful_drawing_count"])


if __name__ == "__main__":
    unittest.main()
