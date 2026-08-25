from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_excel_package import inspect_package  # noqa: E402


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
    def make_package(self, directory, media=None, include_features=()):
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
                media={
                    "xl/media/image1.png": b"same",
                    "xl/media/image2.png": b"same",
                },
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
                media={
                    "xl/media/image1.png": b"first",
                    "xl/media/image2.jpeg": b"second",
                },
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


if __name__ == "__main__":
    unittest.main()
