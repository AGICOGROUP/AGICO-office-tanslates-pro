from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_NAME = "水泥专业名词中英对照.md"
EXPECTED_GLOSSARY_SHA256 = "9b74a21a2625e9745666483e0e1b546cc21745b3fcbcccd976a57eeca4a5022f"


class RootSkillStructureTests(unittest.TestCase):
    def test_python_caches_are_excluded_from_the_repository(self):
        ignore_file = ROOT / ".gitignore"
        self.assertTrue(ignore_file.is_file())
        patterns = set(ignore_file.read_text(encoding="utf-8").splitlines())
        self.assertIn("__pycache__/", patterns)
        self.assertIn("*.pyc", patterns)

    def test_root_skill_is_the_upload_router(self):
        skill = ROOT / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("Use when", text)
        for extension in (".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg"):
            self.assertIn(extension, text)
        self.assertIn("scripts/route_office_file.py", text)
        for adapter in (
            "formats/word/SKILL.md",
            "formats/excel/SKILL.md",
            "formats/ppt/SKILL.md",
            "formats/pdf/SKILL.md",
            "formats/image/SKILL.md",
        ):
            self.assertIn(adapter, text)
        self.assertIn(f"references/{GLOSSARY_NAME}", text)

    def test_root_ui_metadata_exists(self):
        metadata = ROOT / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('display_name: "', text)
        self.assertIn('short_description: "', text)
        self.assertIn('$office-translate-pro', text)

    def test_shared_glossary_is_complete_source_copy(self):
        glossary = ROOT / "references" / GLOSSARY_NAME
        self.assertTrue(glossary.is_file())
        digest = hashlib.sha256(glossary.read_bytes()).hexdigest()
        self.assertEqual(EXPECTED_GLOSSARY_SHA256, digest)


class WordAdapterStructureTests(unittest.TestCase):
    def test_word_adapter_encodes_the_preservation_contract(self):
        skill = ROOT / "formats" / "word" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        required_phrases = (
            "documents:documents",
            "does not depend on another Office translation skill",
            f"../../references/{GLOSSARY_NAME}",
            "editable",
            "image text",
            "protected tokens",
            "Never overwrite",
            "render every page",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_word_ui_metadata_exists(self):
        metadata = ROOT / "formats" / "word" / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('$translate-word-professionally', text)


class PdfAdapterStructureTests(unittest.TestCase):
    def test_pdf_router_and_independent_adapters_exist(self):
        router = ROOT / "formats" / "pdf" / "SKILL.md"
        self.assertTrue(router.is_file())
        text = router.read_text(encoding="utf-8")
        self.assertIn("scripts/route_pdf_file.py", text)
        self.assertIn("formats/pdf/native/SKILL.md", text)
        self.assertIn("formats/pdf/scan/SKILL.md", text)

        native = ROOT / "formats" / "pdf" / "native" / "SKILL.md"
        scan = ROOT / "formats" / "pdf" / "scan" / "SKILL.md"
        self.assertTrue(native.is_file())
        self.assertTrue(scan.is_file())
        self.assertNotEqual(native.read_bytes(), scan.read_bytes())

    def test_bilingual_pdf_keeps_any_source_language_and_adds_chinese(self):
        router = (ROOT / "formats" / "pdf" / "SKILL.md").read_text(encoding="utf-8")
        bilingual = (ROOT / "formats" / "pdf" / "bilingual" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for text in (router, bilingual):
            self.assertIn("source language", text.lower())
            self.assertIn("Chinese", text)
        self.assertIn("unchanged", bilingual)


class ImageAdapterStructureTests(unittest.TestCase):
    def test_image_adapter_reuses_scan_pdf_workflow(self):
        skill = ROOT / "formats" / "image" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("formats/pdf/scan/SKILL.md", text)
        self.assertIn("same pixel dimensions", text)
        self.assertIn("same image format", text)


if __name__ == "__main__":
    unittest.main()
