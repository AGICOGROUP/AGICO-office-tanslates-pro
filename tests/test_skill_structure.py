from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_NAME = "水泥专业名词中英对照.md"
EXPECTED_GLOSSARY_SHA256 = "1fe11d08d4f42ea34c752ea1a7a1f6653dd27235a461dbece51981991a082356"


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
        normalized = " ".join(text.split())
        self.assertIn("Use when", text)
        for extension in (".docx", ".xlsx", ".pptx"):
            self.assertIn(extension, text)
        self.assertIn("scripts/route_office_file.py", text)
        for adapter in (
            "formats/word/SKILL.md",
            "formats/excel/SKILL.md",
            "formats/ppt/SKILL.md",
        ):
            self.assertIn(adapter, text)
        for removed in ("formats/pdf", "formats/image", ".pdf", ".png", ".jpg", ".jpeg"):
            self.assertNotIn(removed, text)
        self.assertEqual(
            {"word", "excel", "ppt"},
            {path.name for path in (ROOT / "formats").iterdir() if path.is_dir()},
        )
        self.assertIn("Routing ends immediately", normalized)
        self.assertIn("Do not read or consider any other format adapter", normalized)
        for downstream_rule in ("Hash and preserve", "glossary", "protected tokens", "render"):
            self.assertNotIn(downstream_rule, text)

    def test_selected_office_adapters_do_not_return_to_the_root_router(self):
        for adapter in ("word", "excel", "ppt"):
            text = (ROOT / "formats" / adapter / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(adapter=adapter):
                self.assertIn("Top-level routing is complete", text)
                self.assertIn("Do not run the root Office router again", text)

    def test_root_ui_metadata_exists(self):
        metadata = ROOT / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('display_name: "', text)
        self.assertIn('short_description: "', text)
        self.assertIn('$office-translate-pro', text)
        for removed in ("PDF", "PNG", "JPEG", "image"):
            self.assertNotIn(removed, text)

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
            "does not depend on another Office translation skill",
            f"../../references/{GLOSSARY_NAME}",
            "editable",
            "image text",
            "protected tokens",
            "Never overwrite",
            "Microsoft Word",
            "without an external PDF conversion or rendering gate",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for forbidden in (
            "documents:documents",
            "render every page",
            "complete rendered comparison",
            "ExportAsFixedFormat",
            "Inspect every final page",
            "page count",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        self.assertIn("word_pipeline.py", text)
        self.assertIn("optional and non-blocking", text)
        self.assertNotIn("Deliver only after that one Word-native validation passes", text)

    def test_word_ui_metadata_exists(self):
        metadata = ROOT / "formats" / "word" / "agents" / "openai.yaml"
        self.assertTrue(metadata.is_file())
        text = metadata.read_text(encoding="utf-8")
        self.assertIn('$translate-word-professionally', text)

if __name__ == "__main__":
    unittest.main()
