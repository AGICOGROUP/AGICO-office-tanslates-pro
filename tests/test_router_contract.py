from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "scripts" / "route_office_file.py"
CFB_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class OfficeRouterContractTests(unittest.TestCase):
    def run_router(self, source: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROUTER), str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def make_ooxml(self, directory: Path, name: str, entry: str) -> Path:
        source = directory / name
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr(entry, "<root/>")
        return source

    def test_routes_supported_files_by_extension_only(self):
        cases = (
            ("sample.docx", "word/document.xml", "word"),
            ("sample.xlsx", "xl/workbook.xml", "excel"),
            ("sample.pptx", "ppt/presentation.xml", "ppt"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, entry, expected_format in cases:
                with self.subTest(filename=filename):
                    result = self.run_router(self.make_ooxml(root, filename, entry))
                    self.assertEqual(0, result.returncode, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(expected_format, report["format"])
                    self.assertEqual(
                        f"formats/{expected_format}/SKILL.md", report["adapter"]
                    )
                    self.assertEqual("extension", report["detection"])
                    self.assertFalse(report["extension_mismatch"])
                    self.assertFalse(report["requires_conversion"])

    def test_routes_legacy_files_by_extension_without_container_inspection(self):
        cases = (("sample.doc", "word"), ("sample.xls", "excel"), ("sample.ppt", "ppt"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, expected_format in cases:
                with self.subTest(filename=filename):
                    source = root / filename
                    source.write_bytes(CFB_SIGNATURE + bytes(504))
                    result = self.run_router(source)
                    self.assertEqual(0, result.returncode, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(expected_format, report["format"])
                    self.assertEqual("extension", report["detection"])
                    self.assertFalse(report["extension_mismatch"])
                    self.assertTrue(report["requires_conversion"])

    def test_rejects_pdf_and_static_images_as_unsupported(self):
        cases = (
            ("sample.pdf", b"%PDF-1.7\n"),
            ("sample.png", b"\x89PNG\r\n\x1a\n" + bytes(16)),
            ("sample.jpg", b"\xff\xd8\xff\xe0" + bytes(16)),
            ("sample.jpeg", b"\xff\xd8\xff\xe1" + bytes(16)),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, payload in cases:
                with self.subTest(filename=filename):
                    source = root / filename
                    source.write_bytes(payload)
                    result = self.run_router(source)
                    self.assertEqual(2, result.returncode)
                    report = json.loads(result.stdout)
                    self.assertIsNone(report["format"])
                    self.assertIsNone(report["adapter"])
                    self.assertIn("unsupported", report["error"])

    def test_rejects_macro_enabled_office_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ("sample.docm", "sample.xlsm", "sample.pptm"):
                with self.subTest(filename=filename):
                    source = root / filename
                    source.write_bytes(b"not-opened-by-root-router")
                    result = self.run_router(source)
                    self.assertEqual(2, result.returncode)
                    report = json.loads(result.stdout)
                    self.assertIsNone(report["format"])
                    self.assertIn("unsupported", report["error"])

    def test_extension_is_authoritative_even_when_container_looks_like_another_format(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_ooxml(Path(directory), "wrong.xlsx", "word/document.xml")
            result = self.run_router(source)
            self.assertEqual(0, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual("excel", report["format"])
            self.assertEqual("extension", report["detection"])
            self.assertFalse(report["extension_mismatch"])
            self.assertIsNone(report["error"])

    def test_supported_extension_routes_even_for_unknown_or_ambiguous_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unknown = self.make_ooxml(root, "unknown.docx", "custom/data.xml")
            result = self.run_router(unknown)
            self.assertEqual(0, result.returncode)
            self.assertEqual("word", json.loads(result.stdout)["format"])

            ambiguous = root / "ambiguous.docx"
            with zipfile.ZipFile(ambiguous, "w") as archive:
                archive.writestr("word/document.xml", "<root/>")
                archive.writestr("xl/workbook.xml", "<root/>")
            result = self.run_router(ambiguous)
            self.assertEqual(0, result.returncode)
            self.assertEqual("word", json.loads(result.stdout)["format"])


if __name__ == "__main__":
    unittest.main()
