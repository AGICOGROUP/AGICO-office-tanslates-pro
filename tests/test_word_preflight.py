from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "formats" / "word" / "scripts" / "analyze_docx.py"
NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class WordPreflightTests(unittest.TestCase):
    def make_docx(self, root: Path, document_body: str, extra_parts: dict[str, str | bytes] | None = None) -> Path:
        path = root / "sample.docx"
        document = f'<w:document xmlns:w="{NS}"><w:body>{document_body}</w:body></w:document>'
        with ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", document)
            for name, content in (extra_parts or {}).items():
                archive.writestr(name, content)
        return path

    def run_preflight(self, path: Path) -> dict:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(result.stdout)

    def test_regular_text_and_tables_stay_on_fast_path_and_are_extracted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            body = (
                "<w:p><w:r><w:t>设备清单</w:t></w:r></w:p>"
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>设备</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                "<w:p><w:r><w:t>设备</w:t></w:r></w:p>"
            )
            path = self.make_docx(Path(directory), body, {"word/media/image1.png": b"png"})
            report = self.run_preflight(path)

        self.assertEqual("fast", report["path"])
        self.assertEqual(3, report["text_occurrence_count"])
        self.assertEqual(["设备清单", "设备"], report["unique_texts"])
        self.assertEqual(1, report["media_count"])
        self.assertTrue(report["needs_image_triage"])
        self.assertEqual([], report["complex_reasons"])

    def test_tracked_changes_and_text_boxes_escalate_to_complex_path(self):
        with tempfile.TemporaryDirectory() as directory:
            body = (
                "<w:p><w:ins><w:r><w:t>修订内容</w:t></w:r></w:ins></w:p>"
                "<w:txbxContent><w:p><w:r><w:t>文本框</w:t></w:r></w:p></w:txbxContent>"
            )
            report = self.run_preflight(self.make_docx(Path(directory), body))

        self.assertEqual("complex", report["path"])
        self.assertIn("tracked_changes", report["complex_reasons"])
        self.assertIn("text_boxes", report["complex_reasons"])

    def test_nested_text_box_text_is_not_duplicated_into_its_outer_paragraph(self):
        with tempfile.TemporaryDirectory() as directory:
            body = (
                "<w:p><w:r><w:t>外层</w:t></w:r>"
                "<w:txbxContent><w:p><w:r><w:t>文本框</w:t></w:r></w:p></w:txbxContent>"
                "</w:p>"
            )
            report = self.run_preflight(self.make_docx(Path(directory), body))

        self.assertEqual(["外层", "文本框"], report["unique_texts"])
        self.assertEqual(2, report["text_occurrence_count"])

    def test_page_number_field_stays_fast_but_toc_field_escalates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page_body = '<w:p><w:r><w:instrText> PAGE </w:instrText></w:r></w:p>'
            page_report = self.run_preflight(self.make_docx(root, page_body))
            toc_body = '<w:p><w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r></w:p>'
            toc_report = self.run_preflight(self.make_docx(root, toc_body))

        self.assertEqual("fast", page_report["path"])
        self.assertEqual("complex", toc_report["path"])
        self.assertIn("complex_fields", toc_report["complex_reasons"])

    def test_default_note_separator_parts_do_not_trigger_complex_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default_notes = (
                f'<w:footnotes xmlns:w="{NS}">'
                '<w:footnote w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                "</w:footnotes>"
            )
            fast_report = self.run_preflight(
                self.make_docx(root, "<w:p><w:r><w:t>正文</w:t></w:r></w:p>", {"word/footnotes.xml": default_notes})
            )
            real_notes = (
                f'<w:footnotes xmlns:w="{NS}">'
                '<w:footnote w:id="1"><w:p><w:r><w:t>真实脚注</w:t></w:r></w:p></w:footnote>'
                "</w:footnotes>"
            )
            complex_report = self.run_preflight(
                self.make_docx(root, "<w:p><w:r><w:t>正文</w:t></w:r></w:p>", {"word/footnotes.xml": real_notes})
            )

        self.assertEqual("fast", fast_report["path"])
        self.assertEqual("complex", complex_report["path"])
        self.assertIn("footnotes", complex_report["complex_reasons"])

    def test_output_file_mode_prints_only_a_compact_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root, "<w:p><w:r><w:t>设备</w:t></w:r></w:p>")
            output = root / "preflight.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            summary = json.loads(result.stdout)
            full_report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("fast", summary["path"])
        self.assertNotIn("occurrences", summary)
        self.assertNotIn("unique_texts", summary)
        self.assertEqual(1, full_report["text_occurrence_count"])


if __name__ == "__main__":
    unittest.main()
