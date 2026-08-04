from __future__ import annotations

import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "scripts" / "route_excel_file.py"
CFB = bytes.fromhex("D0CF11E0A1B11AE1")


class ExcelRouterTests(unittest.TestCase):
    def run_router(self, path: Path):
        return subprocess.run(
            [sys.executable, str(ROUTER), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def make_ooxml(self, path: Path, *, macro: bool = False, macro_container: bool = False, vba_target: str = "vbaProject.bin"):
        with ZipFile(path, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
            content_type = "application/vnd.ms-excel.sheet.macroEnabled.main+xml" if macro or macro_container else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
            vba_override = '<Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/>' if macro else ""
            archive.writestr("[Content_Types].xml", f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="{content_type}"/>{vba_override}</Types>')
            if macro:
                archive.writestr("xl/vbaProject.bin", b"macro")
                archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdVba" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="{vba_target}"/></Relationships>')

    def make_cfb_excel(self, path: Path, *, encrypted: bool = False):
        header = bytearray(512)
        header[:8] = CFB
        struct.pack_into("<H", header, 24, 0x003E)
        struct.pack_into("<H", header, 26, 0x0003)
        header[28:30] = b"\xFE\xFF"
        struct.pack_into("<H", header, 30, 9)
        struct.pack_into("<H", header, 32, 6)
        struct.pack_into("<I", header, 44, 1)
        struct.pack_into("<I", header, 48, 0)
        struct.pack_into("<I", header, 56, 4096)
        struct.pack_into("<I", header, 60, 0xFFFFFFFE)
        struct.pack_into("<I", header, 68, 0xFFFFFFFE)
        for offset in range(76, 512, 4):
            struct.pack_into("<I", header, offset, 0xFFFFFFFF)
        struct.pack_into("<I", header, 76, 1)

        directory = bytearray(512)
        root_name = "Root Entry\0".encode("utf-16le")
        directory[: len(root_name)] = root_name
        struct.pack_into("<H", directory, 64, len(root_name))
        directory[66] = 5
        struct.pack_into("<III", directory, 68, 0xFFFFFFFF, 0xFFFFFFFF, 1)
        struct.pack_into("<I", directory, 116, 0xFFFFFFFE)

        workbook_offset = 128
        encoded = "Workbook\0".encode("utf-16le")
        directory[workbook_offset : workbook_offset + len(encoded)] = encoded
        struct.pack_into("<H", directory, workbook_offset + 64, len(encoded))
        directory[workbook_offset + 66] = 2
        struct.pack_into("<III", directory, workbook_offset + 68, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
        struct.pack_into("<I", directory, workbook_offset + 116, 2)
        struct.pack_into("<Q", directory, workbook_offset + 120, 4096)

        fat = bytearray(b"\xff" * 512)
        struct.pack_into("<I", fat, 0 * 4, 0xFFFFFFFE)
        struct.pack_into("<I", fat, 1 * 4, 0xFFFFFFFD)
        for sector_id in range(2, 9):
            struct.pack_into("<I", fat, sector_id * 4, sector_id + 1)
        struct.pack_into("<I", fat, 9 * 4, 0xFFFFFFFE)
        records = struct.pack("<HH", 0x0809, 4) + b"\x00" * 4
        if encrypted:
            records += struct.pack("<HH", 0x002F, 2) + b"\x00" * 2
        records += struct.pack("<HH", 0x000A, 0)
        workbook_stream = records.ljust(4096, b"\0")
        path.write_bytes(header + directory + fat + workbook_stream)

    def test_routes_legacy_xls_by_cfb_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xls"
            self.make_cfb_excel(source)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("xls", report["subtype"])
            self.assertTrue(report["requires_conversion"])

    def test_routes_xlsx_ooxml(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsx"
            self.make_ooxml(source)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("xlsx", report["subtype"])
            self.assertEqual("artifact-tool", report["engine"])

    def test_routes_xlsm_and_requires_macro_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            self.make_ooxml(source, macro=True)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("xlsm", report["subtype"])
            self.assertTrue(report["preserve_vba"])
            self.assertEqual("excel-com-macro-safe", report["engine"])

    def test_routes_empty_macro_enabled_container_as_xlsm(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            self.make_ooxml(source, macro_container=True)
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("xlsm", report["subtype"])
            self.assertEqual("excel-com-macro-safe", report["engine"])

    def test_rejects_extension_signature_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsx"
            self.make_cfb_excel(source)
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("mismatch", json.loads(result.stdout)["error"].lower())

    def test_rejects_truncated_or_non_excel_cfb(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xls"
            source.write_bytes(CFB + b"\0" * 504)
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("cfb", json.loads(result.stdout)["error"].lower())

    def test_rejects_cfb_with_workbook_name_but_no_fat(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xls"
            header = bytearray(512)
            header[:8] = CFB
            header[28:30] = b"\xFE\xFF"
            struct.pack_into("<H", header, 30, 9)
            fake_directory = bytearray(512)
            encoded = "Workbook\0".encode("utf-16le")
            fake_directory[: len(encoded)] = encoded
            struct.pack_into("<H", fake_directory, 64, len(encoded))
            fake_directory[66] = 2
            source.write_bytes(header + fake_directory)
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("cfb", json.loads(result.stdout)["error"].lower())

    def test_rejects_invalid_content_types_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            with ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", "<workbook/>")
                archive.writestr("[Content_Types].xml", "<broken macroEnabled")
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("xml", json.loads(result.stdout)["error"].lower())

    def test_rejects_unknown_workbook_content_type(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsx"
            with ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
                archive.writestr("[Content_Types].xml", '<Types><Override PartName="/xl/workbook.xml" ContentType="application/octet-stream"/></Types>')
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("content type", json.loads(result.stdout)["error"].lower())

    def test_rejects_workbook_without_spreadsheetml_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsx"
            with ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", "<workbook/>")
                archive.writestr("[Content_Types].xml", f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("namespace", json.loads(result.stdout)["error"].lower())

    def test_rejects_vba_in_xlsx_content_type(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            self.make_ooxml(source)
            with ZipFile(source, "a") as archive:
                archive.writestr("xl/vbaProject.bin", b"macro")
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("vba", json.loads(result.stdout)["error"].lower())

    def test_rejects_biff_filepass_encryption(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "encrypted.xls"
            self.make_cfb_excel(source, encrypted=True)
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("encrypted", json.loads(result.stdout)["error"].lower())

    def test_rejects_misresolved_vba_relationship_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            self.make_ooxml(source, macro=True, vba_target="xl/vbaProject.bin")
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("vba", json.loads(result.stdout)["error"].lower())

    def test_rejects_dangling_vba_content_type_without_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            with ZipFile(source, "w") as archive:
                archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
                archive.writestr("[Content_Types].xml", f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/><Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("vba", json.loads(result.stdout)["error"].lower())

    def test_rejects_dangling_vba_relationship_without_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "equipment.xlsm"
            self.make_ooxml(source, macro_container=True)
            with ZipFile(source, "a") as archive:
                archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdVba" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>')
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            self.assertIn("vba", json.loads(result.stdout)["error"].lower())


if __name__ == "__main__":
    unittest.main()
