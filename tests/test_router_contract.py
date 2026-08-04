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

    def test_routes_ooxml_by_package_signature(self):
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
                    self.assertEqual("ooxml-signature", report["detection"])
                    self.assertFalse(report["extension_mismatch"])
                    self.assertFalse(report["requires_conversion"])

    def test_routes_legacy_cfb_after_signature_confirmation(self):
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
                    self.assertEqual("cfb-signature+extension", report["detection"])
                    self.assertFalse(report["extension_mismatch"])
                    self.assertTrue(report["requires_conversion"])

    def test_routes_pdf_by_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.pdf"
            source.write_bytes(b"%PDF-1.7\n% route contract fixture\n")
            result = self.run_router(source)
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual("pdf", report["format"])
            self.assertEqual("formats/pdf/SKILL.md", report["adapter"])
            self.assertEqual("pdf-signature", report["detection"])
            self.assertFalse(report["extension_mismatch"])
            self.assertFalse(report["requires_conversion"])

    def test_rejects_pdf_extension_and_signature_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            wrong_extension = root / "sample.bin"
            wrong_extension.write_bytes(b"%PDF-1.7\n")
            result = self.run_router(wrong_extension)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertTrue(report["extension_mismatch"])
            self.assertIn("does not match", report["error"])

            fake_pdf = root / "fake.pdf"
            fake_pdf.write_bytes(b"not a pdf")
            result = self.run_router(fake_pdf)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertIsNone(report["format"])
            self.assertIn("signature", report["error"])

    def test_rejects_extension_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_ooxml(Path(directory), "wrong.xlsx", "word/document.xml")
            result = self.run_router(source)
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertTrue(report["extension_mismatch"])
            self.assertIn("does not match", report["error"])

    def test_rejects_unknown_or_ambiguous_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unknown = self.make_ooxml(root, "unknown.docx", "custom/data.xml")
            result = self.run_router(unknown)
            self.assertEqual(2, result.returncode)
            self.assertIn("unsupported", json.loads(result.stdout)["error"])

            ambiguous = root / "ambiguous.docx"
            with zipfile.ZipFile(ambiguous, "w") as archive:
                archive.writestr("word/document.xml", "<root/>")
                archive.writestr("xl/workbook.xml", "<root/>")
            result = self.run_router(ambiguous)
            self.assertEqual(2, result.returncode)
            self.assertIn("ambiguous", json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
