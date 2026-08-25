from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExcelSkillContractTests(unittest.TestCase):
    def test_required_files_exist(self):
        required = {
            "SKILL.md",
            "agents/openai.yaml",
            "references/excel-workflow.md",
            "references/manifest-schema.md",
            "references/image-text-localization.md",
            "references/bilingual-row-layout.md",
            "references/pipeline-cli.md",
            "scripts/route_excel_file.py",
            "scripts/excel_pipeline.mjs",
            "scripts/resolve_repo_glossary.py",
            "scripts/validate_manifest.py",
        }
        missing = sorted(path for path in required if not (ROOT / path).is_file())
        self.assertEqual([], missing)

    def test_skill_routes_every_job_through_balanced_resumable_pipeline(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "references" / "excel-workflow.md").read_text(encoding="utf-8")
        combined = skill + "\n" + workflow
        for token in (
            "excel_pipeline.mjs",
            "inspect",
            "prepare",
            "apply",
            "verify",
            "render",
            "job-state.json",
            "safe deduplication",
            "SHA-256",
            "strict",
        ):
            self.assertIn(token, combined)
        for obsolete in (
            "do not deduplicate repeated text",
            "Review every image",
            "render every final sheet and print area",
        ):
            self.assertNotIn(obsolete, combined)

    def test_skill_is_excel_only_and_complete(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "translate-excel-professionally",
            "spreadsheets:Spreadsheets",
            ".xls",
            ".xlsx",
            ".xlsm",
            "../../references/水泥专业名词中英对照.md",
            "route_excel_file.py",
            "resolve_repo_glossary.py",
            "validate_manifest.py",
            "formula",
            "image",
            "render",
        ]
        missing = [token for token in required if token not in skill]
        self.assertEqual([], missing)

    def test_bilingual_excel_defaults_to_paired_blue_translation_rows(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "references" / "excel-workflow.md").read_text(encoding="utf-8")
        layout_path = ROOT / "references" / "bilingual-row-layout.md"
        self.assertIn("references/bilingual-row-layout.md", skill)
        self.assertIn("bilingual-row-layout.md", workflow)
        self.assertTrue(layout_path.is_file())
        layout = layout_path.read_text(encoding="utf-8")
        for phrase in (
            "source row",
            "translation row",
            "#EAF2F8",
            "#1F4E78",
            "italic",
            "Do not duplicate numeric values",
            "protected identifiers",
            "formulas",
            "page breaks",
        ):
            self.assertIn(phrase, layout)

    def test_no_placeholders_or_generated_caches(self):
        placeholders = []
        caches = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if "tests" in relative.parts:
                continue
            if path.suffix.lower() in {".md", ".yaml", ".py", ".ps1"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "TODO" in text or "[TODO" in text:
                    placeholders.append(str(relative))
            if "__pycache__" in relative.parts or path.suffix.lower() == ".pyc":
                caches.append(str(relative))
        self.assertEqual([], placeholders)
        self.assertEqual([], caches)


if __name__ == "__main__":
    unittest.main()
