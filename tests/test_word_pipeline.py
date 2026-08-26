from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "formats" / "word" / "scripts" / "word_pipeline.py"
WORD_COM = ROOT / "formats" / "word" / "scripts" / "word_com.ps1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class WordPipelineContractTests(unittest.TestCase):
    def load_pipeline(self):
        spec = importlib.util.spec_from_file_location("word_pipeline_test_module", PIPELINE)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(PIPELINE.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        return module

    def make_docx(self, root: Path, body: str | None = None) -> Path:
        path = root / "source.docx"
        body = body or '<w:p><w:r><w:t>设备</w:t></w:r></w:p>'
        xml = f'<w:document xmlns:w="{W_NS}" xmlns:custom="urn:keep-me"><w:body>{body}</w:body></w:document>'
        with ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", xml)
            archive.writestr("word/media/image1.png", b"keep")
        return path

    def test_prepare_creates_complete_translation_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            result = subprocess.run(
                [sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"],
                capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = json.loads((job / "translation-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("设备", manifest["units"][0]["source"])
            self.assertEqual("", manifest["units"][0]["target"])

    def test_apply_uses_manifest_and_preserves_package_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root)
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            with ZipFile(output) as archive:
                self.assertEqual(b"keep", archive.read("word/media/image1.png"))
                xml = archive.read("word/document.xml")
            self.assertIn(b"Equipment", xml)
            self.assertIn(b"urn:keep-me", xml)

    def test_apply_covers_paragraphs_with_tabs_and_preserves_the_tab_node(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t>第一章</w:t><w:tab/><w:t>- 1 -</w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("第一章\t- 1 -", manifest["units"][0]["source"])
            manifest["units"][0]["target"] = "Chapter 1\t- 1 -"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(0, result.returncode, result.stderr)
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml")
            self.assertIn(b"Chapter 1", xml)
            self.assertIn(b"<w:tab", xml)
            apply_report = json.loads((job / "apply-report.json").read_text(encoding="utf-8"))
            self.assertEqual(1, apply_report["applied_occurrences"])
            self.assertEqual([], apply_report["unmatched_unit_ids"])

    def test_apply_distributes_translation_across_existing_formatted_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>设备</w:t></w:r>'
                '<w:r><w:rPr><w:i/></w:rPr><w:t>清单</w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Equipment List"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], check=True)
            with ZipFile(output) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:b", xml)
            self.assertIn("<w:i", xml)
            self.assertNotIn("<w:t></w:t>", xml)
            self.assertIn("Equipment", xml)
            self.assertIn(" List", xml)

    def test_failed_apply_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(root, '<w:p><w:r><w:t>章节</w:t><w:tab/><w:t>1</w:t></w:r></w:p>')
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = "Chapter 1"  # Missing the protected tab: apply must fail.
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            output.write_bytes(b"existing-valid-output")
            result = subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(2, result.returncode)
            self.assertEqual(b"existing-valid-output", output.read_bytes())

    def test_identity_translation_preserves_run_text_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_docx(
                root,
                '<w:p><w:r><w:t xml:space="preserve"> 设备</w:t></w:r>'
                '<w:r><w:t xml:space="preserve">清单 </w:t></w:r></w:p>',
            )
            job = root / "job"
            subprocess.run([sys.executable, str(PIPELINE), "prepare", str(source), "--job-dir", str(job), "--target-language", "English"], check=True)
            manifest_path = job / "translation-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["units"][0]["target"] = manifest["units"][0]["source"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            output = root / "translated.docx"
            subprocess.run([sys.executable, str(PIPELINE), "apply", str(manifest_path), "--output", str(output)], check=True)
            with ZipFile(source) as before, ZipFile(output) as after:
                before_xml = before.read("word/document.xml").decode("utf-8")
                after_xml = after.read("word/document.xml").decode("utf-8")
            self.assertIn("> 设备<", before_xml)
            self.assertIn("> 设备<", after_xml)
            self.assertIn(">清单 <", before_xml)
            self.assertIn(">清单 <", after_xml)

    def test_static_validation_rejects_changed_source_and_missing_targets(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("source file hash changed", text)
        self.assertIn("missing target text", text)
        self.assertIn("protected token mismatch", text)

    def test_protected_token_normalization_accepts_equivalent_office_notation(self):
        pipeline = self.load_pipeline()
        self.assertEqual(
            {"10kv", "1.4°c", "40mm"},
            pipeline.normalize_protected_tokens(["10Kv", "10 kV", "1,4 ℃", "40 mm"]),
        )

    def test_com_contract_uses_visible_legacy_conversion_and_single_content_page_measure(self):
        text = WORD_COM.read_text(encoding="utf-8")
        self.assertIn("$word.Visible = $true", text)
        self.assertIn("SaveAs2", text)
        self.assertNotIn("ComputeStatistics", text)
        self.assertIn("Content.Information(4)", text)

    def test_pipeline_bypasses_local_powershell_script_policy(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn('"-ExecutionPolicy", "Bypass"', text)


if __name__ == "__main__":
    unittest.main()
